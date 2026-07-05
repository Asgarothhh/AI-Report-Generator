# Техническая документация: AI Report Generator

> **Версия:** 2.0  
> **Статус:** Release  
> **Дата:** 2026  
> **Репозиторий:** https://github.com/Asgarothhh/AI-Report-Generator

---

## 1. Описание проекта

**AI Report Generator** — это автоматизированная система оценки недвижимости (Республика Беларусь), которая принимает на вход PDF-документы (выписки ЕГРНИ, технические паспорта, акты осмотра), анализирует их с помощью LLM (Large Language Model) через OpenRouter и формирует структурированный экспертный отчет об оценке.

### 1.1. Цель

Полностью автоматизировать процесс первичного анализа документов и составления черновика отчета об оценке недвижимости, сократив время оценщика с часов до минут. Система не заменяет оценщика, а выступает в роли ассистента: она классифицирует документы, выявляет юридические риски и технические расхождения, формирует структурированный черновик отчета, который человек может отредактировать перед финализацией.

### 1.2. Применение

- **Оценочные компании** — для ускорения подготовки отчетов об оценке квартир, жилых домов, земельных участков.
- **Кадастровые инженеры** — для кросс-проверки данных из разных источников (ЕГРНИ, техпаспорт, акт осмотра).
- **Банки (ипотечные отделы)** — для экспресс-проверки документов при выдаче кредита.

### 1.3. Поддерживаемые типы документов

| Тип документа | Описание |
|---------------|----------|
| `ЕГРНИ_Земля` | Выписка из государственного реестра недвижимости на земельный участок |
| `ЕГРНИ_Помещение` | Выписка из государственного реестра недвижимости на изолированное помещение/квартиру |
| `Техпаспорт` | Технический паспорт на капитальное строение |
| `Акт_Осмотра` | Акт осмотра, составленный оценщиком |
| `Неизвестно` | Fallback-классификация для нераспознанных или сканированных документов |

---

## 2. Архитектура системы

### 2.1. Общая схема

```
┌──────────────────────────────────────────────────────────────┐
│                    Streamlit GUI (app.py)                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Загрузка   │→│ Прогресс     │→│ Результаты + Отчёт   │  │
│  │ PDF        │  │ выполнения   │  │ + Редактирование     │  │
│  └────────────┘  └──────────────┘  └──────────────────────┘  │
└────────────────────────────┬─────────────────────────────────┘
                             │
                      ┌──────▼──────┐
                      │  pipeline   │
                      │  .py        │
                      └──────┬──────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                  LangGraph Workflow (StateGraph)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │Document  │→│Insight   │→│Report    │→│Safety    │   │
│  │Analysis  │  │Generation│  │Drafting  │  │Check     │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘   │
│                      │                                       │
│                      └──────────► Report Finalization ──► END│
└──────────────────────────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  OpenRouter API  │
                    │  (Gemini 2.5    │
                    │   Flash)        │
                    └─────────────────┘
```

### 2.2. Технологический стек

| Компонент | Технология |
|-----------|------------|
| **Язык** | Python 3.11+ |
| **UI / GUI** | Streamlit 1.35+ |
| **Оркестрация** | LangGraph 0.2+ (StateGraph) |
| **LLM** | OpenRouter API (Google Gemini 2.5 Flash) через `langchain-openai` |
| **Валидация данных** | Pydantic v2 |
| **Парсинг PDF** | PyPDF 4+ |
| **Среда выполнения** | Локальная (Windows) |

### 2.3. Структура директорий

