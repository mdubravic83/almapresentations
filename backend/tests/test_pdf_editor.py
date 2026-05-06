"""PDF Editor backend API tests"""
import os
import io
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Read from frontend/.env as fallback
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip('/')
                break
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
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


# Editor: Text blocks (NEW - click-to-edit feature)
class TestEditorTextBlocks:
    def test_get_text_blocks(self, upload_response):
        job_id = upload_response["job_id"]
        r = requests.get(f"{BASE_URL}/api/editor/text-blocks/{job_id}/0", timeout=30)
        assert r.status_code == 200, f"Text blocks fetch failed: {r.text}"
        data = r.json()
        assert "blocks" in data
        assert isinstance(data["blocks"], list)
        assert len(data["blocks"]) > 0, "Expected text blocks for invoice PDF"

        # Validate block structure
        block = data["blocks"][0]
        for key in ["text", "x", "y", "width", "height", "fontSize",
                    "fontColor", "fontName", "bold", "italic"]:
            assert key in block, f"Missing key '{key}' in block"
        assert isinstance(block["text"], str)
        assert isinstance(block["x"], (int, float))
        assert isinstance(block["y"], (int, float))
        assert isinstance(block["fontSize"], (int, float))
        assert block["fontColor"].startswith("#")
        assert isinstance(block["bold"], bool)
        assert isinstance(block["italic"], bool)

    def test_text_blocks_invoice_content(self, upload_response):
        """Verify invoice text content is detected (e.g., 'Customer:' or similar)."""
        job_id = upload_response["job_id"]
        r = requests.get(f"{BASE_URL}/api/editor/text-blocks/{job_id}/0", timeout=30)
        assert r.status_code == 200
        all_text = " ".join(b["text"] for b in r.json()["blocks"]).lower()
        # The test invoice should contain customer-related text
        assert any(kw in all_text for kw in ["customer", "ivan", "consulting", "invoice", "horvat"]), \
            f"Expected invoice keywords in: {all_text[:300]}"

    def test_text_blocks_invalid_page(self, upload_response):
        job_id = upload_response["job_id"]
        r = requests.get(f"{BASE_URL}/api/editor/text-blocks/{job_id}/999", timeout=30)
        assert r.status_code == 404

    def test_text_blocks_invalid_job(self):
        r = requests.get(f"{BASE_URL}/api/editor/text-blocks/nonexistent-job/0", timeout=30)
        assert r.status_code == 404


# Editor: Replace edit type (NEW)
class TestEditorReplace:
    def test_save_with_replace_edit(self, upload_response):
        """Replace edit should whiteout original area and insert new text."""
        job_id = upload_response["job_id"]

        # Get a text block to replace
        rb = requests.get(f"{BASE_URL}/api/editor/text-blocks/{job_id}/0", timeout=30)
        assert rb.status_code == 200
        blocks = rb.json()["blocks"]
        assert len(blocks) > 0
        target = blocks[0]

        edits = {
            "edits": [
                {
                    "type": "replace",
                    "page": 0,
                    "x": target["x"],
                    "y": target["y"],
                    "width": target["width"],
                    "height": target["height"],
                    "text": "TEST_REPLACED",
                    "fontSize": target["fontSize"],
                    "fontColor": target["fontColor"],
                    "bold": target["bold"],
                    "italic": target["italic"],
                    "origX": target["x"],
                    "origY": target["y"],
                    "origWidth": target["width"],
                    "origHeight": target["height"],
                },
            ]
        }
        r = requests.post(f"{BASE_URL}/api/editor/save/{job_id}", json=edits, timeout=60)
        assert r.status_code == 200, f"Replace save failed: {r.text}"
        assert r.json().get("status") == "saved"

        # Download and verify replacement text appears in PDF
        d = requests.get(f"{BASE_URL}/api/editor/download/{job_id}", timeout=30)
        assert d.status_code == 200
        assert d.content[:4] == b"%PDF"

        # Extract text from downloaded PDF to verify replacement
        import fitz
        with open("/tmp/_test_replaced.pdf", "wb") as f:
            f.write(d.content)
        doc = fitz.open("/tmp/_test_replaced.pdf")
        text = doc[0].get_text()
        doc.close()
        assert "TEST_REPLACED" in text, f"Replacement text not found in PDF. Got: {text[:500]}"

    def test_replace_uses_orig_bbox_when_provided(self, upload_response):
        """Replace edit uses origX/origY/origWidth/origHeight for whiteout location."""
        job_id = upload_response["job_id"]
        edits = {
            "edits": [
                {
                    "type": "replace",
                    "page": 0,
                    "x": 100, "y": 100, "width": 50, "height": 20,
                    "text": "TEST_ORIG_BBOX",
                    "fontSize": 12,
                    "fontColor": "#000000",
                    "bold": False, "italic": False,
                    "origX": 50, "origY": 150,
                    "origWidth": 200, "origHeight": 25,
                },
            ]
        }
        r = requests.post(f"{BASE_URL}/api/editor/save/{job_id}", json=edits, timeout=60)
        assert r.status_code == 200
