from typing import List, Optional, Dict, Any, TypedDict
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentProfile(BaseModel):
    """
    Представляет собой результат классификации и первичного анализа 
    загруженного пользователем документа (PDF, изобр, docx).
    """
    document_type: str = Field(
        description="Тип документа (например: 'ЕГРНИ_Земля', 'ЕГРНИ_Помещение', 'Техпаспорт', 'Акт_Осмотра')"
    )
    total_pages: int = Field(description="Общее количество страниц в документе")
    extraction_quality_score: float = Field(
        description="Оценка качества распознавания текста (OCR) от 0.0 до 1.0"
    )
    key_metadata: Dict[str, Any] = Field(
        description="Базовые метаданные (дата выдачи документа, номер бланка, орган выдачи)"
    )


class LandCharacteristicsTable4(BaseModel):
    """
    Строгая структура данных для Таблицы 4 'Характеристики земельного участка' (стр. 23 отчета).
    """
    address: str = Field(description="Адрес (местоположение) земельного участка")
    cadastral_number: str = Field(description="Кадастровый номер земельного участка")
    area_ha: float = Field(description="Площадь земельного участка в гектарах (га)")
    purpose_by_executive_committee: str = Field(
        description="Целевое назначение по решению местного исполнительного комитета"
    )
    purpose_by_classifier: str = Field(
        description="Назначение по единой классификации объектов недвижимого имущества"
    )
    central_utilities: List[str] = Field(
        description="Список центральных инженерных коммуникаций, доступных на участке"
    )
    property_rights: str = Field(description="Вид имущественных прав на земельный участок")
    right_holder_and_share: str = Field(
        description="Наименование правообладателя и его доля в праве"
    )
    encumbrances_or_restrictions: List[str] = Field(
        description="Ограничения (обременения) прав на земельный участок, включая охранные зоны"
    )
    building_inventory_number: str = Field(
        description="Инвентарный номер капитального строения, расположенного на участке"
    )
    cadastral_cost_per_sqm_usd: float = Field(
        description="Кадастровая стоимость 1 кв.м. земель в долларах США"
    )
    cadastral_valuation_date: str = Field(
        description="Дата проведения кадастровой оценки стоимости земель"
    )


class PropertyImprovementsTable5(BaseModel):
    """
    Строгая структура данных для Таблицы 5 'Характеристики недвижимых улучшений' (стр. 24-25 отчета).
    """
    name_and_purpose: str = Field(
        description="Наименование и назначение объекта (например: Изолированное помещение, квартира)"
    )
    year_built: int = Field(description="Год постройки основного здания (жилого дома)")
    actual_condition: str = Field(
        description="Фактическое техническое состояние объекта по результатам осмотра"
    )
    total_floors: int = Field(description="Этажность здания (всего этажей в доме)")
    object_floor: int = Field(description="Этаж расположения оцениваемого объекта")
    finishing_level: str = Field(description="Уровень внутренней отделки помещения")
    total_area_sqm: float = Field(description="Общая площадь жилого помещения (кв.м.)")
    snb_area_sqm: float = Field(description="Общая площадь квартиры по СНБ (кв.м.)")
    living_area_sqm: float = Field(description="Жилая площадь квартиры (кв.м.)")
    
    walls_material: str = Field(description="Материал наружных и внутренних стен")
    partitions_material: str = Field(description="Материал межкомнатных перегородок")
    floors_structure: str = Field(description="Материал и тип междуэтажных перекрытий")
    windows_and_openings: str = Field(description="Характеристика оконных и дверных проемов")
    flooring_material: str = Field(
        description="Материал покрытия полов (если данные взяты из Акта осмотра, пометить *)"
    )
    balcony_or_loggia: str = Field(description="Наличие и тип балконов или лоджий")
    
    engineering_equipment: Dict[str, str] = Field(
        description="Словарь видов инженерного оборудования и их характеристик (отопление, водопровод, газоснабжение и т.д.)"
    )


