"""
OCR service for scanned PDF documents using Gemini Vision multimodal API.

Strategy:
1. Render PDF pages as images via PyMuPDF (fast, local)
2. Stage 1: determine which provided pages contain Table 4 / Table 5 + extract document metadata
3. Stage 2: extract table_4/table_5 ONLY from the selected pages (NO full_text)
4. Falls back gracefully.
"""

import logging
import base64
import json
import os
import time
from typing import Optional, Any

from dotenv import load_dotenv
import requests

load_dotenv()

logger = logging.getLogger(__name__)


def _render_page_as_base64_png(pdf_path: str, page_index: int, dpi: int = 200) -> Optional[str]:
    """Render a single PDF page to base64-encoded PNG image."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
        return None

    try:
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return None
        page = doc[page_index]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to render page {page_index}: {e}")
        return None


def _call_gemini_vision_multipage(
    prompt_text: str,
    images_base64: list,
    model: str = "google/gemini-2.5-flash",
    temperature: float = 0.1,
) -> Optional[str]:
    """Send multiple page images to Gemini Vision in ONE multipart API call."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not images_base64:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "AI Report Generator - OCR",
    }

    content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for img_b64 in images_base64:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            }
        )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content_parts}],
        "temperature": temperature,
        "max_tokens": 8192,
    }

    max_retries = 3
    base_delay = 3

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.warning(f"Vision API attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2**attempt))
            else:
                logger.error("All Vision API retries exhausted")
                return None
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Vision API response: {e}")
            return None

    return None


def _strip_code_fences(s: str) -> str:
    cleaned = s.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1)
    elif cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1)
    if cleaned.endswith("```"):
        cleaned = cleaned[::-1].replace("```", "", 1)[::-1]
    return cleaned.strip()


def _safe_json_loads(s: str) -> dict:
    try:
        return json.loads(_strip_code_fences(s))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON. Error: {e}. First 400 chars: {s[:400]}")
        return {}


