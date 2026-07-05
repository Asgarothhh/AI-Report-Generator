"""
UI-компоненты для Streamlit GUI.
"""
import streamlit as st
import uuid
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


def render_header():
    """Отображает заголовок приложения."""
    st.markdown(
        """
        <style>
        .main-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            padding: 2rem;
            border-radius: 1rem;
            margin-bottom: 2rem;
            border: 1px solid #334155;
        }
        .main-header h1 {
            color: #f8fafc;
            margin: 0;
            font-size: 2rem;
            font-weight: 600;
        }
        .main-header p {
            color: #94a3b8;
            margin: 0.5rem 0 0 0;
            font-size: 1rem;
        }
        .stProgress > div > div > div > div {
            background-color: #3b82f6;
        }
        .insight-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 0.75rem;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }
        .insight-card h4 {
            color: #f8fafc;
            margin: 0 0 0.5rem 0;
        }
        .insight-card p {
            color: #cbd5e1;
            margin: 0;
            font-size: 0.9rem;
        }
        .badge {
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 0.5rem;
        }
        .badge-critical { background: #dc2626; color: #fef2f2; }
        .badge-warning { background: #d97706; color: #fffbeb; }
        .badge-info { background: #2563eb; color: #eff6ff; }
        .report-preview {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 0.75rem;
            padding: 2rem;
            margin-top: 1rem;
        }
        .report-preview h1, .report-preview h2, .report-preview h3 {
            color: #f8fafc;
        }
        .report-preview p, .report-preview li {
            color: #cbd5e1;
        }
        .report-preview table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            color: #cbd5e1;
        }
        .report-preview th, .report-preview td {
            border: 1px solid #334155;
            padding: 0.5rem 1rem;
            text-align: left;
        }
        .report-preview th {
            background: #0f172a;
            color: #f8fafc;
        }
        .upload-box {
            background: #1e293b;
            border: 2px dashed #475569;
            border-radius: 1rem;
            padding: 3rem;
            text-align: center;
            transition: border-color 0.2s;
        }
        .upload-box:hover {
            border-color: #3b82f6;
        }
        /* Footer */
        .footer {
            text-align: center;
            color: #475569;
            padding: 2rem;
            font-size: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="main-header">'
        '<h1>🏢 Система автоматизированной оценки недвижимости</h1>'
        "<p>Загрузите PDF-документы (ЕГРНИ, техпаспорт, акт осмотра) для анализа "
        "и формирования экспертного отчета</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_sidebar() -> Dict[str, Any]:
    """
    Отображает боковую панель с настройками.

    Returns:
        Словарь с настройками пользователя.
    """
    with st.sidebar:
        st.markdown("### ⚙️ Настройки")
        instructions = st.text_area(
            "Инструкции для анализа",
            placeholder="Например: Обратить особое внимание на обременения и охранные зоны",
            height=120,
        )
        st.markdown("---")
        st.markdown("### 📋 Статус системы")
        st.markdown("✅ OpenRouter API: подключён")
        st.markdown("✅ LangGraph: активен")
        st.markdown("---")
        st.markdown("### ℹ️ О системе")
        st.markdown(
            "Версия 2.0 · Документный пайплайн\n\n"
            "Поддерживаемые типы документов:\n"
            "- ЕГРНИ (земельный участок)\n"
            "- ЕГРНИ (изолированное помещение)\n"
            "- Технический паспорт\n"
            "- Акт осмотра оценщиком"
        )
    return {"instructions": instructions}


def render_upload_section() -> Optional[str]:
    """
    Отображает секцию загрузки PDF-файла.

    Returns:
        Путь к сохранённому файлу или None.
    """
    st.markdown("### 📤 Загрузка документов")

    uploaded_file = st.file_uploader(
        "Выберите PDF-документ",
        type=["pdf"],
        help="Загрузите выписку ЕГРНИ, техпаспорт или акт осмотра в формате PDF",
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        # Сохраняем загруженный файл
        import tempfile

        upload_dir = os.path.join("local_app_data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{uploaded_file.name}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"✅ Файл загружен: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} КБ)")
        return file_path

    # Fallback: если не загружен, показываем demo-файл или заглушку
    st.info("Загрузите PDF-документ для начала работы, или используйте тестовый режим.")
    use_demo = st.checkbox("Использовать тестовый PDF (демо)")
    if use_demo:
        # Пробуем найти любой PDF в директории uploads или данных
        demo_path = _find_demo_pdf()
        if demo_path:
            st.info(f"Используется демо-файл: {os.path.basename(demo_path)}")
            return demo_path
        else:
            st.warning("Демо-файл не найден. Загрузите свой PDF.")
    return None


def _find_demo_pdf() -> Optional[str]:
    """Ищет демо-файл PDF в проекте."""
    import glob
    candidates = glob.glob("local_app_data/**/*.pdf", recursive=True)
    candidates += glob.glob("data/**/*.pdf", recursive=True)
    candidates += glob.glob("*.pdf")
    return candidates[0] if candidates else None


def render_progress(current_node: str, status: str):
    """
    Отображает индикатор прогресса прохождения узлов графа.

    Args:
        current_node: Имя текущего узла.
        status: Статус выполнения.
    """
    st.markdown("### ⏳ Прогресс анализа")

    nodes = [
        ("document_analysis", "📄 Анализ документа", "Классификация и извлечение метаданных"),
        ("insight_generation", "🔍 Генерация инсайтов", "Поиск рисков и обременений"),
        ("report_drafting", "📝 Формирование отчета", "Сборка разделов отчета"),
        ("safety_check", "🛡️ Проверка безопасности", "Валидация контента"),
        ("report_finalization", "✅ Финализация", "Компоновка финального отчета"),
    ]

    completed_idx = -1
    for i, (node_id, _, _) in enumerate(nodes):
        if node_id == current_node:
            completed_idx = i
            break
        if status in ("completed", "report_finalized") and node_id == "report_finalization":
            completed_idx = len(nodes) - 1

    for i, (node_id, title, desc) in enumerate(nodes):
        if i < completed_idx:
            st.success(f"**{title}** — {desc}")
        elif i == completed_idx:
            with st.spinner(f"**{title}** — {desc}"):
                st.info(f"⏳ **{title}** — {desc}")
        else:
            st.markdown(f"⏸️ **{title}** — {desc}")

    # Общий прогресс-бар
    total = len(nodes)
    progress = min((completed_idx + 1) / total, 1.0) if completed_idx >= 0 else 0.0
    st.progress(progress)
    st.caption(f"Этап {min(completed_idx + 1, total)} из {total}")


def render_document_profile(profile) -> None:
    """
    Отображает профиль документа.

    Args:
        profile: DocumentProfile объект.
    """
    if not profile:
        st.info("Профиль документа ещё не сформирован.")
        return

    st.markdown("### 📋 Профиль документа")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Тип документа", profile.document_type)
    with col2:
        st.metric("Страниц", profile.total_pages)
    with col3:
        quality = profile.extraction_quality_score * 100
        st.metric("Качество распознавания", f"{quality:.0f}%")

    if profile.key_metadata:
        st.markdown("#### Метаданные")
        meta_df = {"Поле": list(profile.key_metadata.keys()), "Значение": list(profile.key_metadata.values())}
        st.dataframe(meta_df, width="stretch", hide_index=True)


def render_insights(insights: List[Dict[str, Any]], key_prefix: str = "insight") -> List[Dict[str, Any]]:
    """
    Отображает список инсайтов с возможностью редактирования.

    Args:
        insights: Список словарей с полями id, title, severity, narrative, affected_tables.
        key_prefix: Префикс для ключей Streamlit.

    Returns:
        Обновлённый список инсайтов (с учётом правок пользователя).
    """
    if not insights:
        st.info("Инсайты ещё не сгенерированы.")
        return insights

    st.markdown("### 🔍 Выявленные риски и наблюдения")
    st.caption("Вы можете отредактировать описание или уровень критичности перед финальным отчётом.")

    updated = []
    for i, ins in enumerate(insights):
        severity = ins.get("severity", "INFO")
        badge_class = {
            "CRITICAL": "badge-critical",
            "WARNING": "badge-warning",
            "INFO": "badge-info",
        }.get(severity, "badge-info")

        with st.container():
            st.markdown(
                f'<div class="insight-card">'
                f'<h4><span class="badge {badge_class}">{severity}</span> {ins.get("title", "Без названия")}</h4>'
                f"</div>",
                unsafe_allow_html=True,
            )

            col1, col2 = st.columns([3, 1])
            with col1:
                new_narrative = st.text_area(
                    "Описание",
                    value=ins.get("narrative", ""),
                    key=f"{key_prefix}_narrative_{i}",
                    height=80,
                )
            with col2:
                new_severity = st.selectbox(
                    "Критичность",
                    options=["INFO", "WARNING", "CRITICAL"],
                    index=["INFO", "WARNING", "CRITICAL"].index(severity),
                    key=f"{key_prefix}_severity_{i}",
                )

            updated.append({
                "id": ins.get("id", f"insight_{i}"),
                "title": ins.get("title", ""),
                "severity": new_severity,
                "narrative": new_narrative,
                "affected_tables": ins.get("affected_tables", []),
            })
            st.markdown("---")

    return updated


def render_report_preview(markdown_text: str) -> None:
    """
    Отображает предпросмотр отчета в формате Markdown.

    Args:
        markdown_text: Текст отчета в Markdown.
    """
    if not markdown_text:
        st.info("Отчет ещё не сгенерирован.")
        return

    st.markdown("### 📄 Предпросмотр отчета")
    with st.container():
        st.markdown(
            f'<div class="report-preview">{markdown_text}</div>',
            unsafe_allow_html=True,
        )

    st.download_button(
        label="📥 Скачать отчет (Markdown)",
        data=markdown_text,
        file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
    )