```
AI-Report-Generator/
├── app.py                          # Streamlit entry point (GUI)
├── .env                            # API-ключи (OPENROUTER_API_KEY)
├── requirements.txt                # Зависимости
├── README.md                       # Описание проекта
├── TECHNICAL_DOCUMENTATION.md      # Документация (данный файл)
│
├── src/
│   ├── pipeline.py                 # Сервис запуска пайплайна
│   │
│   ├── graph/
│   │   ├── __init__.py             # Экспорты
│   │   └── builder.py              # Построитель графа LangGraph
│   │
│   ├── nodes/
│   │   ├── __init__.py             # Экспорты всех узлов
│   │   ├── document_analysis_node.py   # Узел 1: Анализ документа
│   │   ├── insight_generation_node.py  # Узел 2: Генерация инсайтов
│   │   ├── report_drafting_node.py     # Узел 3: Черновик отчета
│   │   ├── safety_node.py              # Узел 4: Проверка безопасности
│   │   ├── report_finalization_node.py # Узел 5: Финализация отчета
│   │   └── visualization_node.py       # Узел 6: Визуализация (заглушка)
│   │
│   ├── schemas/
│   │   ├── __init__.py             # Экспорты всех схем
│   │   └── states.py               # Pydantic-модели и GraphState
│   │
│   └── ui/
│       └── components.py           # Streamlit UI-компоненты
│
└── local_app_data/
    └── uploads/                    # Загруженные пользователем PDF
```

---

## 3. Core-компоненты

### 3.1. Схемы данных — `src/schemas/states.py`

Определяет все Pydantic-модели и тип состояния графа `GraphState`. Это ядро контракта между узлами.

#### 3.1.1. `DocumentProfile`

Профиль документа после первичного анализа.

| Поле | Тип | Описание |
|------|-----|----------|
| `document_type` | `str` | Тип документа (ЕГРНИ_Земля, ЕГРНИ_Помещение, Техпаспорт, Акт_Осмотра, Неизвестно) |
| `total_pages` | `int` | Количество страниц |
| `extraction_quality_score` | `float` | Оценка качества распознавания (0.0–1.0) |
| `key_metadata` | `Dict[str, Any]` | Базовые метаданные (issue_date, document_number, authority) |

#### 3.1.2. `LandCharacteristicsTable4` (Таблица 4)

Характеристики земельного участка для отчета (стр. 23). Содержит 12 полей: адрес, кадастровый номер, площадь в га, целевое назначение, имущественные права, обременения, кадастровая стоимость и др.

#### 3.1.3. `PropertyImprovementsTable5` (Таблица 5)

Характеристики недвижимых улучшений (стр. 24–25). Содержит 16+ полей: наименование, год постройки, этажность, площадь, материалы стен, инженерное оборудование и др.

#### 3.1.4. `ValuationInsight`

Критическое наблюдение/риск, выявленный при кросс-проверке.

| Поле | Тип | Описание |
|------|-----|----------|
| `insight_id` | `str` | Уникальный ID (encumbrance_1, area_mismatch и т.д.) |
| `title` | `str` | Краткое название |
| `severity` | `str` | INFO / WARNING / CRITICAL |
| `narrative` | `str` | Подробное описание расхождения |
| `affected_tables` | `List[str]` | Затрагиваемые таблицы (Таблица 4, Таблица 5, Обе) |

#### 3.1.5. `ReportSectionDraft`

Черновик раздела отчета.

| Поле | Тип | Описание |
|------|-----|----------|
| `section_title` | `str` | Название раздела |
| `introduction_context` | `str` | Вводная/нормативная часть |
| `table_4_extracted` | `Optional[LandCharacteristicsTable4]` | Данные таблицы 4 |
| `table_5_extracted` | `Optional[PropertyImprovementsTable5]` | Данные таблицы 5 |
| `analysis_narrative` | `List[str]` | Аналитические тексты |
| `methodology_justification` | `Optional[str]` | Обоснование подходов к оценке |

#### 3.1.6. `ReportDraft`

Финальный отчет.

| Поле | Тип | Описание |
|------|-----|----------|
| `document_title` | `str` | Название отчета |
| `compiled_markdown` | `str` | Полный текст отчета в Markdown |
| `format_type` | `str` | Целевой формат (DOCX, PDF) |
| `output_file_path` | `Optional[str]` | Путь к сгенерированному файлу |

#### 3.1.7. `UserFeedback`

Правка от оценщика-верификатора.

| Поле | Тип | Описание |
|------|-----|----------|
| `feedback_id` | `str` | ID правки |
| `target_table` | `str` | Какая таблица правится |
| `target_field` | `str` | Какое поле правится |
| `corrected_value` | `Any` | Новое значение |
| `comment` | `Optional[str]` | Причина правки |
| `timestamp` | `datetime` | Время правки |

#### 3.1.8. `GraphState` (TypedDict)

