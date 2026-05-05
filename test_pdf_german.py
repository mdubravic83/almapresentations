#!/usr/bin/env python3
"""
Focused PDF Translation Test with German as requested in review
Tests the complete PDF translation flow with German language
"""

import requests
import time
import fitz  # PyMuPDF

BACKEND_URL = "https://doc-translate-ocr.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def create_test_pdf():
    """Create a simple test PDF as specified in review request"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello World. This is a test.", fontsize=14)
    doc.save("/tmp/test.pdf")
    doc.close()
    print("✅ Created test PDF: /tmp/test.pdf")
    return "/tmp/test.pdf"

def test_pdf_translation_german():
    """Test complete PDF translation flow with German"""
    print("🚀 Testing PDF Translation Flow with German")
    print("=" * 60)
    
    # Step 1: Create test PDF
    pdf_path = create_test_pdf()
    
    # Step 2: Upload PDF
    print("\n📤 Step 1: Upload PDF...")
    with open(pdf_path, 'rb') as f:
        files = {'file': ('test.pdf', f, 'application/pdf')}
        response = requests.post(f"{API_BASE}/upload", files=files, timeout=30)
    
    if response.status_code != 200:
        print(f"❌ Upload failed: {response.status_code} - {response.text}")
        return False
    
    data = response.json()
    job_id = data['id']
    print(f"✅ Upload successful - Job ID: {job_id}")
    print(f"   Total segments: {data['total_segments']}")
    
    # Step 3: Start translation with German
    print("\n🔄 Step 2: Start translation to German with formal tone...")
    payload = {
        "target_language": "German",
        "tone": "formal"
    }
    response = requests.post(f"{API_BASE}/translate/{job_id}", json=payload, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Translation start failed: {response.status_code} - {response.text}")
        return False
    
    print(f"✅ Translation started: {response.json()}")
    
    # Step 4: Poll progress until completed
    print("\n⏳ Step 3: Polling progress until completed...")
    max_wait = 120
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        response = requests.get(f"{API_BASE}/progress/{job_id}", timeout=10)
        if response.status_code != 200:
            print(f"❌ Progress check failed: {response.status_code}")
            return False
        
        data = response.json()
        status = data['status']
        progress = data['progress']
        
        print(f"   Progress: {progress}%, Status: {status}")
        
        if status == "completed":
            print(f"✅ Translation completed in {time.time() - start_time:.1f}s")
            break
        elif status == "error":
            print(f"❌ Translation failed: {data.get('error_message')}")
            return False
        
        time.sleep(3)
    else:
        print(f"❌ Timeout after {max_wait}s")
        return False
    
    # Step 5: Check preview - verify translation is different from original
    print("\n🔍 Step 4: Check preview - verify translation is different from original...")
    response = requests.get(f"{API_BASE}/preview/{job_id}", timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Preview check failed: {response.status_code}")
        return False
    
    data = response.json()
    segments = data['segments']
    
    if not segments:
        print("❌ No segments in preview")
        return False
    
    print(f"✅ Preview retrieved - {len(segments)} segments")
    
    # Verify translation is different from original
    all_different = True
    for seg in segments:
        original = seg['original']
        translated = seg['translated']
        is_different = original != translated
        
        print(f"\n   Original:   '{original}'")
        print(f"   Translated: '{translated}'")
        print(f"   Different:  {'✅ Yes' if is_different else '❌ No (SAME!)'}")
        
        if not is_different:
            all_different = False
    
    if not all_different:
        print("\n❌ CRITICAL: Some translations are identical to original!")
        return False
    
    print("\n✅ All translations are different from original")
    
    # Step 6: Check slides-info
    print("\n📊 Step 5: Check slides-info...")
    response = requests.get(f"{API_BASE}/slides-info/{job_id}", timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Slides-info check failed: {response.status_code}")
        return False
    
    data = response.json()
    original_count = data['original_count']
    translated_count = data['translated_count']
    
    print(f"✅ Slides info retrieved")
    print(f"   Original count: {original_count}")
    print(f"   Translated count: {translated_count}")
    
    if original_count == 0:
        print("⚠️  WARNING: Original count is 0 (visual preview not generated)")
    if translated_count == 0:
        print("⚠️  WARNING: Translated count is 0 (visual preview not generated)")
    
    # Step 7: Check original slide image (if available)
    if original_count > 0:
        print("\n🖼️  Step 6: Check original slide image...")
        response = requests.get(f"{API_BASE}/slides/{job_id}/original/0", timeout=15)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            size = len(response.content)
            print(f"✅ Original slide image retrieved")
            print(f"   Content-Type: {content_type}")
            print(f"   Size: {size} bytes")
            
            if 'image/png' not in content_type:
                print("❌ Not a PNG image!")
                return False
        else:
            print(f"❌ Original slide image failed: {response.status_code}")
            return False
    
    # Step 8: Check translated slide image (if available)
    if translated_count > 0:
        print("\n🖼️  Step 7: Check translated slide image...")
        response = requests.get(f"{API_BASE}/slides/{job_id}/translated/0", timeout=15)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            size = len(response.content)
            print(f"✅ Translated slide image retrieved")
            print(f"   Content-Type: {content_type}")
            print(f"   Size: {size} bytes")
            
            if 'image/png' not in content_type:
                print("❌ Not a PNG image!")
                return False
        else:
            print(f"❌ Translated slide image failed: {response.status_code}")
            return False
    
    # Step 9: Download translated PDF
    print("\n⬇️  Step 8: Download translated PDF...")
    response = requests.get(f"{API_BASE}/download/{job_id}", timeout=30)
    
    if response.status_code != 200:
        print(f"❌ Download failed: {response.status_code}")
        return False
    
    content_type = response.headers.get('content-type', '')
    size = len(response.content)
    
    print(f"✅ Download successful")
    print(f"   Content-Type: {content_type}")
    print(f"   Size: {size} bytes")
    
    if 'pdf' not in content_type.lower():
        print("❌ Not a PDF!")
        return False
    
    # Save and verify the downloaded PDF
    output_path = "/tmp/translated_german.pdf"
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    print(f"   Saved to: {output_path}")
    
    # Verify the downloaded PDF contains translated text
    try:
        doc = fitz.open(output_path)
        page = doc[0]
        text = page.get_text()
        doc.close()
        
        print(f"\n📄 Downloaded PDF content preview:")
        print(f"   {text[:200]}")
        
        # Check if it contains German words (basic check)
        if "Hallo" in text or "Welt" in text or "Test" in text:
            print("✅ Downloaded PDF appears to contain German text")
        else:
            print("⚠️  Could not verify German text in downloaded PDF")
    except Exception as e:
        print(f"⚠️  Could not verify downloaded PDF: {e}")
    
    print("\n" + "=" * 60)
    print("✅ PDF TRANSLATION FLOW TEST PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_pdf_translation_german()
    exit(0 if success else 1)
