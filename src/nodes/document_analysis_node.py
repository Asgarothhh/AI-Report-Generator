import logging
import requests
import json
import os
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader

from src.schemas.states import GraphState, DocumentProfile
from src.utils.ocr_service import analyze_scanned_pdf

logger = logging.getLogger(__name__)


class DocumentProfileOutput(BaseModel):
    """
    Pydantic-модель для валидации структурированного ответа от LLM
    на этапе первичного профилирования и классификации документа.
    """
    document_type: str = Field(
        description="Тип документа. Строго одно из значений: 'ЕГРНИ_Земля', 'ЕГРНИ_Помещение', 'Техпаспорт', 'Акт_Осмотра', 'Неизвестно'."
    )
    extraction_quality_score: float = Field(
        description="Оценка читаемости и полноты текстового слоя от 0.0 (пустой/неразборчивый) до 1.0 (идеальный цифровой текст)."
    )
    key_metadata: Dict[str, Any] = Field(
        description="Словарь базовых реквизитов документа. Обязательные ключи: 'issue_date' (дата выдачи/составления), 'document_number' (номер выписки/паспорта), 'authority' (орган или фирма, выдавшая документ)."
    )
    summary_observations: str = Field(
        description="Краткий аналитический вывод о применимости документа: какие таблицы (Таблица 4 или 5) можно заполнить на его основе, есть ли визуальные дефекты или пропущенные страницы."
    )


def _extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """
    Извлекает текст из PDF.
    Возвращает (extracted_text, total_pages).
    Если PDF не содержит текстового слоя (скан), возвращает пустую строку.
    """
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)

    pages_to_read = list(range(min(total_pages, 8)))
    text_chunks = []
    for page_num in pages_to_read:
        page_text = reader.pages[page_num].extract_text() or ""
        text_chunks.append(f"--- СТРАНИЦА {page_num + 1} --- \n{page_text}")
    extracted_text = "\n".join(text_chunks)

    return extracted_text, total_pages


