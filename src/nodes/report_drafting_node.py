import logging
import json
import os
import time
import requests
from typing import List, Optional
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from src.schemas.states import (
    GraphState,
    DocumentProfile,
    ValuationInsight,
    ReportSectionDraft,
    LandCharacteristicsTable4,
    PropertyImprovementsTable5,
)

load_dotenv()

logger = logging.getLogger(__name__)


class ReportSectionsDraftOutput(BaseModel):
    """
    Структурированный вывод от LLM для черновика отчета.
    """
    section_title: str = Field(description="Название раздела отчета (например, 'Описание объекта оценки')")
    introduction_context: str = Field(description="Вводная нормативная часть раздела")
    analysis_narrative: List[str] = Field(description="Аналитические тексты-описания характеристик объекта")
    methodology_justification: str = Field(
        description="Обоснование использования или отказа от подходов к оценке"
    )
    table_4_extracted: Optional[dict] = Field(
        default=None,
        description="Данные для Таблицы 4 'Характеристики земельного участка' (если применимо)"
    )
    table_5_extracted: Optional[dict] = Field(
        default=None,
        description="Данные для Таблицы 5 'Характеристики недвижимых улучшений' (если применимо)"
    )


def report_drafting_node(state: GraphState) -> GraphState:
    """
    Формирует черновик разделов отчета об оценке на основе профиля документа
    и выявленных рисков/инсайтов.

    Args:
        state: Текущее состояние графа.

    Returns:
        GraphState с заполненным report_sections_draft.
    """
    request_id = state.get('request_id', 'unknown_request')
    instructions = state.get('instructions', "")

    document_profile: Optional[DocumentProfile] = state.get('document_profile')
    analysis_insights: Optional[List[ValuationInsight]] = state.get('analysis_insights')
    raw_text_dict = state.get('raw_extracted_texts', {})

    if not document_profile:
        logger.error(f"Missing document_profile for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = "Cannot draft report: Missing document profile."
        return state

    logger.info(f"ReportDraftingNode начал обработку запроса: {request_id}")

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
            temperature=0.3,
            max_retries=0,
            model_kwargs={
                "extra_headers": {
                    "HTTP-Referer": "https://localhost",
                    "X-Title": "AI Report Generator - Drafting",
                }
            },
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
        state['status'] = "error"
        state['error_message'] = f"Failed to initialize LLM: {e}"
        return state

    # Формируем контекст профиля
    profile_str = (
        f"Тип документа: {document_profile.document_type}\n"
        f"Страниц: {document_profile.total_pages}\n"
        f"Качество распознавания: {document_profile.extraction_quality_score}\n"
        f"Метаданные: {json.dumps(document_profile.key_metadata, ensure_ascii=False, indent=2)}\n"
    )

    # Контекст инсайтов
    insights_str = ""
    if analysis_insights:
        insights_str = "\nВыявленные риски и наблюдения:\n"
        for ins in analysis_insights:
            insights_str += (
                f"- [{ins.severity}] {ins.title}\n"
                f"  {ins.narrative}\n"
                f"  Затрагивает: {', '.join(ins.affected_tables)}\n\n"
            )

    # OCR данные из raw_text_dict (если есть)
    ocr_table_4_str = raw_text_dict.get('_ocr_table_4_candidate', '')
    ocr_table_5_str = raw_text_dict.get('_ocr_table_5_candidate', '')
    ocr_table_context = ""
    if ocr_table_4_str and ocr_table_4_str != "null":
        ocr_table_context += "\nOCR-извлеченные данные для Таблицы 4 (Земельный участок):\n"
        ocr_table_context += ocr_table_4_str + "\n"
    if ocr_table_5_str and ocr_table_5_str != "null":
        ocr_table_context += "\nOCR-извлеченные данные для Таблицы 5 (Помещение/квартира):\n"
        ocr_table_context += ocr_table_5_str + "\n"

    # Сырой текст из документов (первые 3000 символов)
    text_context = ""
    if raw_text_dict:
        text_context = "\nФрагменты извлеченного текста:\n"
        for doc_name, text in raw_text_dict.items():
            # Пропускаем ключи с OCR-данными, они уже включены выше
            if doc_name.startswith("_ocr_"):
                continue
            text_context += f"--- {doc_name} ---\n{str(text)[:3000]}...\n"

    # Если есть OCR-текст — используем его как основной
    ocr_text = raw_text_dict.get('_ocr_text', '')
    if ocr_text and (not text_context.strip() or len(ocr_text) > len(str(text_context))):
        text_context = "\nOCR-извлеченный текст из документа:\n" + ocr_text[:4000]

    max_retries = 3
    base_delay = 2
    llm_raw_output_str = ""
    draft_output: Optional[ReportSectionsDraftOutput] = None

    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка {attempt + 1}/{max_retries} вызова LLM для формирования черновика отчета...")

            parser = JsonOutputParser(pydantic_object=ReportSectionsDraftOutput)
            prompt = PromptTemplate(
                template="""
Вы — профессиональный оценщик недвижимости (Республика Беларусь), составляющий отчет об оценке.
На основе предоставленных данных сформируйте черновик раздела «Описание объекта оценки».

Внимательно изучите:
1. Тип документа и его метаданные (дата, номер, орган выдачи).
2. Извлеченные фрагменты текста из документов.
3. Выявленные риски и наблюдения (Valuation Insights).

Сформируйте ответ строго в формате JSON со следующими полями:
- `section_title`: Название раздела (например, "Описание объекта оценки").
- `introduction_context`: Вводная часть — нормативные ссылки, цели оценки, дата оценки.
- `analysis_narrative`: Список аналитических текстов (по 1–3 предложения каждый) — описание местоположения, конструктивных характеристик, инженерного оборудования.
- `methodology_justification`: Обоснование выбора подходов к оценке (затратный, доходный, сравнительный) или отказа от них.
- `table_4_extracted`: Если в документах есть данные о земельном участке — словарь с полями: address, cadastral_number, area_ha, purpose_by_executive_committee, purpose_by_classifier, central_utilities, property_rights, right_holder_and_share, encumbrances_or_restrictions, building_inventory_number, cadastral_cost_per_sqm_usd, cadastral_valuation_date.
- `table_5_extracted`: Если в документах есть данные об улучшениях (квартира/помещение) — словарь с полями: name_and_purpose, year_built, actual_condition, total_floors, object_floor, finishing_level, total_area_sqm, snb_area_sqm, living_area_sqm, walls_material, partitions_material, floors_structure, windows_and_openings, flooring_material, balcony_or_loggia, engineering_equipment.

---
ПРОФИЛЬ ДОКУМЕНТА:
{profile_str}

ИНСАЙТЫ И РИСКИ:
{insights_str}

ТЕКСТ ДОКУМЕНТОВ:
{text_context}

ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:
{instructions}

{format_instructions}

Ответ должен быть строго валидным JSON без дополнительного текста.
""",
                input_variables=["profile_str", "insights_str", "text_context", "instructions"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            llm_response = llm.invoke(prompt.invoke({
                "profile_str": profile_str,
                "insights_str": insights_str,
                "text_context": text_context,
                "instructions": instructions,
            }))

            llm_raw_output_str = llm_response.content
            stripped_str = llm_raw_output_str.strip()

            if stripped_str.startswith("```json"):
                stripped_str = stripped_str.replace("```json", "", 1)
            if stripped_str.endswith("```"):
                stripped_str = stripped_str[::-1].replace("```", "", 1)[::-1]

            json_str = stripped_str.strip()
            parsed_data = json.loads(json_str)
            draft_output = ReportSectionsDraftOutput(**parsed_data)
            logger.info(f"LLM успешно сформировал черновик отчета для {request_id}.")
            break

        except (requests.exceptions.RequestException, TimeoutError) as e:
            logger.warning(f"Сетевой сбой на попытке {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                state['status'] = "error"
                state['error_message'] = f"LLM недоступен после {max_retries} попыток: {e}"
                return state

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Ошибка парсинга JSON на попытке {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                state['status'] = "error"
                state['error_message'] = f"Некорректный JSON от LLM: {e}"
                return state

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            state['status'] = "error"
            state['error_message'] = f"Ошибка при формировании черновика: {e}"
            return state

    if draft_output is None:
        state['status'] = "error"
        state['error_message'] = "Черновик отчета не был сформирован."
        return state

    # Собираем markdown-содержимое отчета
    md_lines = []
    md_lines.append(f"# {draft_output.section_title}\n")
    md_lines.append(f"{draft_output.introduction_context}\n")

    if draft_output.table_4_extracted:
        md_lines.append("## Таблица 4. Характеристики земельного участка\n")
        md_lines.append("| Поле | Значение |")
        md_lines.append("|------|----------|")
        for key, value in draft_output.table_4_extracted.items():
            if isinstance(value, list):
                value_str = ", ".join(str(v) for v in value)
            else:
                value_str = str(value) if value is not None else ""
            md_lines.append(f"| {key} | {value_str} |")
        md_lines.append("")

    if draft_output.table_5_extracted:
        md_lines.append("## Таблица 5. Характеристики недвижимых улучшений\n")
        md_lines.append("| Поле | Значение |")
        md_lines.append("|------|----------|")
        eng_eq = draft_output.table_5_extracted.pop("engineering_equipment", {})
        for key, value in draft_output.table_5_extracted.items():
            value_str = str(value) if value is not None else ""
            md_lines.append(f"| {key} | {value_str} |")
        if eng_eq:
            for k, v in eng_eq.items():
                md_lines.append(f"| Инженерное оборудование: {k} | {v} |")
        md_lines.append("")

    md_lines.append("## Аналитическое описание\n")
    for narrative in draft_output.analysis_narrative:
        md_lines.append(f"- {narrative}\n")

    if draft_output.methodology_justification:
        md_lines.append("## Обоснование подходов к оценке\n")
        md_lines.append(f"{draft_output.methodology_justification}\n")

    compiled_markdown = "\n".join(md_lines)

    # Создаём ReportSectionDraft
    report_section = ReportSectionDraft(
        section_title=draft_output.section_title,
        introduction_context=draft_output.introduction_context,
        analysis_narrative=draft_output.analysis_narrative,
        methodology_justification=draft_output.methodology_justification,
    )

    # Если LLM вернул данные для таблиц — заполняем структурированные модели
    if draft_output.table_4_extracted:
        try:
            report_section.table_4_extracted = LandCharacteristicsTable4(
                **draft_output.table_4_extracted
            )
        except Exception as e:
            logger.warning(f"Не удалось распарсить Таблицу 4: {e}")

    if draft_output.table_5_extracted:
        try:
            report_section.table_5_extracted = PropertyImprovementsTable5(
                **draft_output.table_5_extracted
            )
        except Exception as e:
            logger.warning(f"Не удалось распарсить Таблицу 5: {e}")

    state['report_sections_draft'] = report_section
    # Сохраняем скомпилированный markdown в raw_extracted_texts для финализации
    if state.get('raw_extracted_texts') is None:
        state['raw_extracted_texts'] = {}
    state['raw_extracted_texts']['_report_markdown'] = compiled_markdown
    state['status'] = "report_drafted"

    logger.info(f"ReportDraftingNode завершил работу для {request_id}.")
    return state