class ValuationInsight(BaseModel):
    """
    Представляет собой критическое наблюдение, расхождение данных 
    или юридический риск, обнаруженный агентами при кросс-проверке документов.
    """
    insight_id: str = Field(description="Уникальный идентификатор наблюдения")
    title: str = Field(description="Краткое название проблемы/наблюдения")
    severity: str = Field(
        description="Уровень критичности для оценки ('INFO', 'WARNING', 'CRITICAL')"
    )
    narrative: str = Field(
        description="Подробное описание расхождения (например: Площадь в Техпаспорте не совпадает с Выпиской ЕГРНИ)"
    )
    affected_tables: List[str] = Field(
        description="Список таблиц, на которые влияет данное наблюдение (например, ['Таблица 4', 'Таблица 5'])"
    )


class ReportSectionDraft(BaseModel):
    """
    Представляет структуру конкретного генерируемого раздела отчета об оценке.
    """
    section_title: str = Field(description="Название раздела (например, 'Описание объекта оценки')")
    introduction_context: str = Field(description="Вводная/нормативная часть раздела")
    table_4_extracted: Optional[LandCharacteristicsTable4] = Field(
        default=None, description="Данные для Таблицы 4 (если применимо к разделу)"
    )
    table_5_extracted: Optional[PropertyImprovementsTable5] = Field(
        default=None, description="Данные для Таблицы 5 (если применимо к разделу)"
    )
    analysis_narrative: List[str] = Field(
        description="Связанный аналитический текст описания качественных характеристик объекта"
    )
    methodology_justification: Optional[str] = Field(
        default=None, description="Обоснование использования или отказа от подходов к оценке в рамках раздела"
    )


class ReportDraft(BaseModel):
    """
    Представляет собой итоговое содержимое собранного отчета перед компиляцией в файл.
    """
    document_title: str = Field(description="Полное официальное название отчета об оценке")
    compiled_markdown: str = Field(description="Полный текст отчета в формате Markdown со всеми таблицами")
    format_type: str = Field(description="Целевой формат экспорта ('DOCX', 'PDF')")
    output_file_path: Optional[str] = Field(
        default=None, description="Путь к сгенерированному файлу отчета на сервере"
    )


class UserFeedback(BaseModel):
    """
    Обратная связь от оценщика-верификатора для корректировки извлеченных данных.
    """
    feedback_id: str = Field(description="Уникальный идентификатор правки")
    target_table: str = Field(description="Какая таблица правится (например, 'Таблица 5')")
    target_field: str = Field(description="Изменяемое поле (например, 'flooring_material')")
    corrected_value: Any = Field(description="Новое значение, введенное пользователем вручную")
    comment: Optional[str] = Field(default=None, description="Причина корректировки")
    timestamp: datetime = Field(default_factory=datetime.now, description="Время внесения правки")


class GraphState(TypedDict):
    """
    Представляет состояние графа для автоматизации оценки недвижимости.
    
    Attributes:
        request_id (str): Уникальный ID запроса.
        file_path (str): Путь к файлу (PDF/DOCX).
        instructions (str): Инструкции пользователя.
        
        # Данные этапа Document Analysis (заменяют dataframe_profile)
        document_profile (Optional[DocumentProfile]): Профиль и метаданные документа.
        raw_extracted_texts (Optional[Dict[str, str]]): Сырой текст, извлеченный из страниц.
        
        # Данные этапа Insight Generation
        analysis_insights (Optional[List[ValuationInsight]]): Список рисков, обременений и наблюдений.
        
        # Этапы подготовки отчета
        report_sections_draft (Optional[ReportSectionsDraft]): Черновик текста отчета.
        final_report (Optional[ReportFormat]): Скомпилированный финальный отчет (например, в PDF/DOCX).
        
        feedback_history (Optional[List[UserFeedback]]): История правок и уточнений.
        
        status (str): Текущий этап: "pending", "document_profiled", "insights_generated", "report_drafted", "completed", "error".
        error_message (Optional[str]): Описание ошибки при сбое.
        safety_check_retries (int): Счетчик попыток ретраев (для Guardrails/API).
    """
    request_id: str
    file_path: str
    instructions: str
    
    # Специфичные поля для документов
    document_profile: Optional[DocumentProfile]
    raw_extracted_texts: Optional[Dict[str, str]]
    
    # Инсайты по оценке (Valuation Insights)
    analysis_insights: Optional[List[ValuationInsight]]
    
    # Генерация отчета
    report_sections_draft: Optional[ReportSectionDraft]
    final_report: Optional[ReportDraft]
    
    # Управление процессом
    feedback_history: Optional[List[UserFeedback]]
    status: str
    error_message: Optional[str]
    safety_check_retries: int
