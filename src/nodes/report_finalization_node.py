import logging
import os
import json
from datetime import datetime
from typing import Optional

from src.schemas.states import GraphState, ReportSectionDraft, ReportDraft

logger = logging.getLogger(__name__)


def report_finalization_node(state: GraphState) -> GraphState:
    """
    Финализирует отчет: собирает все разделы в единый Markdown-документ
    и сохраняет его в final_report.

    Args:
        state: Текущее состояние графа.

    Returns:
        GraphState с заполненным final_report.
    """
    request_id = state.get('request_id', 'unknown_request')
    report_section: Optional[ReportSectionDraft] = state.get('report_sections_draft')
    raw_texts = state.get('raw_extracted_texts', {})

    logger.info(f"ReportFinalizationNode начал обработку запроса: {request_id}")

    if not report_section:
        logger.error(f"Отсутствует report_sections_draft для {request_id}.")
        state['status'] = "error"
        state['error_message'] = "Cannot finalize report: Report sections draft is missing."
        return state

    try:
        # Используем готовый markdown из raw_extracted_texts, если есть
        compiled_md = raw_texts.get('_report_markdown', "")

        if not compiled_md:
            # Собираем markdown вручную из структуры
            md_lines = []
            md_lines.append(f"# {report_section.section_title}\n")
            md_lines.append(f"{report_section.introduction_context}\n")

            if report_section.table_4_extracted:
                md_lines.append("## Таблица 4. Характеристики земельного участка\n")
                md_lines.append("| Поле | Значение |")
                md_lines.append("|------|----------|")
                data = report_section.table_4_extracted.model_dump()
                for key, value in data.items():
                    if isinstance(value, list):
                        value_str = ", ".join(str(v) for v in value)
                    else:
                        value_str = str(value) if value is not None else ""
                    md_lines.append(f"| {key} | {value_str} |")
                md_lines.append("")

            if report_section.table_5_extracted:
                md_lines.append("## Таблица 5. Характеристики недвижимых улучшений\n")
                md_lines.append("| Поле | Значение |")
                md_lines.append("|------|----------|")
                data = report_section.table_5_extracted.model_dump()
                eng_eq = data.pop("engineering_equipment", {})
                for key, value in data.items():
                    value_str = str(value) if value is not None else ""
                    md_lines.append(f"| {key} | {value_str} |")
                if eng_eq and isinstance(eng_eq, dict):
                    for k, v in eng_eq.items():
                        md_lines.append(f"| Инженерное оборудование: {k} | {v} |")
                md_lines.append("")

            md_lines.append("## Аналитическое описание\n")
            for narrative in report_section.analysis_narrative:
                md_lines.append(f"- {narrative}\n")

            if report_section.methodology_justification:
                md_lines.append("## Обоснование подходов к оценке\n")
                md_lines.append(f"{report_section.methodology_justification}\n")

            compiled_md = "\n".join(md_lines)

        # Создаём ReportDraft
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_title = f"Отчет об оценке недвижимости от {timestamp}"

        final_report = ReportDraft(
            document_title=report_title,
            compiled_markdown=compiled_md,
            format_type="markdown",
            output_file_path=None,  # Будет задано при экспорте
        )

        state['final_report'] = final_report
        state['status'] = "completed"
        logger.info(f"ReportFinalizationNode завершил работу для {request_id}.")
        return state

    except Exception as e:
        logger.error(
            f"Критическая ошибка в ReportFinalizationNode для {request_id}: {e}",
            exc_info=True,
        )
        state['status'] = "error"
        state['error_message'] = f"Ошибка при финализации отчета: {e}"
        return state
