"""Test only the document analysis node with scanned PDF."""
import sys, os, json, logging
sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

from src.nodes.document_analysis_node import document_analysis_node
from src.schemas.states import GraphState, DocumentProfile

pdf_path = 'local_app_data/uploads/3f21cd8f650e428cbef4ba658b1a6df3_3_квартира-pages-2.pdf'
if not os.path.exists(pdf_path):
    import glob
    pdfs = glob.glob("local_app_data/uploads/*.pdf")
    if pdfs:
        pdf_path = pdfs[0]
    else:
        print("ERROR: No PDFs found")
        sys.exit(1)

print(f"Testing with: {os.path.basename(pdf_path)}")

state = GraphState(
    request_id="test_ocr",
    file_path=pdf_path,
    instructions="Извлеки все данные для заполнения таблиц отчета об оценке.",
    document_profile=None,
    raw_extracted_texts=None,
    analysis_insights=None,
    report_sections_draft=None,
    final_report=None,
    feedback_history=None,
    status="pending",
    error_message=None,
    safety_check_retries=0,
)

try:
    result = document_analysis_node(state)
    print(f"\nStatus: {result.get('status')}")
    profile = result.get('document_profile')
    if profile:
        print(f"Type: {profile.document_type}")
        print(f"Quality: {profile.extraction_quality_score}")
        print(f"Metadata: {json.dumps(profile.key_metadata, ensure_ascii=False, indent=2)}")
    
    texts = result.get('raw_extracted_texts', {})
    print(f"\nText keys: {list(texts.keys())}")
    
    t4 = texts.get('_ocr_table_4_candidate', '')
    t5 = texts.get('_ocr_table_5_candidate', '')
    if t4 and t4 != 'null':
        print(f"\nTable 4 candidate found: {t4[:300]}")
    if t5 and t5 != 'null':
        print(f"\nTable 5 candidate found: {t5[:300]}")
    
    vision_text = texts.get('_ocr_text', '')
    if vision_text:
        print(f"\nOCR text length: {len(vision_text)} chars")
        print(f"Text preview: {vision_text[:400]}")
    
    print("\nDOCUMENT ANALYSIS OK")
    
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
