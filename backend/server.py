from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import asyncio
import subprocess
import base64
import glob
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from pptx import Presentation as PptxPresentation
from docx import Document as DocxDocument
import fitz  # PyMuPDF
from openai import AsyncOpenAI
from PIL import Image
import pytesseract
import io

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
UPLOAD_DIR = Path("/tmp/pptx_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pptx", ".docx", ".pdf"}


# ════════════════════════════════════════
# Models
# ════════════════════════════════════════
class JobInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    filename: str
    file_type: str
    total_segments: int
    status: str

class TranslateRequest(BaseModel):
    target_language: str
    tone: str = "formal"

class ProgressResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    status: str
    progress: float
    total_segments: int
    translated_segments: int
    error_message: Optional[str] = None


# ════════════════════════════════════════
# PPTX extraction & rebuild
# ════════════════════════════════════════
def extract_pptx_segments(path: str) -> list:
    prs = PptxPresentation(path)
    segments = []
    idx = 0
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if hasattr(shape, 'has_text_frame') and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    full_text = "".join(r.text for r in para.runs)
                    if full_text.strip():
                        segments.append({
                            "idx": idx,
                            "slide_num": slide_idx + 1,
                            "original": full_text,
                            "translated": None,
                            "translatable": not full_text.strip().startswith("http"),
                        })
                        idx += 1
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            full_text = "".join(r.text for r in para.runs)
                            if full_text.strip():
                                segments.append({
                                    "idx": idx,
                                    "slide_num": slide_idx + 1,
                                    "original": full_text,
                                    "translated": None,
                                    "translatable": True,
                                })
                                idx += 1
    return segments


def rebuild_pptx(original_path: str, output_path: str, translations: dict):
    prs = PptxPresentation(original_path)
    idx = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, 'has_text_frame') and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    full_text = "".join(r.text for r in para.runs)
                    if full_text.strip():
                        translated = translations.get(idx)
                        if translated:
                            runs = para.runs
                            if runs:
                                runs[0].text = translated
                                for r in runs[1:]:
                                    r.text = ""
                        idx += 1
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            full_text = "".join(r.text for r in para.runs)
                            if full_text.strip():
                                translated = translations.get(idx)
                                if translated:
                                    runs = para.runs
                                    if runs:
                                        runs[0].text = translated
                                        for r in runs[1:]:
                                            r.text = ""
                                idx += 1
    prs.save(output_path)


# ════════════════════════════════════════
# DOCX extraction & rebuild
# ════════════════════════════════════════
def extract_docx_segments(path: str) -> list:
    doc = DocxDocument(path)
    segments = []
    idx = 0
    page_num = 1
    line_count = 0

    # Extract paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            segments.append({
                "idx": idx,
                "slide_num": page_num,  # approximate page number
                "original": text,
                "translated": None,
                "translatable": not text.startswith("http"),
            })
            idx += 1
            line_count += 1
            # Rough page estimation (every ~35 lines)
            if line_count > 35:
                page_num += 1
                line_count = 0

    # Extract table cells
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    # Avoid duplicates from merged cells
                    if not segments or segments[-1]["original"] != text:
                        segments.append({
                            "idx": idx,
                            "slide_num": page_num,
                            "original": text,
                            "translated": None,
                            "translatable": True,
                        })
                        idx += 1
    return segments


def rebuild_docx(original_path: str, output_path: str, translations: dict):
    doc = DocxDocument(original_path)
    idx = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            translated = translations.get(idx)
            if translated and para.runs:
                para.runs[0].text = translated
                for r in para.runs[1:]:
                    r.text = ""
            idx += 1

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    translated = translations.get(idx)
                    if translated:
                        for p in cell.paragraphs:
                            if p.runs:
                                p.runs[0].text = translated
                                for r in p.runs[1:]:
                                    r.text = ""
                                translated = ""  # Only set in first paragraph of cell
                    idx += 1
    doc.save(output_path)