def document_analysis_node(state: GraphState) -> GraphState:
    """
    Узел LangGraph для первичного анализа, верификации и классификации входного документа.

    Args:
        state (GraphState): Текущее состояние графа автоматизации.

    Returns:
        GraphState: Обновленное состояние с заполненным профилем документа или флагом ошибки.
    """
    request_id = state.get('request_id', 'unknown_request')
    file_path = state.get('file_path')
    instructions = state.get('instructions', '')

    if not file_path:
        logger.error(f"Missing file_path for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = "Cannot perform document analysis: A file path was not provided."
        return state

    if not os.path.exists(file_path):
        logger.error(f"File not found at path: {file_path} for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = f"File not found at disk path: {file_path}"
        return state

    logger.info(f"DocumentAnalysisNode начали обработку запроса: {request_id}")

    file_extension = os.path.splitext(file_path)[1].lower()

    # --- ШАГ 1: Попытка извлечь текстовый слой из PDF ---
    extracted_text = ""
    total_pages = 1

    try:
        if file_extension == ".pdf":
            extracted_text, total_pages = _extract_text_from_pdf(file_path)
        elif file_extension in [".docx", ".txt"]:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                extracted_text = f.read()[:15000]
        else:
            extracted_text = ""

        # Если текст найден — используем старую логику с LLM через текст
        if extracted_text.strip():
            logger.info(f"PDF содержит текстовый слой ({len(extracted_text.strip())} chars) для {request_id}")
            return _classify_with_text_llm(state, extracted_text, total_pages, instructions)

        # --- ШАГ 2: Текст не найден — это скан. Используем OCR через Gemini Vision ---
        logger.warning(f"PDF не содержит текстового слоя (скан) для {request_id}. Запускаем OCR через Gemini Vision...")
        return _classify_with_vision_ocr(state, file_path, total_pages, instructions)

    except Exception as e:
        logger.error(f"Error reading document content for request {request_id}: {e}", exc_info=True)
        # Fallback: пытаемся через OCR, даже если pypdf выбросил исключение
        logger.info(f"Falling back to Vision OCR after PyPDF error for {request_id}")
        try:
            return _classify_with_vision_ocr(state, file_path, 1, instructions)
        except Exception as e2:
            logger.error(f"Vision OCR also failed: {e2}", exc_info=True)
            state['status'] = "error"
            state['error_message'] = f"Failed to parse document: {e}"
            return state


def _classify_with_text_llm(
    state: GraphState, extracted_text: str, total_pages: int, instructions: str
) -> GraphState:
    """Классификация документа через LLM на основе извлеченного текста."""
    request_id = state['request_id']
    file_path = state['file_path']

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        logger.error(f"OPENROUTER_API_KEY not found for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = "API key for OpenRouter not found."
        return state

    try:
        llm = ChatOpenAI(
            model="google/gemini-2.5-flash",
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.2,
            max_retries=0,
            model_kwargs={
                "extra_headers": {
                    "HTTP-Referer": "https://localhost",
                    "X-Title": "AI Report Generator"
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
        state['status'] = "error"
        state['error_message'] = f"Failed to initialize LLM: {e}"
        return state

    file_extension = os.path.splitext(file_path)[1].lower()
    profile_payload = {
        "file_name": os.path.basename(file_path),
        "file_extension": file_extension,
        "total_pages": total_pages,
        "text_sample": extracted_text[:8000]
    }

    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка {attempt + 1}/{max_retries} вызова LLM через OpenRouter для анализа профиля (текст)...")

            parser = JsonOutputParser(pydantic_object=DocumentProfileOutput)
            prompt = PromptTemplate(
                template="""
                Вы — специализированный ИИ-ассистент, эксперт по анализу юридических, кадастровых и технических документов в сфере недвижимости (Республика Беларусь).
                Ваша задача — классифицировать входящий документ и извлечь его первичные метаданные для системы автоматического составления отчетов об оценке.

                На основе предоставленного текста определите:
                1. **Тип документа**: строго одно из: 'ЕГРНИ_Земля', 'ЕГРНИ_Помещение', 'Техпаспорт', 'Акт_Осмотра', 'Неизвестно'.
                2. **extraction_quality_score**: от 0.0 до 1.0 — насколько хорошо читается текст.
                3. **key_metadata**: словарь с полями issue_date, document_number, authority (если не найдены — пустая строка).
                4. **summary_observations**: кратко — какие таблицы отчета можно заполнить, есть ли дефекты.

                Содержимое документа:
                {profile_payload}

                Инструкции пользователя: {instructions}

                {format_instructions}

                Ответ должен быть строго валидным JSON.
                """,
                input_variables=["profile_payload", "instructions"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            profile_payload_str = json.dumps(profile_payload, ensure_ascii=False, indent=2)

            llm_response = llm.invoke(prompt.invoke({
                "profile_payload": profile_payload_str,
                "instructions": instructions
            }))

            llm_raw_output_str = llm_response.content
            stripped_str = llm_raw_output_str.strip()

            if stripped_str.startswith("```json"):
                stripped_str = stripped_str.replace("```json", "", 1)
            if stripped_str.endswith("```"):
                stripped_str = stripped_str[::-1].replace("```", "", 1)[::-1]
            json_str = stripped_str.strip()

            if "do not have information on that topic" in json_str.lower():
                logger.warning(f"LLM вернула отказ для {request_id}. Создаём fallback-профиль.")
                state['document_profile'] = DocumentProfile(
                    document_type="Неизвестно",
                    total_pages=total_pages,
                    extraction_quality_score=max(0.1, len(extracted_text.strip()) / 5000),
                    key_metadata={
                        "issue_date": "",
                        "document_number": "",
                        "authority": "",
                        "note": "LLM отклонила запрос, создан fallback-профиль."
                    }
                )
                state['raw_extracted_texts'] = {"_fallback": extracted_text[:5000]}
                state['status'] = "document_profiled"
                return state

            parsed_data = json.loads(json_str)
            parsed_output = DocumentProfileOutput(**parsed_data)

            state['document_profile'] = DocumentProfile(
                document_type=parsed_output.document_type,
                total_pages=total_pages,
                extraction_quality_score=parsed_output.extraction_quality_score,
                key_metadata=parsed_output.key_metadata
            )
            state['raw_extracted_texts'] = {"_full": extracted_text}
            state['status'] = "document_profiled"

            logger.info(f"DocumentAnalysisNode успешно завершил работу для {request_id}. Определен тип: {parsed_output.document_type}")
            return state

        except (requests.exceptions.RequestException, TimeoutError) as e:
            logger.warning(f"Сетевой сбой при вызове OpenRouter на попытке {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                logger.error(f"Превышено число попыток подключения для запроса {request_id}.")
                state['status'] = "error"
                state['error_message'] = f"Failed to get a response from OpenRouter after {max_retries} attempts: {e}"
                return state

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON на попытке {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                state['document_profile'] = DocumentProfile(
                    document_type="Неизвестно",
                    total_pages=total_pages,
                    extraction_quality_score=max(0.1, len(extracted_text.strip()) / 5000),
                    key_metadata={
                        "issue_date": "",
                        "document_number": "",
                        "authority": "",
                        "note": "LLM вернула некорректный JSON. Создан fallback-профиль."
                    }
                )
                state['raw_extracted_texts'] = {"_fallback": extracted_text[:5000]}
                state['status'] = "document_profiled"
                return state

        except Exception as e:
            logger.error(f"Критическая непредвиденная ошибка для ID {request_id}: {e}", exc_info=True)
            state['status'] = "error"
            state['error_message'] = f"An unexpected error occurred during document profiling: {e}"
            return state

    state['status'] = "error"
    state['error_message'] = "An unexpected failure occurred after executing all LLM retries."
    return state


def _classify_with_vision_ocr(
    state: GraphState, file_path: str, total_pages: int, instructions: str
) -> GraphState:
    """Классификация документа через Gemini Vision OCR (для сканов)."""
    request_id = state['request_id']

    logger.info(f"Запуск OCR через Gemini Vision для {request_id}...")

    try:
        ocr_result = analyze_scanned_pdf(
            pdf_path=file_path,
            instructions=instructions,
            dpi=200,
            max_pages=10,
        )
    except Exception as e:
        logger.error(f"Vision OCR failed for {request_id}: {e}", exc_info=True)
        state['status'] = "error"
        state['error_message'] = f"OCR processing failed: {e}"
        return state

    if ocr_result.get("error"):
        logger.error(f"OCR error for {request_id}: {ocr_result['error']}")
        state['document_profile'] = DocumentProfile(
            document_type="Неизвестно",
            total_pages=total_pages,
            extraction_quality_score=0.0,
            key_metadata={
                "issue_date": "", "document_number": "", "authority": "",
                "note": f"OCR ошибка: {ocr_result['error']}"
            }
        )
        state['raw_extracted_texts'] = {"_ocr_failed": ocr_result.get('raw_text', '')}
        state['status'] = "document_profiled"
        return state

    # Сохраняем сырой текст из OCR
    state['raw_extracted_texts'] = {
        "_ocr_text": ocr_result.get('raw_text', ''),
        "_ocr_table_4_candidate": json.dumps(ocr_result.get('table_4_candidate'), ensure_ascii=False) if ocr_result.get('table_4_candidate') else "null",
        "_ocr_table_5_candidate": json.dumps(ocr_result.get('table_5_candidate'), ensure_ascii=False) if ocr_result.get('table_5_candidate') else "null",
    }

    # Сохраняем insights из OCR в raw_extracted_texts (как JSON строку)
    ocr_insights = ocr_result.get('insights', [])
    if ocr_insights:
        processed_insights = [
            {
                "title": ins.get("title", "Наблюдение"),
                "severity": ins.get("severity", "INFO"),
                "narrative": ins.get("description", ins.get("title", "")),
                "affected_tables": ins.get("affected_tables", ["Таблица 4", "Таблица 5"]),
            }
            for ins in ocr_insights
        ]
        state['raw_extracted_texts']['_ocr_pre_insights'] = json.dumps(processed_insights, ensure_ascii=False)

    # Заполняем профиль
    state['document_profile'] = DocumentProfile(
        document_type=ocr_result.get('document_type', "Неизвестно"),
        total_pages=ocr_result.get('total_pages', total_pages),
        extraction_quality_score=ocr_result.get('extraction_quality_score', 0.5),
        key_metadata=ocr_result.get('key_metadata', {
            "issue_date": "", "document_number": "", "authority": ""
        }),
    )

    state['status'] = "document_profiled"
    logger.info(
        f"DocumentAnalysisNode завершил OCR для {request_id}. "
        f"Тип: {state['document_profile'].document_type}, "
        f"Качество: {state['document_profile'].extraction_quality_score:.2f}"
    )

    # Если есть table_4 — логируем
    t4 = ocr_result.get('table_4_candidate')
    t5 = ocr_result.get('table_5_candidate')
    if t4:
        logger.info(f"OCR извлек Table 4: {json.dumps(t4, ensure_ascii=False)[:200]}")
    if t5:
        logger.info(f"OCR извлек Table 5: {json.dumps(t5, ensure_ascii=False)[:200]}")

    return state
