"""
Узел визуализации данных для отчета об оценке недвижимости.
В текущей версии пайплайна не используется (зарезервирован для будущих расширений).
"""
import logging
import json
import os
from typing import List, Optional
from pydantic import BaseModel, Field
from src.schemas.states import GraphState

logger = logging.getLogger(__name__)


class GeneratedVisual(BaseModel):
    """Модель сгенерированной визуализации."""
    visual_id: str
    type: str
    description: str
    file_path: str
    suggested_section: str = "Analysis"
    chart_code: str = ""


def visualization_node(state: GraphState) -> GraphState:
    """
    Заглушка для узла визуализации.
    В текущей версии графа не используется (расчет на основе документов,
    а не датафреймов). Возвращает состояние без изменений.

    Args:
        state: Текущее состояние графа.

    Returns:
        GraphState без изменений.
    """
    request_id = state.get('request_id', 'unknown_request')
    logger.info(f"VisualizationNode: пропуск (не используется в документном пайплайне) для {request_id}")
    return state
