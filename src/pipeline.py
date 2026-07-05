"""
Сервис для запуска полного пайплайна оценки недвижимости.

Предоставляет функцию `run_valuation_pipeline`, которая:
1. Инициализирует граф LangGraph.
2. Запускает обработку PDF-документа.
3. Возвращает итоговое состояние со всеми результатами.
"""
import logging
import os
import uuid
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from src.graph.builder import create_graph_workflow
from src.schemas.states import GraphState, DocumentProfile, ValuationInsight, ReportDraft

load_dotenv()

logger = logging.getLogger(__name__)


def run_valuation_pipeline(
    file_path: str,
    instructions: str = "",
    request_id: Optional[str] = None,
) -> GraphState:
    """
    Запускает полный пайплайн оценки недвижимости на основе PDF-документа.

    Args:
        file_path: Путь к PDF-документу.
        instructions: Дополнительные инструкции пользователя.
        request_id: Уникальный ID запроса (генерируется автоматически, если не указан).

    Returns:
        Итоговое состояние графа (GraphState) со всеми результатами.
    """
    if not request_id:
        request_id = str(uuid.uuid4())

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    logger.info(f"Запуск пайплайна оценки для запроса {request_id}, файл: {file_path}")

    # Начальное состояние
    initial_state: GraphState = {
        "request_id": request_id,
        "file_path": file_path,
        "instructions": instructions,
        "document_profile": None,
        "raw_extracted_texts": None,
        "analysis_insights": None,
        "report_sections_draft": None,
        "final_report": None,
        "feedback_history": None,
        "status": "pending",
        "error_message": None,
        "safety_check_retries": 0,
    }

    # Создаём и запускаем граф
    try:
        app = create_graph_workflow()
        final_state = app.invoke(initial_state)
        logger.info(f"Пайплайн завершён для {request_id}. Статус: {final_state.get('status')}")
        return final_state
    except Exception as e:
        logger.error(f"Ошибка при выполнении пайплайна для {request_id}: {e}", exc_info=True)
        initial_state["status"] = "error"
        initial_state["error_message"] = f"Pipeline execution failed: {e}"
        return initial_state


def format_report_preview(state: GraphState) -> str:
    """
    Форматирует результат пайплайна для отображения в GUI.

    Args:
        state: Итоговое состояние графа.

    Returns:
        Markdown-текст для предпросмотра или сообщение об ошибке.
    """
    if state.get("status") == "error":
        return f"**Ошибка:** {state.get('error_message', 'Неизвестная ошибка')}"

    final_report: Optional[ReportDraft] = state.get("final_report")
    if final_report:
        return final_report.compiled_markdown

    # Если финального отчета нет — показываем что есть
    parts = []

    profile: Optional[DocumentProfile] = state.get("document_profile")
    if profile:
        parts.append(f"**Тип документа:** {profile.document_type}")
        parts.append(f"**Страниц:** {profile.total_pages}")
        parts.append(f"**Качество распознавания:** {profile.extraction_quality_score:.2f}")
        parts.append("")

    insights: Optional[list] = state.get("analysis_insights")
    if insights:
        parts.append("## Выявленные риски и наблюдения\n")
        for ins in insights:
            parts.append(f"- **[{ins.severity}]** {ins.title}")
            parts.append(f"  {ins.narrative}")
            parts.append("")

    return "\n".join(parts) if parts else "Нет данных для отображения."


def extract_insights_for_edit(state: GraphState) -> list:
    """
    Извлекает список инсайтов для редактирования в GUI.

    Args:
        state: Состояние графа.

    Returns:
        Список словарей с данными инсайтов.
    """
    insights: Optional[list] = state.get("analysis_insights", [])
    if not insights:
        return []
    return [
        {
            "id": ins.insight_id,
            "title": ins.title,
            "severity": ins.severity,
            "narrative": ins.narrative,
            "affected_tables": ins.affected_tables,
        }
        for ins in insights
    ]
