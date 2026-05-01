#!/usr/bin/env python3
"""
Backend test for PDF translation with OCR support.
Tests both image-based PDFs (OCR flow) and text-based PDFs (standard flow).
"""

import requests
import time
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import io
import sys

# Backend URL from frontend/.env
BACKEND_URL = "https://slide-translator-app.preview.emergentagent.com/api"

def create_image_based_pdf(output_path: str):
    """Create an image-based PDF (no text layer) for OCR testing."""
    print(f"Creating image-based PDF at {output_path}...")
    
    # Create an image with text
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)
    
    # Use default font since we may not have custom fonts
    draw.text((50, 50), "Hello World", fill='black')
    draw.text((50, 100), "This is a test document", fill='black')
    draw.text((50, 150), "Beautiful weather today", fill='black')
    
    # Save image to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    # Create PDF from image (no text layer)
    doc = fitz.open()
    page = doc.new_page(width=800, height=400)
    page.insert_image(page.rect, stream=img_bytes.read())
    doc.save(output_path)
    doc.close()
    
    print(f"✓ Image-based PDF created: {output_path}")


def create_text_based_pdf(output_path: str):
    """Create a normal text-based PDF for standard flow testing."""
    print(f"Creating text-based PDF at {output_path}...")
    
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello World", fontsize=14)
    page.insert_text((72, 100), "This is a test document", fontsize=14)
    page.insert_text((72, 128), "Beautiful weather today", fontsize=14)
    doc.save(output_path)
    doc.close()
    
    print(f"✓ Text-based PDF created: {output_path}")


def test_pdf_flow(pdf_path: str, pdf_type: str, target_language: str = "German", tone: str = "formal"):
    """
    Test the full PDF translation flow.
    
    Args:
        pdf_path: Path to the PDF file
        pdf_type: "image-based" or "text-based"
        target_language: Target language for translation
        tone: Translation tone
    
    Returns:
        dict with test results
    """
    print(f"\n{'='*60}")
    print(f"Testing {pdf_type} PDF flow")
    print(f"{'='*60}")
    
    results = {
        "pdf_type": pdf_type,
        "upload": False,
        "translate": False,
        "progress": False,
        "preview": False,
        "download": False,
        "ocr_detected": False,
        "translation_works": False,
        "errors": []
    }
    
    try:
        # Step 1: Upload PDF
        print(f"\n1. Uploading {pdf_type} PDF...")
        with open(pdf_path, 'rb') as f:
            files = {'file': (f'test_{pdf_type}.pdf', f, 'application/pdf')}
            response = requests.post(f"{BACKEND_URL}/upload", files=files, timeout=30)
        
        if response.status_code != 200:
            results["errors"].append(f"Upload failed: {response.status_code} - {response.text}")
            print(f"✗ Upload failed: {response.status_code}")
            return results
        
        upload_data = response.json()
        job_id = upload_data.get('id')
        total_segments = upload_data.get('total_segments', 0)
        
        print(f"✓ Upload successful")
        print(f"  Job ID: {job_id}")
        print(f"  Total segments: {total_segments}")
        print(f"  File type: {upload_data.get('file_type')}")
        
        if total_segments == 0:
            results["errors"].append(f"No segments extracted from {pdf_type} PDF")
            print(f"✗ No segments extracted!")
            return results
        
        results["upload"] = True
        
        # For image-based PDFs, we expect OCR to extract text
        if pdf_type == "image-based" and total_segments > 0:
            results["ocr_detected"] = True
            print(f"✓ OCR successfully extracted {total_segments} segments")
        
        # Step 2: Start translation
        print(f"\n2. Starting translation to {target_language}...")
        translate_payload = {
            "target_language": target_language,
            "tone": tone
        }
        response = requests.post(
            f"{BACKEND_URL}/translate/{job_id}",
            json=translate_payload,
            timeout=30
        )
        
        if response.status_code != 200:
            results["errors"].append(f"Translation start failed: {response.status_code} - {response.text}")
            print(f"✗ Translation start failed: {response.status_code}")
            return results
        
        print(f"✓ Translation started")
        results["translate"] = True
        
        # Step 3: Poll progress until completed
        print(f"\n3. Polling translation progress...")
        max_wait = 120  # 2 minutes max
        start_time = time.time()
        completed = False
        
        while time.time() - start_time < max_wait:
            response = requests.get(f"{BACKEND_URL}/progress/{job_id}", timeout=30)
            
            if response.status_code != 200:
                results["errors"].append(f"Progress check failed: {response.status_code}")
                print(f"✗ Progress check failed: {response.status_code}")
                break
            
            progress_data = response.json()
            status = progress_data.get('status')
            progress = progress_data.get('progress', 0)
            translated_segments = progress_data.get('translated_segments', 0)
            
            print(f"  Status: {status}, Progress: {progress:.1f}%, Translated: {translated_segments}/{total_segments}")
            
            if status == "completed":
                completed = True
                results["progress"] = True
                print(f"✓ Translation completed")
                break
            elif status == "error":
                error_msg = progress_data.get('error_message', 'Unknown error')
                results["errors"].append(f"Translation error: {error_msg}")
                print(f"✗ Translation error: {error_msg}")
                break
            
            time.sleep(2)
        
        if not completed:
            results["errors"].append("Translation timed out")
            print(f"✗ Translation timed out after {max_wait}s")
            return results
        
        # Step 4: Get preview and verify translation
        print(f"\n4. Checking preview...")
        response = requests.get(f"{BACKEND_URL}/preview/{job_id}", timeout=30)
        
        if response.status_code != 200:
            results["errors"].append(f"Preview failed: {response.status_code}")
            print(f"✗ Preview failed: {response.status_code}")
            return results
        
        preview_data = response.json()
        segments = preview_data.get('segments', [])
        
        if not segments:
            results["errors"].append("No translated segments in preview")
            print(f"✗ No translated segments in preview")
            return results
        
        results["preview"] = True
        print(f"✓ Preview retrieved: {len(segments)} segments")
        
        # Verify translation actually translated (not just returning original)
        translation_verified = False
        for seg in segments[:3]:  # Check first 3 segments
            original = seg.get('original', '')
            translated = seg.get('translated', '')
            print(f"  Segment {seg.get('idx')}:")
            print(f"    Original: {original[:50]}...")
            print(f"    Translated: {translated[:50]}...")
            
            # Check if translation is different from original
            if original and translated and original != translated:
                translation_verified = True
        
        if translation_verified:
            results["translation_works"] = True
            print(f"✓ Translation verified: text was actually translated")
        else:
            results["errors"].append("Translation returned original text (not translated)")
            print(f"✗ Translation did not change text")
        
        # Step 5: Download translated PDF
        print(f"\n5. Downloading translated PDF...")
        response = requests.get(f"{BACKEND_URL}/download/{job_id}", timeout=30)
        
        if response.status_code != 200:
            results["errors"].append(f"Download failed: {response.status_code}")
            print(f"✗ Download failed: {response.status_code}")
            return results
        
        # Verify it's a valid PDF
        content_type = response.headers.get('content-type', '')
        content_length = len(response.content)
        
        print(f"✓ Download successful")
        print(f"  Content-Type: {content_type}")
        print(f"  Size: {content_length} bytes")
        
        if 'application/pdf' not in content_type:
            results["errors"].append(f"Downloaded file is not a PDF: {content_type}")
            print(f"✗ Downloaded file is not a PDF")
            return results
        
        # Try to open the PDF to verify it's valid
        try:
            pdf_bytes = io.BytesIO(response.content)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            doc.close()
            print(f"✓ Downloaded PDF is valid ({page_count} pages)")
            results["download"] = True
        except Exception as e:
            results["errors"].append(f"Downloaded PDF is invalid: {str(e)}")
            print(f"✗ Downloaded PDF is invalid: {e}")
            return results
        
    except Exception as e:
        results["errors"].append(f"Unexpected error: {str(e)}")
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    return results