# ════════════════════════════════════════
# PDF extraction & rebuild
# ════════════════════════════════════════
def extract_pdf_segments(path: str) -> tuple:
    """Extract text segments from PDF. Returns (segments, is_ocr).
    Falls back to OCR if no text layer is found.
    """
    doc = fitz.open(path)
    segments = []
    idx = 0
    for page_num, page in enumerate(doc):
        blocks = page.get_text("blocks")
        for block in blocks:
            # block: (x0, y0, x1, y1, text, block_no, block_type)
            if block[6] == 0:  # text block
                text = block[4].strip()
                if text and not text.startswith("http"):
                    segments.append({
                        "idx": idx,
                        "slide_num": page_num + 1,
                        "original": text,
                        "translated": None,
                        "translatable": True,
                    })
                    idx += 1
    doc.close()

    # If no text found, fall back to OCR
    if not segments:
        logger.info(f"No text layer found in PDF, falling back to OCR: {path}")
        segments = extract_pdf_segments_ocr(path)
        return segments, True

    return segments, False


def extract_pdf_segments_ocr(path: str) -> list:
    """Extract text segments from image-based PDF using OCR (Tesseract).
    Returns segments with bounding box data for rebuilding.
    """
    doc = fitz.open(path)
    segments = []
    idx = 0
    render_dpi = 300

    for page_num, page in enumerate(doc):
        # Render page as high-res image for OCR
        pix = page.get_pixmap(dpi=render_dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        # OCR with bounding box data
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        # Group words into lines
        lines = {}
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if text and data['conf'][i] > 30:
                block_num = data['block_num'][i]
                line_num = data['line_num'][i]
                key = (block_num, line_num)
                if key not in lines:
                    lines[key] = {
                        'words': [],
                        'left': data['left'][i],
                        'top': data['top'][i],
                        'right': data['left'][i] + data['width'][i],
                        'bottom': data['top'][i] + data['height'][i],
                    }
                lines[key]['words'].append(text)
                lines[key]['left'] = min(lines[key]['left'], data['left'][i])
                lines[key]['top'] = min(lines[key]['top'], data['top'][i])
                lines[key]['right'] = max(lines[key]['right'], data['left'][i] + data['width'][i])
                lines[key]['bottom'] = max(lines[key]['bottom'], data['top'][i] + data['height'][i])

        # Group lines into blocks
        blocks = {}
        for (block_num, line_num), line_data in sorted(lines.items()):
            if block_num not in blocks:
                blocks[block_num] = {
                    'text': '',
                    'left': line_data['left'],
                    'top': line_data['top'],
                    'right': line_data['right'],
                    'bottom': line_data['bottom'],
                }
            line_text = ' '.join(line_data['words'])
            if blocks[block_num]['text']:
                blocks[block_num]['text'] += ' ' + line_text
            else:
                blocks[block_num]['text'] = line_text
            blocks[block_num]['left'] = min(blocks[block_num]['left'], line_data['left'])
            blocks[block_num]['top'] = min(blocks[block_num]['top'], line_data['top'])
            blocks[block_num]['right'] = max(blocks[block_num]['right'], line_data['right'])
            blocks[block_num]['bottom'] = max(blocks[block_num]['bottom'], line_data['bottom'])

        # Convert pixel coords to PDF points (72 DPI)
        scale = 72.0 / render_dpi
        page_rect = page.rect

        for block_num, b in sorted(blocks.items()):
            text = b['text'].strip()
            if not text or len(text) < 2:
                continue
            # Skip if it looks like OCR noise
            if text.startswith("http"):
                continue

            # Convert pixel coordinates to PDF point coordinates
            x0 = b['left'] * scale
            y0 = b['top'] * scale
            x1 = b['right'] * scale
            y1 = b['bottom'] * scale

            # Clamp to page bounds
            x0 = max(0, min(x0, page_rect.width))
            y0 = max(0, min(y0, page_rect.height))
            x1 = max(0, min(x1, page_rect.width))
            y1 = max(0, min(y1, page_rect.height))

            segments.append({
                "idx": idx,
                "slide_num": page_num + 1,
                "original": text,
                "translated": None,
                "translatable": True,
                "ocr_bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            })
            idx += 1

    doc.close()
    logger.info(f"OCR extracted {len(segments)} text segments")
    return segments


def rebuild_pdf(original_path: str, output_path: str, translations: dict, is_ocr: bool = False):
    """Rebuild PDF by overlaying translated text on original blocks."""
    doc = fitz.open(original_path)

    # Use Liberation Sans for Unicode support (Croatian, etc.)
    FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    FONT_BOLD_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_NAME = "libsans"
    FONT_BOLD_NAME = "libsansbold"

    if is_ocr:
        # For OCR-based (image) PDFs: preserve original pages intact,
        # add a clean translation page after each original page.

        # Group translations by page
        page_translations = {}
        for idx_key, tdata in translations.items():
            if not isinstance(tdata, dict):
                continue
            page_idx = tdata.get("page", 0)
            if page_idx not in page_translations:
                page_translations[page_idx] = []
            page_translations[page_idx].append(tdata)

        # Process pages in reverse order so inserting doesn't shift indices
        for page_idx in sorted(page_translations.keys(), reverse=True):
            segments = page_translations[page_idx]
            orig_page = doc[page_idx]
            page_width = orig_page.rect.width
            page_height = orig_page.rect.height

            # Insert a new translation page right after the original
            new_page = doc.new_page(pno=page_idx + 1, width=page_width, height=page_height)

            # Light background
            new_page.draw_rect(new_page.rect, color=None, fill=(0.98, 0.98, 0.97))

            margin = 50
            y_cursor = margin

            # Header
            header_rect = fitz.Rect(margin, y_cursor, page_width - margin, y_cursor + 30)
            new_page.insert_textbox(
                header_rect,
                f"TRANSLATION - Page {page_idx + 1}",
                fontsize=18,
                fontname=FONT_BOLD_NAME,
                fontfile=FONT_BOLD_PATH,
                color=(0.15, 0.15, 0.15),
                align=0,
            )
            y_cursor += 38

            # Separator line
            new_page.draw_line(
                fitz.Point(margin, y_cursor),
                fitz.Point(page_width - margin, y_cursor),
                color=(0.6, 0.6, 0.6),
                width=0.8,
            )
            y_cursor += 20

            # Add each translated segment
            for seg in segments:
                original = seg.get("original", "")
                translated = seg.get("text", "")
                if not translated:
                    continue

                available_height = page_height - y_cursor - margin
                if available_height < 100:
                    new_page = doc.new_page(pno=-1, width=page_width, height=page_height)
                    new_page.draw_rect(new_page.rect, color=None, fill=(0.98, 0.98, 0.97))
                    y_cursor = margin

                # Original text label
                label_rect = fitz.Rect(margin, y_cursor, page_width - margin, y_cursor + 16)
                new_page.insert_textbox(
                    label_rect,
                    "ORIGINAL:",
                    fontsize=8,
                    fontname=FONT_BOLD_NAME,
                    fontfile=FONT_BOLD_PATH,
                    color=(0.45, 0.45, 0.45),
                    align=0,
                )
                y_cursor += 17

                # Original text
                orig_display = original[:400]
                chars_per_line = max(1, int((page_width - 2 * margin) / 6))
                est_lines = max(1, (len(orig_display) // chars_per_line) + 1)
                orig_height = max(30, est_lines * 16)

                orig_rect = fitz.Rect(margin, y_cursor, page_width - margin, y_cursor + orig_height)
                new_page.insert_textbox(
                    orig_rect,
                    orig_display,
                    fontsize=10,
                    fontname=FONT_NAME,
                    fontfile=FONT_PATH,
                    color=(0.4, 0.4, 0.4),
                    align=0,
                )
                y_cursor += orig_height + 8

                # Translated text label
                label_rect = fitz.Rect(margin, y_cursor, page_width - margin, y_cursor + 16)
                new_page.insert_textbox(
                    label_rect,
                    "TRANSLATED:",
                    fontsize=8,
                    fontname=FONT_BOLD_NAME,
                    fontfile=FONT_BOLD_PATH,
                    color=(0.05, 0.4, 0.25),
                    align=0,
                )
                y_cursor += 17

                # Translated text
                trans_display = translated[:400]
                est_lines = max(1, (len(trans_display) // chars_per_line) + 1)
                trans_height = max(30, est_lines * 18)

                trans_rect = fitz.Rect(margin, y_cursor, page_width - margin, y_cursor + trans_height)
                new_page.insert_textbox(
                    trans_rect,
                    trans_display,
                    fontsize=12,
                    fontname=FONT_BOLD_NAME,
                    fontfile=FONT_BOLD_PATH,
                    color=(0.05, 0.05, 0.05),
                    align=0,
                )
                y_cursor += trans_height + 16

                # Separator between segments
                new_page.draw_line(
                    fitz.Point(margin + 30, y_cursor),
                    fitz.Point(page_width - margin - 30, y_cursor),
                    color=(0.82, 0.82, 0.82),
                    width=0.4,
                )
                y_cursor += 16

    else:
        # Standard text-layer PDF rebuild
        idx = 0
        for page in doc:
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] == 0:
                    text = block[4].strip()
                    if text and not text.startswith("http"):
                        translated = translations.get(idx)
                        if translated:
                            rect = fitz.Rect(block[0], block[1], block[2], block[3])
                            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                            rect_height = rect.height
                            font_size = min(rect_height * 0.8, 11)
                            font_size = max(font_size, 6)
                            page.insert_textbox(
                                rect,
                                translated,
                                fontsize=font_size,
                                fontname=FONT_NAME,
                                fontfile=FONT_PATH,
                                color=(0, 0, 0),
                                align=0,
                            )
                        idx += 1

    doc.save(output_path)
    doc.close()


# ════════════════════════════════════════
# Visual preview generation
# ════════════════════════════════════════
def generate_slide_images(file_path: str, file_type: str, job_id: str, suffix: str = "original") -> list:
    """Convert document to images for visual preview.
    Returns list of image file paths.
    """
    images_dir = UPLOAD_DIR / f"{job_id}_{suffix}_images"
    images_dir.mkdir(exist_ok=True)

    pdf_path = None

    if file_type == "pdf":
        pdf_path = file_path
    elif file_type in ("pptx", "docx"):
        # Convert to PDF using LibreOffice
        pdf_output_dir = UPLOAD_DIR / f"{job_id}_pdf"
        pdf_output_dir.mkdir(exist_ok=True)
        try:
            result = subprocess.run(
                [
                    "libreoffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(pdf_output_dir), file_path
                ],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "HOME": "/tmp"}
            )
            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr}")
                return []
            # Find the generated PDF
            base_name = Path(file_path).stem
            pdf_candidates = list(pdf_output_dir.glob(f"{base_name}*.pdf"))
            if not pdf_candidates:
                logger.error("No PDF generated by LibreOffice")
                return []
            pdf_path = str(pdf_candidates[0])
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice conversion timed out")
            return []
        except Exception as e:
            logger.error(f"LibreOffice conversion error: {e}")
            return []

    if not pdf_path:
        return []

    # Convert PDF to images using pdftoppm
    try:
        output_prefix = str(images_dir / "slide")
        subprocess.run(
            [
                "pdftoppm", "-png", "-r", "150",
                "-l", "10",  # Limit to first 10 pages for preview
                pdf_path, output_prefix
            ],
            capture_output=True, timeout=60
        )
        image_files = sorted(glob.glob(f"{output_prefix}*.png"))
        return image_files
    except Exception as e:
        logger.error(f"PDF to image conversion error: {e}")
        return []


# ════════════════════════════════════════
# Translation logic
# ════════════════════════════════════════
async def translate_batch(texts: list, target_language: str, tone: str) -> list:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    tone_map = {
        "formal": "formal and professional",
        "academic": "academic and scholarly",
        "general": "general and natural-sounding",
    }
    tone_desc = tone_map.get(tone, "general and natural-sounding")

    prompt = f"""Translate the following text segments to {target_language}.
Tone: {tone_desc}.

Rules:
- Preserve all proper nouns, scientific/Latin terms, abbreviations, and URLs unchanged
- Preserve special characters like arrows and symbols
- Maintain original formatting, spacing, and punctuation style
- Return ONLY a valid JSON array of translated strings, in the same order as input
- The array must have exactly {len(texts)} elements

Input:
{json.dumps(texts, ensure_ascii=False)}"""

    try:
        response = await openai_client.chat.completions.create(
            model="o4-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            content = content.strip()
        result = json.loads(content)
        if isinstance(result, list) and len(result) == len(texts):
            return result
        while len(result) < len(texts):
            result.append(texts[len(result)])
        return result[:len(texts)]
    except Exception as e:
        logger.error(f"Translation batch failed: {e}")
        return texts


async def run_translation(job_id: str, target_language: str, tone: str):
    try:
        job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
        if not job:
            return

        segments = job["segments"]
        translatable = [(i, s) for i, s in enumerate(segments) if s["translatable"]]

        if not translatable:
            await db.translation_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "completed", "translated_segments": 0, "progress": 100}}
            )
            return

        batch_size = 20
        translated_count = 0

        for batch_start in range(0, len(translatable), batch_size):
            batch = translatable[batch_start:batch_start + batch_size]
            texts = [s["original"] for _, s in batch]
            translated_texts = await translate_batch(texts, target_language, tone)

            update_ops = {}
            for (orig_idx, _), translated_text in zip(batch, translated_texts):
                update_ops[f"segments.{orig_idx}.translated"] = translated_text

            translated_count += len(batch)
            progress = (translated_count / len(translatable)) * 100
            update_ops["translated_segments"] = translated_count
            update_ops["progress"] = progress

            await db.translation_jobs.update_one({"id": job_id}, {"$set": update_ops})
            await asyncio.sleep(0.5)

        # Non-translatable segments keep original
        final_ops = {}
        for i, s in enumerate(segments):
            if not s["translatable"]:
                final_ops[f"segments.{i}.translated"] = s["original"]

        final_ops["status"] = "completed"
        final_ops["progress"] = 100
        await db.translation_jobs.update_one({"id": job_id}, {"$set": final_ops})

        # Generate translated file and its preview images
        try:
            job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
            is_ocr = job.get("is_ocr", False)

            file_type = job["file_type"]
            original_path = job["file_path"]
            translated_path = str(UPLOAD_DIR / f"{job_id}_translated.{file_type}")

            if file_type == "pdf" and is_ocr:
                # For OCR PDFs, build translations dict with bbox, page, and original text
                translations = {}
                for s in job["segments"]:
                    if s.get("translated") and s.get("ocr_bbox"):
                        translations[s["idx"]] = {
                            "text": s["translated"],
                            "bbox": s["ocr_bbox"],
                            "page": s["slide_num"] - 1,  # 0-indexed
                            "original": s["original"],
                        }
                rebuild_pdf(original_path, translated_path, translations, is_ocr=True)
            else:
                # Standard rebuild for text-based files
                translations = {}
                for s in job["segments"]:
                    if s.get("translated"):
                        translations[s["idx"]] = s["translated"]

                if file_type == "pptx":
                    rebuild_pptx(original_path, translated_path, translations)
                elif file_type == "docx":
                    rebuild_docx(original_path, translated_path, translations)
                elif file_type == "pdf":
                    rebuild_pdf(original_path, translated_path, translations, is_ocr=False)

            # Generate visual preview images for translated file
            translated_images = generate_slide_images(translated_path, file_type, job_id, "translated")
            translated_image_paths = [str(p) for p in translated_images]
            await db.translation_jobs.update_one(
                {"id": job_id},
                {"$set": {"translated_file_path": translated_path, "translated_images": translated_image_paths}}
            )
        except Exception as e:
            logger.error(f"Post-translation processing error: {e}")

        logger.info(f"Job {job_id} completed: {translated_count} segments translated")

    except Exception as e:
        logger.error(f"Translation job {job_id} failed: {e}")
        await db.translation_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "error", "error_message": str(e)}}
        )