Состояние графа — основной контракт между узлами LangGraph.

```python
class GraphState(TypedDict):
    request_id: str               # Уникальный ID запроса
    file_path: str                # Путь к загруженному файлу
    instructions: str             # Инструкции пользователя
    document_profile: Optional[DocumentProfile]
    raw_extracted_texts: Optional[Dict[str, str]]
    analysis_insights: Optional[List[ValuationInsight]]
    report_sections_draft: Optional[ReportSectionDraft]
    final_report: Optional[ReportDraft]
    feedback_history: Optional[List[UserFeedback]]
    status: str                   # pending / document_profiled / insights_generated / report_drafted / safety_checked / completed / error / retrying
    error_message: Optional[str]
    safety_check_retries: int
```

---

### 3.2. Граф LangGraph — `src/graph/builder.py`

#### 3.2.1. Узлы графа

| Имя узла | Функция | Назначение |
|----------|---------|------------|
| `document_analysis` | `document_analysis_node` | Читает PDF, классифицирует тип документа, извлекает метаданные |
| `insight_generation` | `insight_generation_node` | Анализирует документ на предмет рисков и юридических обременений |
| `report_drafting` | `report_drafting_node` | Формирует черновик отчета с таблицами 4 и 5 |
| `safety_check` | `safety_check_node` | Проверяет отчет на безопасность и точность |
| `report_finalization` | `report_finalization_node` | Компилирует финальный Markdown-документ |

#### 3.2.2. Условные переходы

1. **После `document_analysis`** — функция `check_analysis_validity`:
   - Если `document_profile` не создан → переход на `END`
   - Иначе → переход на `insight_generation`

2. **После `safety_check`** — функция `check_safety_status`:
   - Если статус `"error"` и число ретраев < 2 → повтор `report_drafting`
   - Если статус `"error"` и ретраи исчерпаны → `END` (аварийная остановка)
   - Если проверка пройдена → переход на `report_finalization`

#### 3.2.3. Граф переходов

```
document_analysis ──► [check_analysis_validity]
    ├── (есть profile) ──► insight_generation ──► report_drafting ──► safety_check
    └── (нет profile) ──► END

safety_check ──► [check_safety_status]
    ├── (safe) ──► report_finalization ──► END
    ├── (error, retries < 2) ──► report_drafting (retry)
    └── (error, retries >= 2) ──► END
```

---

### 3.3. Узлы пайплайна

#### 3.3.1. `document_analysis_node` — Анализ документа

**Вход:** `GraphState` с `file_path`  
**Выход:** `GraphState` с заполненным `document_profile` и `raw_extracted_texts`

**Алгоритм:**

1. Проверяет наличие файла и API-ключа OpenRouter.
2. Инициализирует `ChatOpenAI` с моделью `google/gemini-2.5-flash` через OpenRouter.
3. Читает PDF через `pypdf.PdfReader`, извлекает текст со всех страниц (до 8 страниц).
4. Если текст отсутствует (скан) — создаёт fallback-профиль с `extraction_quality_score = 0.0` и завершается.
5. Отправляет текст в LLM с промптом, который просит классифицировать документ (тип, качество, метаданные).
6. Обрабатывает ответ: очищает от Markdown-тегов, парсит JSON.
7. **Retry-логика:** 3 попытки с exponential backoff (2s, 4s, 8s) при сетевых ошибках.
8. При некорректном JSON после всех попыток — создаёт fallback-профиль.

**Ключевой промпт:** Просит LLM определить `document_type` (строго из заданного набора), оценить качество текста, извлечь метаданные и дать summary-наблюдение.

#### 3.3.2. `insight_generation_node` — Генерация инсайтов

**Вход:** `GraphState` с `document_profile` и `raw_extracted_texts`  
**Выход:** `GraphState` с `analysis_insights: List[ValuationInsight]`

**Алгоритм:**

1. Проверяет наличие профиля документа.
2. Инициализирует LLM через OpenRouter.
3. Формирует контекст: профиль документа + фрагменты сырого текста (до 2000 символов на документ).
4. Запрашивает у LLM от 1 до 5 инсайтов (рисков, расхождений, обременений).
5. Каждый инсайт содержит: `insight_id`, `title`, `severity`, `narrative`, `affected_tables`.
6. При отсутствии рисков LLM должна вернуть один инсайт с `severity = INFO`, подтверждающий чистоту документа.
7. Retry-логика: 3 попытки, exponential backoff.