def main():
    print("="*60)
    print("PDF Translation Backend Test with OCR Support")
    print("="*60)
    print(f"Backend URL: {BACKEND_URL}")
    
    # Create test PDFs
    image_pdf_path = "/tmp/test_image_pdf.pdf"
    text_pdf_path = "/tmp/test_text_pdf.pdf"
    
    create_image_based_pdf(image_pdf_path)
    create_text_based_pdf(text_pdf_path)
    
    # Test 1: Image-based PDF (OCR flow)
    print("\n" + "="*60)
    print("TEST 1: Image-based PDF (OCR flow)")
    print("="*60)
    image_results = test_pdf_flow(image_pdf_path, "image-based", "German", "formal")
    
    # Test 2: Text-based PDF (standard flow)
    print("\n" + "="*60)
    print("TEST 2: Text-based PDF (standard flow)")
    print("="*60)
    text_results = test_pdf_flow(text_pdf_path, "text-based", "German", "formal")
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    def print_results(results, test_name):
        print(f"\n{test_name}:")
        print(f"  Upload: {'✓' if results['upload'] else '✗'}")
        print(f"  Translate: {'✓' if results['translate'] else '✗'}")
        print(f"  Progress: {'✓' if results['progress'] else '✗'}")
        print(f"  Preview: {'✓' if results['preview'] else '✗'}")
        print(f"  Download: {'✓' if results['download'] else '✗'}")
        if results['pdf_type'] == "image-based":
            print(f"  OCR Detected: {'✓' if results['ocr_detected'] else '✗'}")
        print(f"  Translation Works: {'✓' if results['translation_works'] else '✗'}")
        if results['errors']:
            print(f"  Errors:")
            for err in results['errors']:
                print(f"    - {err}")
    
    print_results(image_results, "Image-based PDF (OCR)")
    print_results(text_results, "Text-based PDF (Standard)")
    
    # Overall status
    image_success = all([
        image_results['upload'],
        image_results['translate'],
        image_results['progress'],
        image_results['preview'],
        image_results['download'],
        image_results['ocr_detected'],
        image_results['translation_works']
    ])
    
    text_success = all([
        text_results['upload'],
        text_results['translate'],
        text_results['progress'],
        text_results['preview'],
        text_results['download'],
        text_results['translation_works']
    ])
    
    print("\n" + "="*60)
    print("OVERALL RESULT")
    print("="*60)
    print(f"Image-based PDF (OCR): {'✓ PASS' if image_success else '✗ FAIL'}")
    print(f"Text-based PDF (Standard): {'✓ PASS' if text_success else '✗ FAIL'}")
    
    if image_success and text_success:
        print("\n✓ ALL TESTS PASSED")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
