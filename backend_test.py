#!/usr/bin/env python3
"""
Backend API Testing for PPTX Translator
Tests all API endpoints with real file upload and translation
"""

import requests
import sys
import os
import time
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches

# Use the public backend URL from frontend .env
BACKEND_URL = "https://admiring-wilson-10.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

class PPTXTranslatorTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.job_id = None
        self.test_file_path = None

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def create_test_pptx(self):
        """Create a small test PPTX file for testing"""
        try:
            prs = Presentation()
            
            # Slide 1
            slide1 = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
            slide1.shapes.title.text = "Test Presentation"
            content = slide1.placeholders[1].text_frame
            content.text = "This is a test slide for translation."
            
            # Slide 2
            slide2 = prs.slides.add_slide(prs.slide_layouts[1])
            slide2.shapes.title.text = "Second Slide"
            content2 = slide2.placeholders[1].text_frame
            content2.text = "Another text segment to translate."
            
            # Save test file
            self.test_file_path = "/tmp/test_presentation.pptx"
            prs.save(self.test_file_path)
            return True
        except Exception as e:
            print(f"Failed to create test PPTX: {e}")
            return False

    def test_health_check(self):
        """Test GET /api/ health check endpoint"""
        try:
            response = requests.get(f"{API_BASE}/", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                details += f", Response: {data}"
            return self.log_test("Health Check", success, details)
        except Exception as e:
            return self.log_test("Health Check", False, f"Error: {str(e)}")

    def test_upload_pptx(self):
        """Test POST /api/upload endpoint"""
        if not self.test_file_path or not os.path.exists(self.test_file_path):
            return self.log_test("Upload PPTX", False, "Test file not found")
        
        try:
            with open(self.test_file_path, 'rb') as f:
                files = {'file': ('test.pptx', f, 'application/vnd.openxmlformats-officedocument.presentationml.presentation')}
                response = requests.post(f"{API_BASE}/upload", files=files, timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                self.job_id = data.get('id')
                details += f", Job ID: {self.job_id}, Segments: {data.get('total_segments')}"
            else:
                details += f", Error: {response.text}"
                
            return self.log_test("Upload PPTX", success, details)
        except Exception as e:
            return self.log_test("Upload PPTX", False, f"Error: {str(e)}")

    def test_upload_invalid_file(self):
        """Test upload with invalid file type"""
        try:
            # Create a fake txt file
            fake_file = b"This is not a PPTX file"
            files = {'file': ('test.txt', fake_file, 'text/plain')}
            response = requests.post(f"{API_BASE}/upload", files=files, timeout=10)
            
            # Should return 400 for invalid file type
            success = response.status_code == 400
            details = f"Status: {response.status_code}"
            return self.log_test("Upload Invalid File", success, details)
        except Exception as e:
            return self.log_test("Upload Invalid File", False, f"Error: {str(e)}")

    def test_start_translation(self):
        """Test POST /api/translate/{job_id} endpoint"""
        if not self.job_id:
            return self.log_test("Start Translation", False, "No job ID available")
        
        try:
            payload = {
                "target_language": "Spanish",
                "tone": "formal"
            }
            response = requests.post(f"{API_BASE}/translate/{self.job_id}", json=payload, timeout=10)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                details += f", Response: {data}"
            else:
                details += f", Error: {response.text}"
                
            return self.log_test("Start Translation", success, details)
        except Exception as e:
            return self.log_test("Start Translation", False, f"Error: {str(e)}")

    def test_get_progress(self):
        """Test GET /api/progress/{job_id} endpoint"""
        if not self.job_id:
            return self.log_test("Get Progress", False, "No job ID available")
        
        try:
            response = requests.get(f"{API_BASE}/progress/{self.job_id}", timeout=10)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                details += f", Progress: {data.get('progress')}%, Status: {data.get('status')}"
            else:
                details += f", Error: {response.text}"
                
            return self.log_test("Get Progress", success, details)
        except Exception as e:
            return self.log_test("Get Progress", False, f"Error: {str(e)}")

    def test_wait_for_completion(self, max_wait=120):
        """Wait for translation to complete and test progress polling"""
        if not self.job_id:
            return self.log_test("Wait for Completion", False, "No job ID available")
        
        print(f"⏳ Waiting for translation to complete (max {max_wait}s)...")
        start_time = time.time()
        
        try:
            while time.time() - start_time < max_wait:
                response = requests.get(f"{API_BASE}/progress/{self.job_id}", timeout=10)
                if response.status_code != 200:
                    return self.log_test("Wait for Completion", False, f"Progress check failed: {response.status_code}")
                
                data = response.json()
                status = data.get('status')
                progress = data.get('progress', 0)
                
                print(f"   Progress: {progress}%, Status: {status}")
                
                if status == "completed":
                    return self.log_test("Wait for Completion", True, f"Completed in {time.time() - start_time:.1f}s")
                elif status == "error":
                    error_msg = data.get('error_message', 'Unknown error')
                    return self.log_test("Wait for Completion", False, f"Translation failed: {error_msg}")
                
                time.sleep(3)  # Wait 3 seconds between checks
            
            return self.log_test("Wait for Completion", False, f"Timeout after {max_wait}s")
        except Exception as e:
            return self.log_test("Wait for Completion", False, f"Error: {str(e)}")

    def test_get_preview(self):
        """Test GET /api/preview/{job_id} endpoint"""
        if not self.job_id:
            return self.log_test("Get Preview", False, "No job ID available")
        
        try:
            response = requests.get(f"{API_BASE}/preview/{self.job_id}", timeout=10)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                segments = data.get('segments', [])
                details += f", Segments: {len(segments)}"
                if segments:
                    details += f", Sample: '{segments[0].get('original', '')}' -> '{segments[0].get('translated', '')}'"
            else:
                details += f", Error: {response.text}"
                
            return self.log_test("Get Preview", success, details)
        except Exception as e:
            return self.log_test("Get Preview", False, f"Error: {str(e)}")

    def test_download_translated(self):
        """Test GET /api/download/{job_id} endpoint"""
        if not self.job_id:
            return self.log_test("Download Translated", False, "No job ID available")
        
        try:
            response = requests.get(f"{API_BASE}/download/{self.job_id}", timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                content_type = response.headers.get('content-type', '')
                content_length = len(response.content)
                details += f", Content-Type: {content_type}, Size: {content_length} bytes"
                
                # Verify it's a PPTX file
                if 'presentation' in content_type or content_length > 1000:
                    details += " (Valid PPTX)"
                else:
                    success = False
                    details += " (Invalid PPTX)"
            else:
                details += f", Error: {response.text}"
                
            return self.log_test("Download Translated", success, details)
        except Exception as e:
            return self.log_test("Download Translated", False, f"Error: {str(e)}")

    def test_invalid_job_id(self):
        """Test endpoints with invalid job ID"""
        fake_job_id = "invalid-job-id-12345"
        
        try:
            # Test progress with invalid ID
            response = requests.get(f"{API_BASE}/progress/{fake_job_id}", timeout=10)
            success1 = response.status_code == 404
            
            # Test preview with invalid ID
            response = requests.get(f"{API_BASE}/preview/{fake_job_id}", timeout=10)
            success2 = response.status_code == 404
            
            # Test download with invalid ID
            response = requests.get(f"{API_BASE}/download/{fake_job_id}", timeout=10)
            success3 = response.status_code == 404
            
            success = success1 and success2 and success3
            details = f"Progress: {success1}, Preview: {success2}, Download: {success3}"
            
            return self.log_test("Invalid Job ID Handling", success, details)
        except Exception as e:
            return self.log_test("Invalid Job ID Handling", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting PPTX Translator Backend Tests")
        print(f"📡 Testing API at: {API_BASE}")
        print("=" * 60)
        
        # Create test file
        if not self.create_test_pptx():
            print("❌ Failed to create test PPTX file. Exiting.")
            return False
        
        # Run tests in order
        tests = [
            self.test_health_check,
            self.test_upload_invalid_file,
            self.test_upload_pptx,
            self.test_start_translation,
            self.test_get_progress,
            self.test_wait_for_completion,
            self.test_get_preview,
            self.test_download_translated,
            self.test_invalid_job_id,
        ]
        
        for test in tests:
            test()
            print()  # Add spacing between tests
        
        # Cleanup
        if self.test_file_path and os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)
        
        # Summary
        print("=" * 60)
        print(f"📊 Backend Tests Summary: {self.tests_passed}/{self.tests_run} passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test runner"""
    tester = PPTXTranslatorTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())