**Типы выявляемых проблем:**
- Обременения (ипотека, арест, охранные зоны)
- Расхождения площади или этажности
- Отсутствие критических данных
- Специфические вопросы из инструкций пользователя

#### 3.3.3. `report_drafting_node` — Черновик отчета

**Вход:** `GraphState` с `document_profile`, `analysis_insights`, `raw_extracted_texts`  
**Выход:** `GraphState` с `report_sections_draft: ReportSectionDraft`

**Алгоритм:**

1. Собирает полный контекст: профиль, инсайты, фрагменты текста (до 3000 символов).
2. Запрашивает у LLM структурированный JSON с следующими полями:
   - `section_title` — название раздела
   - `introduction_context` — нормативная вводная часть
   - `analysis_narrative` — список аналитических текстов
   - `methodology_justification` — обоснование подходов к оценке
   - `table_4_extracted` — данные для Таблицы 4 (если применимо)
   - `table_5_extracted` — данные для Таблицы 5 (если применимо)
3. Парсит ответ: если LLM вернул данные для таблиц — создаёт строго типизированные объекты `LandCharacteristicsTable4` / `PropertyImprovementsTable5`.
4. Компилирует Markdown-строку из всех разделов.
5. Сохраняет скомпилированный Markdown в `raw_extracted_texts["_report_markdown"]` для финализации.
6. Retry-логика: 3 попытки, exponential backoff.

#### 3.3.4. `safety_node` — Проверка безопасности

**Вход:** `GraphState` с `report_sections_draft` и `document_profile`  
**Выход:** `GraphState` с обновлённым `status` (`"safety_checked"` или `"error"`)

**Алгоритм:**

1. Инициализирует LLM с низкой температурой (0.1) для детерминированности.
2. Запрашивает у LLM три проверки:
   - **`is_safe`**: нет ли дискриминационных, оскорбительных или неправомерных формулировок
   - **`is_accurate`**: соответствует ли отчет профилю документа и инструкциям
   - **`reasoning`**: объяснение решения
3. Если любая проверка не пройдена — выставляет `status = "error"` с описанием.
4. Если данные отсутствуют — пропускает проверку (не блокирует пайплайн).
5. Retry-логика: 3 попытки.

**Роль в графе:** Является **gatekeeper** — при ошибке граф может вернуться на `report_drafting` для повторной генерации (до 2 ретраев).

#### 3.3.5. `report_finalization_node` — Финализация отчета

**Вход:** `GraphState` с `report_sections_draft`  
**Выход:** `GraphState` с `final_report: ReportDraft` и `status = "completed"`

**Алгоритм:**

1. Проверяет наличие `report_sections_draft`.
2. Использует готовый Markdown из `raw_extracted_texts["_report_markdown"]` (если есть).
3. Если Markdown отсутствует — собирает вручную из структуры `ReportSectionDraft`:
   - Заголовок и вводная часть
   - Таблица 4 (если есть)
   - Таблица 5 (если есть)
   - Аналитические тексты
   - Обоснование подходов к оценке
4. Создаёт `ReportDraft` с заполненным `compiled_markdown`.
5. Устанавливает `status = "completed"`.

#### 3.3.6. `visualization_node` — Визуализация (заглушка)

Зарезервированный узел для будущего расширения. В текущей версии не используется — возвращает состояние без изменений.

---

### 3.4. Пайплайн — `src/pipeline.py`

#### 3.4.1. `run_valuation_pipeline(file_path, instructions, request_id)`

**Назначение:** Точка входа для запуска полного пайплайна.

**Алгоритм:**
1. Генерирует `request_id` (UUID), если не передан.
2. Проверяет существование файла.
3. Создаёт начальное состояние графа (`GraphState`).
4. Создаёт граф через `create_graph_workflow()`.
5. Запускает граф через `app.invoke(initial_state)`.
6. При ошибке — возвращает состояние с `status = "error"` и описанием.

