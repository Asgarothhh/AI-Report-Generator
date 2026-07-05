"""Debug OCR service - find out exactly what's happening."""
import sys, os, json, logging
sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

from src.utils.ocr_service import _render_page_as_base64_png, _call_gemini_vision_multipage, analyze_scanned_pdf

path = 'local_app_data/uploads/3f21cd8f650e428cbef4ba658b1a6df3_3_квартира-pages-2.pdf'
if not os.path.exists(path):
    import glob
    pdfs = glob.glob("local_app_data/uploads/*.pdf")
    if pdfs:
        path = pdfs[0]

print(f"Testing with: {path}")
print(f"File size: {os.path.getsize(path)/1024/1024:.1f} MB")
print(f"File exists: {os.path.exists(path)}")

# Test 1: Can we render pages?
print("\n=== TEST 1: Render pages ===")
for i in [0, 1, 2]:
    img = _render_page_as_base64_png(path, i, 100)
    if img:
        print(f"  Page {i}: {len(img)/1024:.0f} KB base64")
    else:
        print(f"  Page {i}: FAILED")

# Test 2: Send just 2 pages with simple prompt (fast test)
print("\n=== TEST 2: 2-page OCR ===")
pages = []
for i in [0, 2]:
    img = _render_page_as_base64_png(path, i, 100)
    if img:
        pages.append(img)

if pages:
    prompt = 'Извлеки весь текст с этих страниц. Ответь ТОЛЬКО текстом.'
    import time
    start = time.time()
    result = _call_gemini_vision_multipage(prompt, pages)
    took = time.time() - start
    print(f"  Time: {took:.1f}s")
    if result:
        print(f"  Result: {result[:400]}")
    else:
        print("  RESULT: None (API failed)")

# Test 3: Full analysis with min settings
print("\n=== TEST 3: analyze_scanned_pdf with very low settings ===")
ocr_result = analyze_scanned_pdf(path, instructions="Тест", dpi=100, max_pages=3)
print(f"  Error: {ocr_result.get('error')}")
print(f"  Doc type: {ocr_result.get('document_type')}")
print(f"  Quality: {ocr_result.get('extraction_quality_score')}")
print(f"  Table 4: {'YES' if ocr_result.get('table_4_candidate') else 'NO'}")
print(f"  Table 5: {'YES' if ocr_result.get('table_5_candidate') else 'NO'}")
print(f"  Keys: {list(ocr_result.keys())}")

print("\n=== DONE ===")