def analyze_scanned_pdf(
    pdf_path: str,
    instructions: str = "",
    dpi: int = 150,
    max_pages: int = 6,
) -> dict:
    """Complete analysis of a scanned PDF using Gemini Vision (2-stage OCR).

    Returns:
      {
        "error": str|None,
        "document_type": str,
        "extraction_quality_score": float,
        "total_pages": int,
        "key_metadata": {issue_date, document_number, authority},
        "raw_text": "",
        "table_4_candidate": dict|None,
        "table_5_candidate": dict|None,
        "insights": list
      }
    """

    # Step 0: Check PyMuPDF
    try:
        import fitz
    except ImportError:
        return {"error": "PyMuPDF not installed. Run: pip install PyMuPDF"}

    # Step 1: open PDF and compute total pages
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        return {"error": f"Cannot open PDF: {e}"}

    # Step 2: choose candidate pages to render
    pages_to_render = set()
    for i in range(min(3, total_pages)):
        pages_to_render.add(i)
    for i in range(3, min(9, total_pages)):
        pages_to_render.add(i)
    if total_pages > 1:
        pages_to_render.add(total_pages - 1)

    pages_to_render = sorted(list(pages_to_render))[:max_pages]
    logger.info(f"Rendering {len(pages_to_render)} pages: {pages_to_render}")

    page_images: list[str] = []
    page_labels: list[str] = []
    for pg in pages_to_render:
        img_b64 = _render_page_as_base64_png(pdf_path, pg, dpi)
        if img_b64:
            page_images.append(img_b64)
            page_labels.append(f"Страница {pg + 1} из {total_pages}")
        else:
            logger.warning(f"Could not render page {pg}")

    if not page_images:
        return {
            "error": "Failed to render any pages from the PDF",
            "document_type": "Неизвестно",
            "extraction_quality_score": 0.0,
            "total_pages": total_pages,
            "key_metadata": {"issue_date": "", "document_number": "", "authority": ""},
            "raw_text": "",
            "table_4_candidate": None,
            "table_5_candidate": None,
            "insights": [],
        }

    pages_map_1based_to_subset_index = {pg + 1: idx for idx, pg in enumerate(pages_to_render)}

    # -------- Stage 1 prompt --------
    stage1_prompt = (
        "Ты — эксперт по документам недвижимости Республики Беларусь.\n"
        f"Всего страниц в документе: {total_pages}\n"
        "Тебе предоставлены изображения следующих страниц (в формате: Страница X из Y):\n"
        f"{chr(10).join(f'- {lbl}' for lbl in page_labels)}\n\n"
        "Задача:\n"
        "1) Определи document_type (строго одно из: 'ЕГРНИ_Земля','ЕГРНИ_Помещение','Техпаспорт','Акт_Осмотра','Неизвестно').\n"
        "2) Извлеки key_metadata: issue_date, document_number, authority (если не найдено — пустые строки).\n"
        "3) Выбери страницы, где находятся Таблица 4 и/или Таблица 5: верни индексы страниц В ИСХОДНОМ ДОКУМЕНТЕ (1-based),\n"
        "   соответствующие 'Страница X из Y' из списка выше. Если не уверен — не добавляй.\n"
        "4) Оцени extraction_quality_score от 0.0 до 1.0 по читаемости предоставленных страниц.\n\n"
        "=== ФОРМАТ ОТВЕТА (строго JSON) ===\n"
        "{{\n"
        '  "document_type": "...",\n'
        '  "extraction_quality_score": 0.0,\n'
        '  "issue_date": "...",\n'
        '  "document_number": "...",\n'
        '  "authority": "...",\n'
        '  "table_4_pages": [1,2] или [],\n'
        '  "table_5_pages": [1,2] или [],\n'
        '  "insights": [{{"title":"...","severity":"INFO|WARNING|CRITICAL","description":"..."}}]\n'
        "}}\n\n"
        "Инструкции пользователя: {instructions}"
    ).format(instructions=instructions)

    logger.info("OCR Stage 1: selecting pages for Table 4/5...")
    response1 = _call_gemini_vision_multipage(stage1_prompt, page_images)
    if not response1:
        return {
            "error": "Gemini Vision API returned no response (stage 1)",
            "document_type": "Неизвестно",
            "extraction_quality_score": 0.0,
            "total_pages": total_pages,
            "key_metadata": {"issue_date": "", "document_number": "", "authority": ""},
            "raw_text": "",
            "table_4_candidate": None,
            "table_5_candidate": None,
            "insights": [],
        }

    parsed1 = _safe_json_loads(response1)

    doc_type = parsed1.get("document_type", "Неизвестно")
    quality = float(parsed1.get("extraction_quality_score", 0.5) or 0.5)
    key_metadata = {
        "issue_date": parsed1.get("issue_date", ""),
        "document_number": parsed1.get("document_number", ""),
        "authority": parsed1.get("authority", ""),
    }
    insights = parsed1.get("insights", [])

    table4_pages_1based = parsed1.get("table_4_pages", []) or []
    table5_pages_1based = parsed1.get("table_5_pages", []) or []

    table4_subset_indices = [
        pages_map_1based_to_subset_index[p] for p in table4_pages_1based if p in pages_map_1based_to_subset_index
    ]
    table5_subset_indices = [
        pages_map_1based_to_subset_index[p] for p in table5_pages_1based if p in pages_map_1based_to_subset_index
    ]

    # -------- Stage 2 prompt --------
    stage2_images: list[str] = []
    stage2_labels: list[str] = []

    used_indices = set()
    for idx in table4_subset_indices + table5_subset_indices:
        if idx in used_indices:
            continue
        used_indices.add(idx)
        stage2_images.append(page_images[idx])
        stage2_labels.append(f"Страница {pages_to_render[idx] + 1} из {total_pages}")

    # fallback: if stage1 didn't find table pages, use whole subset
    # (note: even then we still extract only table_4/table_5)
    if not stage2_images:
        stage2_images = page_images
        stage2_labels = page_labels

    stage2_prompt = (
        "Ты — эксперт по извлечению табличных данных из документов недвижимости (Республика Беларусь).\n"
        "Извлеки ТОЛЬКО Таблицу 4 и/или Таблицу 5 из предоставленных изображений.\n"
        "НЕ извлекай full_text, не добавляй никаких дополнительных полей кроме требуемых JSON.\n\n"
        "Страницы для извлечения:\n"
        f"{chr(10).join(f'- {lbl}' for lbl in stage2_labels)}\n\n"
        "Правила:\n"
        "- Если таблица не найдена — верни null для соответствующего объекта.\n"
        "- Если поле не удалось определить — верни null (для строк и чисел).\n\n"
        "=== Таблица 4 поля ===\n"
        "address, cadastral_number, area_ha, purpose_by_executive_committee, purpose_by_classifier, central_utilities,\n"
        "property_rights, right_holder_and_share, encumbrances_or_restrictions, cadastral_cost_per_sqm_usd\n\n"
        "=== Таблица 5 поля ===\n"
        "name_and_purpose, year_built, actual_condition, total_floors, object_floor, finishing_level,\n"
        "total_area_sqm, snb_area_sqm, living_area_sqm, walls_material, partitions_material, floors_structure,\n"
        "windows_and_openings, flooring_material, balcony_or_loggia, engineering_equipment\n\n"
        "=== ФОРМАТ ОТВЕТА (строго JSON) ===\n"
        "{{\n"
        '  "table_4": {{...}} или null,\n'
        '  "table_5": {{...}} или null\n'
        "}}"
    )

    logger.info("OCR Stage 2: extracting tables from selected pages...")
    response2 = _call_gemini_vision_multipage(stage2_prompt, stage2_images)
    if not response2:
        return {
            "error": "Gemini Vision API returned no response (stage 2)",
            "document_type": doc_type,
            "extraction_quality_score": quality,
            "total_pages": total_pages,
            "key_metadata": key_metadata,
            "raw_text": "",
            "table_4_candidate": None,
            "table_5_candidate": None,
            "insights": insights if isinstance(insights, list) else [],
        }

    parsed2 = _safe_json_loads(response2)

    return {
        "error": None,
        "document_type": doc_type,
        "extraction_quality_score": quality,
        "total_pages": total_pages,
        "key_metadata": key_metadata,
        "raw_text": "",
        "table_4_candidate": parsed2.get("table_4"),
        "table_5_candidate": parsed2.get("table_5"),
        "insights": insights if isinstance(insights, list) else [],
    }