**Функции-хелперы:**
- `format_report_preview(state)` — форматирует результаты для GUI (Markdown или сообщение об ошибке)
- `extract_insights_for_edit(state)` — извлекает инсайты как список словарей для редактора в GUI

---

### 3.5. Streamlit GUI — `app.py` + `src/ui/components.py`

#### 3.5.1. `app.py` — Основной цикл

**Поток выполнения:**

1. **Инициализация:** Настройка страницы (`st.set_page_config`), логгирование.
2. **Заголовок** — `render_header()` (кастомный CSS + стилизованный блок).
3. **Боковая панель** — `render_sidebar()` (инструкции пользователя, статус системы).
4. **Инициализация сессии:** `pipeline_state`, `current_node`, `pipeline_status`, `edited_insights`, `report_generated`.
5. **Две колонки:**
   - **Левая (2/5):**
     - `render_upload_section()` — загрузка PDF с опцией демо-режима
     - Кнопка "Начать анализ"
     - `render_progress()` — индикатор выполнения узлов графа
   - **Правая (3/5):**
     - Приветственный экран (если анализ ещё не запущен)
     - Профиль документа (`render_document_profile`)
     - Редактируемые инсайты (`render_insights`)
     - Кнопка генерации финального отчёта
     - Предпросмотр отчета (`render_report_preview`) с кнопкой скачивания
6. **Футер.**

**Управление состоянием сессии:**
- `pipeline_state` — последнее состояние графа
- `current_node` — имя текущего узла (для индикатора прогресса)
- `pipeline_status` — `"idle"` / `"running"` / `"completed"` / `"error"`
- `edited_insights` — инсайты после редактирования пользователем
- `report_generated` — флаг, что финальный отчёт сгенерирован с учётом правок

#### 3.5.2. `src/ui/components.py` — UI-компоненты

| Функция | Назначение |
|---------|------------|
| `render_header()` | Заголовок с CSS-стилями (тёмная тема, градиент, badge-классы) |
| `render_sidebar()` | Боковая панель с инструкциями и информацией о системе |
| `render_upload_section()` | Загрузка PDF + опция демо-режима (поиск локальных PDF) |
| `render_progress(current_node, status)` | Индикатор прогресса: 5 этапов с иконками, статусами и прогресс-баром |
| `render_document_profile(profile)` | Метрики типа документа, страниц, качества распознавания + таблица метаданных |
| `render_insights(insights, key_prefix)` | Список инсайтов с возможностью редактирования (textarea для описания, select для severity) |
| `render_report_preview(markdown_text)` | HTML-предпросмотр отчёта + кнопка скачивания |

**Дизайн:** Тёмная тема (background: `#0f172a`, `#1e293b`), синие акценты (`#3b82f6`), кастомные badge-стили для severity (`badge-critical` — красный, `badge-warning` — жёлтый, `badge-info` — синий).

---

## 4. Поток данных

### 4.1. Полный цикл обработки

```
1. [GUI] Загрузка PDF → file_path
2. [GUI] Кнопка "Начать анализ" → st.session_state.pipeline_status = "running"
3. [Pipeline] run_valuation_pipeline(file_path, instructions)
    a. Создание начального GraphState
    b. Создание графа (create_graph_workflow)
    c. Запуск графа (app.invoke)
4. [Node] document_analysis_node
    a. Чтение PDF, извлечение текста
    b. LLM → классификация документа
    c. → document_profile, raw_extracted_texts
5. [Edge] check_analysis_validity
    a. Если profile есть → insight_generation
    b. Если profile нет → END (error)
6. [Node] insight_generation_node
    a. LLM → выявление рисков
    b. → analysis_insights
7. [Node] report_drafting_node
    a. LLM → формирование черновика с таблицами
    b. → report_sections_draft + compiled_markdown
8. [Node] safety_check_node
    a. LLM → проверка is_safe + is_accurate
    b. Если fail → error + retry (report_drafting)
9. [Edge] check_safety_status
    a. safe → report_finalization
    b. error, retries < 2 → report_drafting (retry)
    c. error, retries >= 2 → END (abort)
10. [Node] report_finalization_node
    a. Сборка финального Markdown
    b. → final_report, status = "completed"
11. [GUI] Отображение результатов
    a. Профиль документа
    b. Инсайты (редактируемые)
    c. Кнопка "Сгенерировать отчёт с учётом правок"
    d. Предпросмотр + скачивание
```