# ════════════════════════════════════════
# API Routes
# ════════════════════════════════════════
@api_router.get("/")
async def root():
    return {"message": "PPTX Translator API"}


@api_router.post("/upload", response_model=JobInfo)
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")

    job_id = str(uuid.uuid4())
    file_type = ext.lstrip(".")
    file_path = UPLOAD_DIR / f"{job_id}.{file_type}"

    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 100MB)")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        is_ocr = False
        if file_type == "pptx":
            segments = extract_pptx_segments(str(file_path))
        elif file_type == "docx":
            segments = extract_docx_segments(str(file_path))
        elif file_type == "pdf":
            segments, is_ocr = extract_pdf_segments(str(file_path))
        else:
            raise HTTPException(400, "Unsupported file type")
    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse file: {str(e)}")

    # Generate original preview images in background
    original_images = generate_slide_images(str(file_path), file_type, job_id, "original")
    original_image_paths = [str(p) for p in original_images]

    job_doc = {
        "id": job_id,
        "filename": file.filename,
        "file_type": file_type,
        "file_path": str(file_path),
        "segments": segments,
        "total_segments": len(segments),
        "translated_segments": 0,
        "progress": 0,
        "status": "ready",
        "error_message": None,
        "original_images": original_image_paths,
        "translated_images": [],
        "is_ocr": is_ocr,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.translation_jobs.insert_one(job_doc)

    return JobInfo(id=job_id, filename=file.filename, file_type=file_type, total_segments=len(segments), status="ready")


@api_router.post("/translate/{job_id}")
async def start_translation(job_id: str, req: TranslateRequest):
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] == "translating":
        raise HTTPException(400, "Translation already in progress")

    await db.translation_jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "translating",
            "progress": 0,
            "translated_segments": 0,
            "target_language": req.target_language,
            "tone": req.tone,
        }}
    )
    asyncio.create_task(run_translation(job_id, req.target_language, req.tone))
    return {"status": "translating", "job_id": job_id}


