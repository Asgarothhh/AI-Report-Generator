# Документация базы данных системы оценки недвижимости (с RBAC)

Данный документ описывает структуру реляционной базы данных для системы автоматизированной генерации отчетов об оценке, включая ролевую модель управления доступом.

## Архитектурные решения
* **СУБД:** PostgreSQL.
* **Типы ключей:** `UUID` (v4) для всех первичных ключей.
* **Связи:** Настроены строгие внешние ключи (Foreign Keys) для обеспечения целостности.
* **RBAC:** Реализована через связующие таблицы `user_roles` и `role_permissions` (Многие-ко-Многим).

---

## Часть 1: Управление пользователями и доступом (RBAC)

### 1. `users`
Учетные записи сотрудников системы.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | Уникальный идентификатор пользователя. |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Email (используется как логин). |
| `password_hash` | VARCHAR(255) | NOT NULL | Хэш пароля (например, bcrypt/Argon2). |
| `first_name` | VARCHAR(100) | NOT NULL | Имя пользователя. |
| `last_name` | VARCHAR(100) | NOT NULL | Фамилия пользователя. |
| `is_active` | BOOLEAN | DEFAULT TRUE | Статус учетной записи (для мягкого удаления). |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

### 2. `roles`
Справочник ролей (например: 'Admin', 'Appraiser', 'Reviewer').

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | Системное имя роли (например, 'appraiser'). |
| `description` | VARCHAR(255) | | Читаемое описание роли. |

### 3. `permissions`
Гранулярные права доступа.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | Код права (например, 'generate_report', 'edit_tables'). |
| `description` | VARCHAR(255) | | Описание действия. |

### 4. `user_roles`
Связующая таблица: какие роли назначены пользователю.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `user_id` | UUID | FK -> users(id), PK | (Composite Primary Key с role_id). |
| `role_id` | UUID | FK -> roles(id), PK | |

### 5. `role_permissions`
Связующая таблица: какие права входят в роль.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `role_id` | UUID | FK -> roles(id), PK | (Composite Primary Key с permission_id). |
| `permission_id`| UUID | FK -> permissions(id), PK | |

---

## Часть 2: Процесс оценки и артефакты

### 6. `valuation_projects`
Основная сущность процесса оценки. Теперь привязана к конкретным сотрудникам.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `title` | VARCHAR(255) | NOT NULL | Название проекта. |
| `status` | VARCHAR(50) | NOT NULL | Статус графа LangGraph. |
| `appraiser_id` | UUID | FK -> users(id) | Оценщик, создавший/ведущий проект. |
| `reviewer_id` | UUID | FK -> users(id) | Верификатор (опционально, если назначен). |
| `instructions` | TEXT | | Исходные инструкции для LLM. |
| `final_report_path`| VARCHAR(500)| | Путь к сгенерированному файлу. |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

### 7. `documents`
Исходные файлы (PDF), привязанные к проекту.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `project_id` | UUID | FK -> valuation_projects(id) | (ON DELETE CASCADE). |
| `file_name` | VARCHAR(255) | NOT NULL | |
| `file_path` | VARCHAR(500) | NOT NULL | |
| `document_type` | VARCHAR(100) | | Тип (ЕГРНИ, Техпаспорт). |
| `total_pages` | INTEGER | | |
| `extraction_score`| DECIMAL(3,2) | | Оценка качества OCR. |
| `metadata_json` | JSONB | | Реквизиты документа. |
| `raw_text` | TEXT | | Извлеченный текстовый слой. |

### 8. `land_characteristics`
Данные для "Таблицы 4: Характеристики земельного участка".

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `project_id` | UUID | FK -> valuation_projects(id), UNIQUE | Связь 1:1. |
| `address` | VARCHAR(500) | | |
| `cadastral_number`| VARCHAR(100) | | |
| `area_ha` | DECIMAL(10,4) | | |
| `purpose_exec` | VARCHAR(500) | | |
| `purpose_class` | VARCHAR(500) | | |
| `property_rights` | VARCHAR(255) | | |
| `right_holder` | VARCHAR(500) | | |
| `building_inv_no` | VARCHAR(100) | | |
| `cadastral_cost` | DECIMAL(15,2) | | |
| `valuation_date` | VARCHAR(50) | | |
| `utilities` | JSONB | | |
| `encumbrances` | JSONB | | |

### 9. `property_improvements`
Данные для "Таблицы 5: Характеристики недвижимых улучшений".

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `project_id` | UUID | FK -> valuation_projects(id), UNIQUE | Связь 1:1. |
| `name_purpose` | VARCHAR(255) | | |
| `year_built` | INTEGER | | |
| `actual_condition`| VARCHAR(255) | | |
| `total_floors` | INTEGER | | |
| `object_floor` | INTEGER | | |
| `finishing_level` | VARCHAR(255) | | |
| `total_area_sqm` | DECIMAL(10,2) | | |
| `snb_area_sqm` | DECIMAL(10,2) | | |
| `living_area_sqm` | DECIMAL(10,2) | | |
| `walls_material` | VARCHAR(255) | | |
| `partitions` | VARCHAR(255) | | |
| `floors_structure`| VARCHAR(255) | | |
| `flooring_material`| VARCHAR(255) | | |
| `windows_openings`| VARCHAR(255) | | |
| `balcony_loggia` | VARCHAR(255) | | |
| `engineering_eq` | JSONB | | |

### 10. `valuation_insights`
Выявленные ИИ риски и расхождения в документах.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `project_id` | UUID | FK -> valuation_projects(id) | |
| `insight_key` | VARCHAR(100) | NOT NULL | Ключ инсайта. |
| `title` | VARCHAR(255) | NOT NULL | Заголовок. |
| `severity` | VARCHAR(50) | NOT NULL | Уровень критичности. |
| `narrative` | TEXT | NOT NULL | Описание. |
| `affected_tables` | JSONB | | |

### 11. `user_feedback`
Аудит ручных правок: отслеживает, кто из сотрудников (user_id) изменил данные, предложенные LLM.

| Поле | Тип данных | Ограничения | Описание |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | |
| `project_id` | UUID | FK -> valuation_projects(id) | |
| `user_id` | UUID | FK -> users(id) | Сотрудник, вносящий правку. |
| `target_table` | VARCHAR(100) | NOT NULL | Название таблицы БД. |
| `target_field` | VARCHAR(100) | NOT NULL | Изменяемое поле. |
| `old_value` | TEXT | | Старое значение. |
| `new_value` | TEXT | NOT NULL | Новое значение. |
| `comment` | TEXT | | Причина правки. |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |