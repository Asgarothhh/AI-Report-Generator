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

from src.schemas.states import GraphState, ValuationInsight, DocumentProfile


load_dotenv()

logger = logging.getLogger(__name__)


class GeneratedInsightsOutput(BaseModel):
    """
    Обертка для списка инсайтов (рисков/наблюдений), 
    ожидаемая от LLM при структурированном парсинге.
    """
    insights: List[ValuationInsight] = Field(
        description="Список ключевых наблюдений, расхождений или рисков, выявленных при анализе документов."
    )


def insight_generation_node(state: GraphState) -> GraphState:
    """
    Генерирует аналитические выводы (Valuation Insights) на основе профиля 
    документа и инструкций. Выявляет юридические обременения, технические 
    расхождения и риски для Таблицы 4 и Таблицы 5.
    """
    request_id = state.get('request_id', 'unknown_request')
    instructions = state.get('instructions', "")
    
    # Получаем профиль документа, созданный на предыдущем шаге
    document_profile: Optional[DocumentProfile] = state.get('document_profile')
    
    # Если в стейте есть сырой текст (извлекаемый на других этапах), берем и его для контекста
    raw_text_dict = state.get('raw_extracted_texts', {})

    if not document_profile:
        logger.error(f"Missing document profile for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = "Cannot generate valuation insights: Missing document profile in state."
        return state

    logger.info(f"InsightGenerationNode processing request: {request_id}")

    # Проверяем, есть ли пред-инсайты от OCR (из сканированных PDF)
    ocr_pre_insights_json = raw_text_dict.get('_ocr_pre_insights', '')
    ocr_pre_insights = json.loads(ocr_pre_insights_json) if ocr_pre_insights_json else []
    if ocr_pre_insights:
        logger.info(f"Found {len(ocr_pre_insights)} OCR pre-insights, using them directly.")
        from src.schemas.states import ValuationInsight
        generated_insights = []
        for i, ins in enumerate(ocr_pre_insights):
            insight = ValuationInsight(
                insight_id=f"ocr_insight_{i}",
                title=ins.get("title", "Наблюдение"),
                severity=ins.get("severity", "INFO"),
                narrative=ins.get("narrative", ins.get("description", "")),
                affected_tables=ins.get("affected_tables", []),
            )
            generated_insights.append(insight)
        state['analysis_insights'] = generated_insights
        state['status'] = "insights_generated"
        logger.info(f"InsightGenerationNode completed for request: {request_id}. Used {len(generated_insights)} OCR pre-insights.")
        return state

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        logger.error(f"OPENROUTER_API_KEY not found for request {request_id}.")
        state['status'] = "error"
        state['error_message'] = "API key for OpenRouter not found. Please set OPENROUTER_API_KEY in your .env file."
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
                    "X-Title": "LangGraph Report Generator"
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM for insight generation: {e}", exc_info=True)
        state['status'] = "error"
        state['error_message'] = f"Failed to initialize LLM for insight generation: {e}"
        return state

    # Подготавливаем контекст профиля для модели
    profile_summary = (
        f"Тип документа: {document_profile.document_type}\n"
        f"Количество страниц: {document_profile.total_pages}\n"
        f"Качество распознавания: {document_profile.extraction_quality_score}\n"
        f"Метаданные: {json.dumps(document_profile.key_metadata, ensure_ascii=False)}\n"
    )

    # Если есть извлеченные тексты, добавляем первые 2000 символов для контекста
    text_context = ""
    if raw_text_dict:
        text_context = "\nФрагменты сырого текста из документов:\n"
        for doc_name, text in raw_text_dict.items():
            text_context += f"--- {doc_name} ---\n{str(text)[:2000]}...\n"

    max_retries = 3
    base_delay = 2  
    llm_raw_output_str = ""
    generated_insights: List[ValuationInsight] = []

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries} to invoke LLM for insight generation...")

            parser = JsonOutputParser(pydantic_object=GeneratedInsightsOutput)
            prompt = PromptTemplate(
                template="""
                Вы — профессиональный аудитор и оценщик недвижимости (Республика Беларусь).
                Ваша задача — проанализировать профиль документа и выявить юридические или технические риски (Valuation Insights),
                которые могут повлиять на рыночную стоимость или формирование Таблицы 4 (Земельный участок) и Таблицы 5 (Улучшения).
                
                Ищите следующие проблемы:
                - Наличие обременений (ипотека, арест, охранные зоны историко-культурных ценностей, линии электропередач).
                - Расхождения или странности в площади или этажности.
                - Отсутствие критических данных (например, не указано целевое назначение).
                - Ответы на специфические вопросы, указанные в инструкциях пользователя.
                
                Для каждого инсайта предоставьте:
                - `insight_id`: Уникальный ID (например, 'encumbrance_1', 'area_mismatch').
                - `title`: Краткое понятное название риска.
                - `severity`: Строго одно из значений: 'INFO', 'WARNING', 'CRITICAL'. (Обременения — это минимум WARNING).
                - `narrative`: Подробное описание наблюдения на основе переданных данных.
                - `affected_tables`: Список таблиц, на которые это влияет (допустимые значения: "Таблица 4", "Таблица 5", "Обе").
                
                --- ПРОФИЛЬ ДОКУМЕНТА ---
                {profile_summary}
                
                --- ДОПОЛНИТЕЛЬНЫЙ ТЕКСТ (если есть) ---
                {text_context}
                
                --- ИНСТРУКЦИИ ЗАКАЗЧИКА ---
                {instructions}
                
                Сгенерируйте от 1 до 5 наиболее важных инсайтов. Если рисков нет, сгенерируйте один инсайт с severity 'INFO', подтверждающий чистоту документа.
                
                {format_instructions}
                
                Ответ должен быть строго валидным JSON.
                """,
                input_variables=["profile_summary", "text_context", "instructions"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            llm_response = llm.invoke(prompt.invoke({
                "profile_summary": profile_summary,
                "text_context": text_context,
                "instructions": instructions
            }))
            
            llm_raw_output_str = llm_response.content
            stripped_str = llm_raw_output_str.strip()

            # Очистка JSON от маркдаун-тегов
            if stripped_str.startswith("```json"):
                stripped_str = stripped_str.replace("```json", "", 1)
            if stripped_str.endswith("```"):
                stripped_str = stripped_str[::-1].replace("```", "", 1)[::-1]
            json_str = stripped_str.strip()

            parsed_data = json.loads(json_str)
            parsed_insights_output = GeneratedInsightsOutput(**parsed_data)
            
            generated_insights = parsed_insights_output.insights
            logger.info(f"DEBUG: LLM returned {len(generated_insights)} valuation insights.")
            break

        except (requests.exceptions.RequestException, TimeoutError) as e:
            logger.warning(f"LLM call failed on attempt {attempt + 1}/{max_retries} due to network/timeout: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying LLM call for request {request_id} in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"Max retries reached. LLM call failed for request {request_id}.")
                state['status'] = "error"
                state['error_message'] = f"Failed to get a response from the LLM after {max_retries} attempts: {e}"
                return state

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Error parsing LLM JSON for insights for request {request_id}: {e}", exc_info=True)
            logger.debug(f"Raw LLM Output: {llm_raw_output_str}")
            if attempt == max_retries - 1:
                state['status'] = "error"
                state['error_message'] = f"LLM output for insights was invalid JSON or schema: {e}."
                return state

        except Exception as e:
            logger.error(f"An unexpected error occurred during LLM call for insight generation: {e}", exc_info=True)
            state['status'] = "error"
            state['error_message'] = f"An unexpected error occurred during insight generation LLM call: {e}"
            return state

    if generated_insights:
        state['analysis_insights'] = generated_insights
        state['status'] = "insights_generated"
        logger.info(f"InsightGenerationNode completed for request: {request_id}. Generated {len(generated_insights)} valuation insights.")
    else:
        state['status'] = "error"
        state['error_message'] = "An unexpected failure occurred: no insights were generated after all LLM retries."

    return state
