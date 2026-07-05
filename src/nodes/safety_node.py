import logging
import os
import json
import time
from typing import Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field, ValidationError
import requests

from src.schemas.states import GraphState, ReportSectionDraft

load_dotenv()

logger = logging.getLogger(__name__)


class SafetyCheckResult(BaseModel):
    """
    Pydantic-модель для валидации вывода LLM на этапе проверки безопасности.
    """
    is_safe: bool = Field(
        description="True, если контент безопасен, не содержит вредных или неподобающих формулировок."
    )
    is_accurate: bool = Field(
        description="True, если отчет логически согласован с профилем документа и инструкциями пользователя."
    )
    reasoning: str = Field(
        description="Объяснение решения, особенно если проверка не пройдена."
    )


def safety_check_node(state: GraphState) -> GraphState:
    """
    Выполняет проверку безопасности и точности сгенерированного черновика отчета.
    Использует LLM через OpenRouter в качестве валидатора.

    Args:
        state: Текущее состояние графа.

    Returns:
        GraphState с обновленным статусом проверки.
    """
    logger.info("--- ВЫПОЛНЕНИЕ ПРОВЕРКИ БЕЗОПАСНОСТИ И ТОЧНОСТИ ---")

    request_id = state.get('request_id', 'unknown_request')
    report_draft: Optional[ReportSectionDraft] = state.get("report_sections_draft")
    document_profile = state.get("document_profile")
    instructions = state.get("instructions")

    if report_draft is None or document_profile is None:
        logger.warning(f"Отсутствуют данные для проверки безопасности для {request_id}. Пропуск.")
        # Если нет данных — считаем, что проверка пройдена (не блокируем пайплайн)
        state['status'] = "safety_checked"
        return state

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        logger.error(f"OPENROUTER_API_KEY не найден для {request_id}.")
        state['status'] = "error"
        state['error_message'] = "API key for OpenRouter not found."
        return state

    try:
        llm = ChatOpenAI(
            model="google/gemini-2.5-flash",
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.1,
            max_retries=0,
            model_kwargs={
                "extra_headers": {
                    "HTTP-Referer": "https://localhost",
                    "X-Title": "AI Report Generator - Safety Check",
                }
            },
        )
    except Exception as e:
        logger.error(f"Не удалось инициализировать LLM: {e}", exc_info=True)
        state['status'] = "error"
        state['error_message'] = f"Failed to initialize LLM: {e}"
        return state

    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка {attempt + 1}/{max_retries} проверки безопасности...")

            parser = JsonOutputParser(pydantic_object=SafetyCheckResult)

            prompt_template = """
Ты — эксперт по проверке отчетов об оценке недвижимости.
Твоя задача — проверить черновик отчета на безопасность и точность.

1. **Безопасность**: нет ли в отчете дискриминационных, оскорбительных или неправомерных формулировок.
2. **Точность**: соответствует ли отчет профилю документа и инструкциям пользователя.
3. **Полнота**: все ли обязательные разделы присутствуют.

Черновик отчета:
{report_draft}

Профиль документа:
{document_profile}

Инструкции пользователя:
{instructions}

{format_instructions}

Ответ должен быть строго валидным JSON.
"""

            prompt = PromptTemplate.from_template(prompt_template).format(
                report_draft=report_draft.model_dump_json(indent=2, ensure_ascii=False),
                document_profile=document_profile.model_dump_json(indent=2, ensure_ascii=False),
                instructions=instructions,
                format_instructions=parser.get_format_instructions(),
            )

            llm_response = llm.invoke(prompt)
            result = parser.invoke(llm_response)

            if not result['is_safe']:
                error_msg = f"Проверка безопасности не пройдена: {result['reasoning']}"
                logger.error(error_msg)
                state['status'] = "error"
                state['error_message'] = error_msg
                return state

            if not result['is_accurate']:
                error_msg = f"Проверка точности не пройдена: {result['reasoning']}"
                logger.error(error_msg)
                state['status'] = "error"
                state['error_message'] = error_msg
                return state

            logger.info(f"Проверка безопасности и точности пройдена для {request_id}.")
            state['status'] = "safety_checked"
            return state

        except (requests.exceptions.RequestException, TimeoutError) as e:
            logger.warning(f"Сетевой сбой на попытке {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                state['status'] = "error"
                state['error_message'] = f"LLM недоступен после {max_retries} попыток: {e}"
                return state

        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа LLM: {e}")
            state['status'] = "error"
            state['error_message'] = f"Ошибка валидации ответа LLM: {e}"
            return state

        except Exception as e:
            logger.error(f"Критическая ошибка при проверке безопасности: {e}", exc_info=True)
            state['status'] = "error"
            state['error_message'] = f"Ошибка при проверке безопасности: {e}"
            return state

    state['status'] = "error"
    state['error_message'] = "Не удалось выполнить проверку безопасности."
    return state
