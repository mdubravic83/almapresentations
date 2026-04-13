from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from pptx import Presentation
from openai import AsyncOpenAI

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


# --- Models ---
class JobInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    filename: str
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

class PreviewSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    idx: int
    slide_num: int
    original: str
    translated: Optional[str] = None


# --- PPTX helpers ---
def extract_segments(pptx_path: str) -> list:
    """Extract all text segments from a PPTX in deterministic order."""
    prs = Presentation(pptx_path)
    segments = []
    idx = 0
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if hasattr(shape, 'has_text_frame') and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    full_text = "".join(r.text for r in para.runs)
                    if full_text.strip():
                        is_url = full_text.strip().startswith("http")
                        segments.append({
                            "idx": idx,
                            "slide_num": slide_idx + 1,
                            "original": full_text,
                            "translated": None,
                            "translatable": not is_url,
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
    """Rebuild PPTX with translated text, preserving formatting."""
    prs = Presentation(original_path)
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


# --- Translation logic ---
async def translate_batch(texts: list, target_language: str, tone: str) -> list:
    """Translate a batch of text segments using OpenAI o4-mini."""
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
- Preserve special characters like ↑ ↓ → and arrows
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
        # Strip markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            content = content.strip()
        result = json.loads(content)
        if isinstance(result, list) and len(result) == len(texts):
            return result
        logger.warning(f"Translation returned {len(result)} items, expected {len(texts)}")
        # Pad or trim
        while len(result) < len(texts):
            result.append(texts[len(result)])
        return result[:len(texts)]
    except Exception as e:
        logger.error(f"Translation batch failed: {e}")
        return texts  # Return originals as fallback


async def run_translation(job_id: str, target_language: str, tone: str):
    """Background task to translate all segments."""
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

            # Update segments in memory
            update_ops = {}
            for (orig_idx, _), translated_text in zip(batch, translated_texts):
                update_ops[f"segments.{orig_idx}.translated"] = translated_text

            translated_count += len(batch)
            progress = (translated_count / len(translatable)) * 100

            update_ops["translated_segments"] = translated_count
            update_ops["progress"] = progress

            await db.translation_jobs.update_one(
                {"id": job_id},
                {"$set": update_ops}
            )

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        # Mark non-translatable segments (URLs) as "translated" with original text
        final_ops = {}
        for i, s in enumerate(segments):
            if not s["translatable"]:
                final_ops[f"segments.{i}.translated"] = s["original"]

        final_ops["status"] = "completed"
        final_ops["progress"] = 100
        await db.translation_jobs.update_one({"id": job_id}, {"$set": final_ops})
        logger.info(f"Job {job_id} completed: {translated_count} segments translated")

    except Exception as e:
        logger.error(f"Translation job {job_id} failed: {e}")
        await db.translation_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "error", "error_message": str(e)}}
        )


# --- API Routes ---
@api_router.get("/")
async def root():
    return {"message": "PPTX Translator API"}


@api_router.post("/upload", response_model=JobInfo)
async def upload_pptx(file: UploadFile = File(...)):
    if not file.filename.endswith(".pptx"):
        raise HTTPException(400, "Only .pptx files are supported")

    job_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{job_id}.pptx"

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 50MB)")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        segments = extract_segments(str(file_path))
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse PPTX: {str(e)}")

    job_doc = {
        "id": job_id,
        "filename": file.filename,
        "file_path": str(file_path),
        "segments": segments,
        "total_segments": len(segments),
        "translated_segments": 0,
        "progress": 0,
        "status": "ready",
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.translation_jobs.insert_one(job_doc)

    return JobInfo(id=job_id, filename=file.filename, total_segments=len(segments), status="ready")


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


@api_router.get("/download/{job_id}")
async def download_translated(job_id: str):
    job = await db.translation_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(400, "Translation not yet completed")

    original_path = job["file_path"]
    if not Path(original_path).exists():
        raise HTTPException(404, "Original file not found")

    translations = {}
    for s in job["segments"]:
        if s.get("translated"):
            translations[s["idx"]] = s["translated"]

    output_path = str(UPLOAD_DIR / f"{job_id}_translated.pptx")
    rebuild_pptx(original_path, output_path, translations)

    original_name = job["filename"].replace(".pptx", "")
    lang = job.get("target_language", "translated")
    download_name = f"{original_name}_{lang}.pptx"

    return FileResponse(
        path=output_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
