"""PDF Editor backend API tests"""
import os
import io
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://doc-translate-ocr.preview.emergentagent.com').rstrip('/')
TEST_PDF = "/tmp/test_invoice2.pdf"


@pytest.fixture(scope="module")
def upload_response():
    """Upload a PDF and return the response data"""
    with open(TEST_PDF, "rb") as f:
        files = {"file": ("test_invoice2.pdf", f, "application/pdf")}
        r = requests.post(f"{BASE_URL}/api/editor/upload", files=files, timeout=60)
    assert r.status_code == 200, f"Upload failed: {r.status_code} {r.text}"
    return r.json()


# Editor: Upload
class TestEditorUpload:
    def test_upload_pdf(self, upload_response):
        data = upload_response
        assert "job_id" in data
        assert "page_count" in data
        assert "page_dims" in data
        assert data["page_count"] >= 1
        assert isinstance(data["page_dims"], list)
        assert len(data["page_dims"]) == data["page_count"]
        assert "width" in data["page_dims"][0]
        assert "height" in data["page_dims"][0]

    def test_upload_rejects_non_pdf(self):
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/editor/upload", files=files, timeout=30)
        assert r.status_code == 400


# Editor: Page render
class TestEditorPage:
    def test_get_page_image(self, upload_response):
        job_id = upload_response["job_id"]
        r = requests.get(f"{BASE_URL}/api/editor/page/{job_id}/0", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 1000  # PNG should have meaningful size

    def test_get_page_invalid_num(self, upload_response):
        job_id = upload_response["job_id"]
        r = requests.get(f"{BASE_URL}/api/editor/page/{job_id}/999", timeout=30)
        assert r.status_code == 404

    def test_get_page_invalid_job(self):
        r = requests.get(f"{BASE_URL}/api/editor/page/nonexistent-job-id/0", timeout=30)
        assert r.status_code == 404


# Editor: Save edits
class TestEditorSave:
    def test_save_with_whiteout_and_text(self, upload_response):
        job_id = upload_response["job_id"]
        edits = {
            "edits": [
                {
                    "type": "whiteout",
                    "page": 0,
                    "x": 50, "y": 50,
                    "width": 100, "height": 30,
                    "backgroundColor": "#ffffff",
                },
                {
                    "type": "text",
                    "page": 0,
                    "x": 60, "y": 60,
                    "width": 200, "height": 30,
                    "text": "TEST_EDITED_TEXT",
                    "fontSize": 14,
                    "fontColor": "#ff0000",
                    "bold": True,
                    "italic": False,
                },
            ]
        }
        r = requests.post(f"{BASE_URL}/api/editor/save/{job_id}", json=edits, timeout=60)
        assert r.status_code == 200, f"Save failed: {r.text}"
        data = r.json()
        assert data.get("status") == "saved"
        assert "download_url" in data

    def test_save_invalid_job(self):
        edits = {"edits": []}
        r = requests.post(f"{BASE_URL}/api/editor/save/nonexistent-job", json=edits, timeout=30)
        assert r.status_code == 404


# Editor: Download
class TestEditorDownload:
    def test_download_after_save(self, upload_response):
        job_id = upload_response["job_id"]
        # Ensure save happened
        edits = {"edits": [{"type": "text", "page": 0, "x": 50, "y": 50,
                            "width": 100, "height": 20, "text": "Hi",
                            "fontSize": 12, "fontColor": "#000000",
                            "bold": False, "italic": False}]}
        s = requests.post(f"{BASE_URL}/api/editor/save/{job_id}", json=edits, timeout=60)
        assert s.status_code == 200

        r = requests.get(f"{BASE_URL}/api/editor/download/{job_id}", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type") == "application/pdf"
        assert r.content[:4] == b"%PDF"

    def test_download_invalid_job(self):
        r = requests.get(f"{BASE_URL}/api/editor/download/nonexistent-job", timeout=30)
        assert r.status_code == 404
