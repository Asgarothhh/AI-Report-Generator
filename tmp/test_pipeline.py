"""
Test the full pipeline with a real scanned PDF.
This tests the entire flow: document_analysis -> insight_generation -> report_drafting -> report_finalization.
"""
import sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

from src.pipeline import run_valuation_pipeline, format_report_preview

# Find any PDF in uploads
import glob
pdfs = glob.glob("local_app_data/uploads/*.pdf")
if not pdfs:
    print("ERROR: No PDFs found in uploads")
    sys.exit(1)

test_pdf = pdfs[0]
print(f"Testing with: {os.path.basename(test_pdf)}")

# Test the full pipeline with a timeout safety
try:
    result = run_valuation_pipeline(
        file_path=test_pdf,
        instructions="Извлеки все данные из документов для заполнения Таблицы 4 и Таблицы 5.",
    )
    
    print(f"\n{'='*60}")
    print(f"Status: {result.get('status')}")
    print(f"Error: {result.get('error_message')}")
    
    profile = result.get('document_profile')
    if profile:
        print(f"\nDocument Profile:")
        print(f"  Type: {profile.document_type}")
        print(f"  Pages: {profile.total_pages}")
        print(f"  Quality: {profile.extraction_quality_score:.2f}")
        print(f"  Metadata: {json.dumps(profile.key_metadata, ensure_ascii=False)}")
    
    insights = result.get('analysis_insights')
    if insights:
        print(f"\nAnalysis Insights ({len(insights)}):")
        for ins in insights:
            print(f"  [{ins.severity}] {ins.title}")
    
    draft = result.get('report_sections_draft')
    if draft:
        print(f"\nReport Draft:")
        print(f"  Section: {draft.section_title}")
        print(f"  Table 4: {'YES' if draft.table_4_extracted else 'NO'}")
        print(f"  Table 5: {'YES' if draft.table_5_extracted else 'NO'}")
        if draft.table_4_extracted:
            print(f"  T4 data: {draft.table_4_extracted.model_dump_json(indent=2, ensure_ascii=False)[:300]}")
        if draft.table_5_extracted:
            print(f"  T5 data: {draft.table_5_extracted.model_dump_json(indent=2, ensure_ascii=False)[:300]}")
    
    final = result.get('final_report')
    if final:
        print(f"\nFinal Report: {len(final.compiled_markdown)} chars")
        print(f"  Preview: {final.compiled_markdown[:500]}...")
    
    print(f"\n{'='*60}")
    print("PIPELINE TEST COMPLETE")
    
except Exception as e:
    print(f"PIPELINE FAILED: {e}")
    import traceback
    traceback.print_exc()