@api_router.get("/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str):
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    translatable_count = sum(1 for s in job["segments"] if s["translatable"])
    return ProgressResponse(
        id=job_id,
        status=job["status"],
        progress=job.get("progress", 0),
        total_segments=translatable_count,
        translated_segments=job.get("translated_segments", 0),
        error_message=job.get("error_message"),
    )


@api_router.get("/preview/{job_id}")
async def get_preview(job_id: str):
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")

    preview = []
    for s in job["segments"]:
        if s["translatable"] and s.get("translated"):
            preview.append({
                "idx": s["idx"],
                "slide_num": s["slide_num"],
                "original": s["original"],
                "translated": s["translated"],
            })
    return {"segments": preview, "status": job["status"]}


@api_router.get("/slides/{job_id}/{version}/{slide_index}")
async def get_slide_image(job_id: str, version: str, slide_index: int):
    """Serve slide preview images. version: 'original' or 'translated'."""
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")

    key = f"{version}_images"
    images = job.get(key, [])
    if slide_index < 0 or slide_index >= len(images):
        raise HTTPException(404, "Slide image not found")

    img_path = images[slide_index]
    if not Path(img_path).exists():
        raise HTTPException(404, "Image file not found")

    return FileResponse(img_path, media_type="image/png")


@api_router.get("/slides-info/{job_id}")
async def get_slides_info(job_id: str):
    """Return count of available slide images for original and translated."""
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "original_count": len(job.get("original_images", [])),
        "translated_count": len(job.get("translated_images", [])),
        "file_type": job.get("file_type", "pptx"),
    }