### 4.2. Формат данных между узлами

Все узлы получают и возвращают `GraphState` (TypedDict). Узлы могут **читать** любые поля состояния и **записывать** только свои выходные поля. Это гарантирует изоляцию и предсказуемость.

**Контракты:**

| Узел | Читает | Пишет |
|------|--------|-------|
| `document_analysis` | `request_id`, `file_path`, `instructions` | `document_profile`, `raw_extracted_texts`, `status` |
| `insight_generation` | `document_profile`, `raw_extracted_texts`, `instructions` | `analysis_insights`, `status` |
| `report_drafting` | `document_profile`, `analysis_insights`, `raw_extracted_texts`, `instructions` | `report_sections_draft`, `status` |
| `safety_check` | `report_sections_draft`, `document_profile`, `instructions` | `status` |
| `report_finalization` | `report_sections_draft`, `raw_extracted_texts` | `final_report`, `status` |

---

## 5. Обработка ошибок и отказоустойчивость

### 5.1. Retry-логика LLM

Каждый узел, вызывающий LLM, реализует:

- **3 попытки** вызова с exponential backoff: 2s, 4s, 8s
- Обработка сетевых ошибок (`RequestException`, `TimeoutError`)
- Обработка ошибок парсинга JSON (`JSONDecodeError`) и валидации Pydantic (`ValidationError`)

### 5.2. Fallback-режимы

**Document Analysis:**
- Если PDF — скан (нет текстового слоя): создаётся fallback-профиль с `quality = 0.0` и пометкой "Требуется OCR"
- Если LLM вернула отказ (guardrails): создаётся fallback-профиль с пометкой
- Если LLM вернула некорректный JSON после 3 попыток: создаётся fallback-профиль

**Insight Generation:**
- Если LLM не вернула ни одного инсайта после всех retry: `status = "error"`

**Safety Check:**
- Если данные отсутствуют: проверка **пропускается** (не блокирует пайплайн)

### 5.3. Ретраи графа

При ошибке в `safety_check_node` граф может вернуться на `report_drafting_node` для повторной генерации отчета (до 2 ретраев). Счётчик хранится в `safety_check_retries`.

---

## 6. Конфигурация и окружение

### 6.1. `.env`

```env
OPENROUTER_API_KEY=sk-or-v1-...
```

### 6.2. Модель LLM

- **Провайдер:** OpenRouter
- **Модель:** `google/gemini-2.5-flash`
- **Температура:** 0.1–0.3 (в зависимости от узла)
- **Base URL:** `https://openrouter.ai/api/v1`
- **Заголовки:** `HTTP-Referer` + `X-Title` (требования OpenRouter)

---

## 7. Установка и запуск

### 7.1. Требования

- Python 3.11+
- Зависимости из `requirements.txt`

### 7.2. Установка

```bash
pip install -r requirements.txt
```

### 7.3. Запуск

```bash
streamlit run app.py
```

Откроется браузер с адресом `http://localhost:8501`.

### 7.4. Использование

1. Загрузите PDF-документ (ЕГРНИ, техпаспорт или акт осмотра).
2. Опционально укажите инструкции для анализа в боковой панели.
3. Нажмите **«Начать анализ»**.
4. Наблюдайте за прогрессом прохождения узлов графа.
5. После завершения — просмотрите профиль документа и инсайты.
6. **Отредактируйте инсайты** при необходимости (текст описания, уровень критичности).
7. Нажмите **«Сгенерировать отчёт с учётом правок»**.
8. Просмотрите финальный отчёт и скачайте его в Markdown.

---

## 8. Ограничения и известные проблемы

1. **OCR отсутствует:** Система не распознаёт текст из сканированных PDF (нужен внешний OCR-сервис).
2. **Один документ за раз:** Пайплайн рассчитан на обработку одного PDF-файла. Поддержка нескольких документов не реализована.
3. **Экспорт только в Markdown:** Финальный отчёт сохраняется как `.md`. Экспорт в DOCX/PDF требует дополнительного конвертера.
4. **Языковая модель:** Завязана на `google/gemini-2.5-flash` через OpenRouter. Смена модели или провайдера требует изменения кода в каждом узле.
5. **Нет кэширования:** При каждом запуске LLM вызывается заново для одних и тех же документов.
6. **Узел визуализации:** Не реализован (заглушка). Графики и диаграммы в отчёт не добавляются.

