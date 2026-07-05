import logging
from langgraph.graph import StateGraph, END
from src.schemas.states import GraphState
from src.nodes.document_analysis_node import document_analysis_node
from src.nodes.insight_generation_node import insight_generation_node
from src.nodes.report_drafting_node import report_drafting_node
from src.nodes.report_finalization_node import report_finalization_node
from src.nodes.safety_node import safety_check_node

logger = logging.getLogger(__name__)


def check_analysis_validity(state: GraphState) -> str:
    """
    Решает, куда перейти после document_analysis_node.
    Возвращает имя следующего узла или END.
    """
    profile = state.get("document_profile")
    if not profile:
        logger.warning("Нет профиля документа. Завершение.")
        return END
    return "insight_generation"


def check_safety_status(state: GraphState) -> str:
    """
    Решает, перейти к финализации или повторить/остановиться
    на основе проверки безопасности.
    """
    max_retries = 2
    current_retries = state.get("safety_check_retries", 0)
    current_status = state.get("status")

    if current_status == "error":
        if current_retries < max_retries:
            logger.warning(
                f"Safety check не пройден. Повтор report_drafting. "
                f"Попытка {current_retries + 1}/{max_retries}."
            )
            state['safety_check_retries'] = current_retries + 1
            state['status'] = "retrying"
            state['error_message'] = "Safety check не пройден, повторяем черновик отчета."
            return "report_drafting"
        else:
            logger.error(f"Safety check не пройден после {max_retries} попыток. Остановка.")
            state['status'] = "error"
            state['error_message'] = (
                f"Генерация отчета прервана после {max_retries} попыток "
                f"из-за неудачной проверки безопасности."
            )
            return END

    logger.info("Safety check пройден. Переход к report_finalization.")
    return "report_finalization"


def create_graph_workflow() -> StateGraph:
    """
    Создает и компилирует LangGraph workflow для автоматизации оценки недвижимости.
    """
    workflow = StateGraph(GraphState)

    # Определяем узлы графа
    workflow.add_node("document_analysis", document_analysis_node)
    workflow.add_node("insight_generation", insight_generation_node)
    workflow.add_node("report_drafting", report_drafting_node)
    workflow.add_node("safety_check", safety_check_node)
    workflow.add_node("report_finalization", report_finalization_node)

    # Точка входа
    workflow.set_entry_point("document_analysis")

    # Условный переход после анализа документа
    workflow.add_conditional_edges(
        "document_analysis",
        check_analysis_validity,
        {
            "insight_generation": "insight_generation",
            END: END,
        },
    )

    # Линейные переходы
    workflow.add_edge("insight_generation", "report_drafting")
    workflow.add_edge("report_drafting", "safety_check")

    # Условный переход после проверки безопасности
    workflow.add_conditional_edges(
        "safety_check",
        check_safety_status,
        {
            "report_finalization": "report_finalization",
            "report_drafting": "report_drafting",
            END: END,
        },
    )

    # Финализация -> конец
    workflow.add_edge("report_finalization", END)

    # Компилируем граф
    app = workflow.compile()
    return app