@api_router.get("/download/{job_id}")
async def download_translated(job_id: str):
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(400, "Translation not yet completed")

    file_type = job["file_type"]
    translated_path = job.get("translated_file_path")

    if not translated_path or not Path(translated_path).exists():
        # Rebuild on the fly
        original_path = job["file_path"]
        if not Path(original_path).exists():
            raise HTTPException(404, "Original file not found")

        is_ocr = job.get("is_ocr", False)
        translated_path = str(UPLOAD_DIR / f"{job_id}_translated.{file_type}")

        if file_type == "pdf" and is_ocr:
            translations = {}
            for s in job["segments"]:
                if s.get("translated") and s.get("ocr_bbox"):
                    translations[s["idx"]] = {
                        "text": s["translated"],
                        "bbox": s["ocr_bbox"],
                        "page": s["slide_num"] - 1,
                        "original": s["original"],
                    }
            rebuild_pdf(original_path, translated_path, translations, is_ocr=True)
        else:
            translations = {}
            for s in job["segments"]:
                if s.get("translated"):
                    translations[s["idx"]] = s["translated"]

            if file_type == "pptx":
                rebuild_pptx(original_path, translated_path, translations)
            elif file_type == "docx":
                rebuild_docx(original_path, translated_path, translations)
            elif file_type == "pdf":
                rebuild_pdf(original_path, translated_path, translations, is_ocr=False)

    original_name = Path(job["filename"]).stem
    lang = job.get("target_language", "translated")
    download_name = f"{original_name}_{lang}.{file_type}"

    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }

    return FileResponse(
        path=translated_path,
        filename=download_name,
        media_type=media_types.get(file_type, "application/octet-stream"),
    )


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