---

## 9. Планы по развитию

1. **Поддержка OCR** — интеграция Tesseract или OCR-сервиса для сканированных PDF.
2. **Мульти-документный пайплайн** — загрузка нескольких PDF (ЕГРНИ + техпаспорт + акт осмотра) с кросс-верификацией.
3. **Экспорт в DOCX/PDF** — генерация отчёта в форматах Microsoft Word и PDF.
4. **Кэширование LLM-ответов** — уменьшение времени повторного анализа.
5. **Агентный цикл обратной связи** — интеграция `UserFeedback` для автоматического уточнения данных.
6. **Docker-контейнеризация** — для лёгкого деплоя на сервер.

---

## 10. Диаграмма классов (схема данных)

```
┌──────────────────────────────────────────────────────────┐
│                     GraphState (TypedDict)                │
├──────────────────────────────────────────────────────────┤
│ request_id: str                                          │
│ file_path: str                                           │
│ instructions: str                                        │
│ document_profile: Optional[DocumentProfile]              │
│ raw_extracted_texts: Optional[Dict[str, str]]            │
│ analysis_insights: Optional[List[ValuationInsight]]      │
│ report_sections_draft: Optional[ReportSectionDraft]      │
│ final_report: Optional[ReportDraft]                      │
│ feedback_history: Optional[List[UserFeedback]]          │
│ status: str                                              │
│ error_message: Optional[str]                             │
│ safety_check_retries: int                                │
└───────────────────┬──────────────────────────────────────┘
                    │ содержит
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Pydantic Models                               │
├──────────────────────┬───────────────────────┬───────────────────────┤
│   DocumentProfile    │   ValuationInsight    │   ReportSectionDraft  │
│──────────────────────│───────────────────────│───────────────────────│
│ document_type        │ insight_id            │ section_title         │
│ total_pages          │ title                 │ introduction_context  │
│ extraction_quality   │ severity              │ table_4_extracted     │
│ key_metadata         │ narrative             │ table_5_extracted     │
│                      │ affected_tables       │ analysis_narrative    │
│                      │                       │ methodology_just      │
├──────────────────────┴───────────────────────┴───────────────────────┤
│  LandCharacteristicsTable4              PropertyImprovementsTable5  │
│──────────────────────────────────────────────────────────────────────│
│ address, cadastral_number, area_ha,     name_and_purpose, year_built │
│ purpose_by_executive_committee,         actual_condition, total_floors│
│ purpose_by_classifier, central_utils,   object_floor, finishing_level│
│ property_rights, right_holder,          total_area_sqm, snb_area_sqm│
│ encumbrances, building_inventory_number, living_area_sqm, materials  │
│ cadastral_cost_per_sqm, valuation_date  engineering_equipment (dict) │
├──────────────────────────────────────────────────────────────────────┤
│  ReportDraft                               UserFeedback              │
│──────────────────────┬───────────────────────────────────────────────┤
│ document_title       │ feedback_id, target_table, target_field       │
│ compiled_markdown    │ corrected_value, comment, timestamp           │
│ format_type          │                                               │
│ output_file_path     │                                               │
└──────────────────────┴───────────────────────────────────────────────┘
```

---

## 11. Заключение

AI Report Generator представляет собой законченный proof-of-concept автоматизированной системы оценки недвижимости на базе LangGraph и LLM. Система демонстрирует практическое применение графов состояний для оркестрации多-шаговых бизнес-процессов с участием LLM, с обработкой ошибок, retry-логикой и человеческим контролем на критических этапах.

Архитектура на основе LangGraph StateGraph обеспечивает:
- **Модульность** — каждый узел изолирован и тестируем
- **Устойчивость** — retry-логика и fallback-режимы на каждом этапе
- **Прозрачность** — полный трекинг состояния на каждом шаге
- **Расширяемость** — новые узлы добавляются без изменения существующих
