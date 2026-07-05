"""
Streamlit GUI для системы автоматизированной оценки недвижимости.

Запуск:
    streamlit run app.py
"""
import streamlit as st
import logging
import sys
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Настройка страницы — ДОЛЖНО БЫТЬ ПЕРВЫМ ВЫЗОВОМ STREAMLIT
st.set_page_config(
    page_title="AI Оценка Недвижимости",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.pipeline import run_valuation_pipeline, format_report_preview, extract_insights_for_edit
from src.ui.components import (
    render_header,
    render_sidebar,
    render_upload_section,
    render_progress,
    render_document_profile,
    render_insights,
    render_report_preview,
)


def main():
    """Основная функция приложения."""
    # Заголовок
    render_header()

    # Боковая панель
    settings = render_sidebar()
    instructions = settings["instructions"]

    # Инициализация состояния сессии
    if "pipeline_state" not in st.session_state:
        st.session_state.pipeline_state = None
    if "current_node" not in st.session_state:
        st.session_state.current_node = "idle"
    if "pipeline_status" not in st.session_state:
        st.session_state.pipeline_status = "idle"
    if "edited_insights" not in st.session_state:
        st.session_state.edited_insights = None
    if "report_generated" not in st.session_state:
        st.session_state.report_generated = False

    # Основной контент — две колонки
    col_left, col_right = st.columns([2, 3])

    with col_left:
        # 1. Загрузка PDF
        file_path = render_upload_section()

        # 2. Кнопка запуска анализа
        st.markdown("### 🚀 Запуск анализа")

        can_run = (
            file_path is not None
            and st.session_state.pipeline_status != "running"
        )

        if st.button(
            "Начать анализ",
            type="primary",
            disabled=not can_run,
            use_container_width=True,
        ):
            if not file_path:
                st.error("Загрузите PDF-документ перед запуском.")
            else:
                st.session_state.pipeline_status = "running"
                st.session_state.current_node = "document_analysis"
                st.session_state.report_generated = False
                st.session_state.edited_insights = None
                st.rerun()

        # 3. Индикатор прогресса (если запущено)
        if st.session_state.pipeline_status == "running":
            st.markdown("---")
            with st.spinner("Выполняется анализ документов..."):
                try:
                    result_state = run_valuation_pipeline(
                        file_path=file_path,
                        instructions=instructions,
                    )
                    st.session_state.pipeline_state = result_state
                    st.session_state.pipeline_status = result_state.get("status", "error")
                    st.session_state.current_node = "report_finalization"

                    # Извлекаем инсайты для редактирования
                    raw_insights = extract_insights_for_edit(result_state)
                    st.session_state.edited_insights = raw_insights

                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при выполнении пайплайна: {e}")
                    logger.exception("Pipeline execution failed")
                    st.session_state.pipeline_status = "error"
                    st.session_state.current_node = "error"

        # Отображаем прогресс
        if st.session_state.pipeline_status == "running":
            render_progress(st.session_state.current_node, st.session_state.pipeline_status)

    with col_right:
        state = st.session_state.pipeline_state

        if state is None:
            # Показываем приветствие
            st.markdown(
                """
                <div style="
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 1rem;
                    padding: 3rem;
                    text-align: center;
                ">
                    <h3 style="color: #f8fafc; margin: 0 0 1rem 0;">
                        Добро пожаловать в систему оценки недвижимости
                    </h3>
                    <p style="color: #94a3b8;">
                        Загрузите PDF-документ слева и нажмите «Начать анализ»,<br>
                        чтобы автоматически сформировать экспертный отчет.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            # Отображаем результаты
            status = state.get("status", "unknown")

            if status == "error":
                st.error(f"❌ Ошибка: {state.get('error_message', 'Неизвестная ошибка')}")
            elif status == "completed":
                # Профиль документа
                render_document_profile(state.get("document_profile"))

                # Инсайты с редактированием
                st.markdown("---")
                updated_insights = render_insights(
                    st.session_state.edited_insights or [],
                    key_prefix="edit",
                )
                st.session_state.edited_insights = updated_insights

                # Кнопка генерации финального отчёта
                st.markdown("---")
                st.markdown("### 📄 Финальный отчёт")

                if not st.session_state.report_generated:
                    if st.button("🔄 Сгенерировать отчёт с учётом правок", type="primary"):
                        st.session_state.report_generated = True
                        st.rerun()
                else:
                    # Показываем предпросмотр отчёта
                    report_md = format_report_preview(state)
                    render_report_preview(report_md)

                    # Очистка
                    if st.button("🔄 Новый анализ", type="secondary"):
                        st.session_state.pipeline_state = None
                        st.session_state.pipeline_status = "idle"
                        st.session_state.current_node = "idle"
                        st.session_state.edited_insights = None
                        st.session_state.report_generated = False
                        st.rerun()
            else:
                st.info(f"Статус: {status}")

    # Футер
    st.markdown("---")
    st.markdown(
        '<div class="footer">'
        "AI Report Generator v2.0 · Документный пайплайн · LangGraph + OpenRouter"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
