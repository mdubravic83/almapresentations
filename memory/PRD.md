# PRD - SlideTranslate: AI Document Translator

## Original Problem Statement
Build a web app where users upload a .pptx presentation and get it translated using OpenAI o4-mini. Later expanded to support .docx and .pdf formats, plus visual slide preview.

## Architecture
- **Backend**: FastAPI + python-pptx + python-docx + PyMuPDF + OpenAI o4-mini + MongoDB
- **Frontend**: React + Custom CSS (Swiss design, Outfit + IBM Plex Sans fonts)
- **Tools**: LibreOffice (headless PPTX/DOCX→PDF), pdftoppm (PDF→PNG)
- **Database**: MongoDB for job tracking and segment storage

## User Flow
1. Upload .pptx, .docx, or .pdf (drag & drop or browse)
2. Select target language (17 preset + custom input)
3. Choose translation tone (Formal / Academic / General)
4. Click "Translate" → progress bar shows real-time progress
5. Toggle between Visual Preview (side-by-side slides) and Text Preview
6. Download translated file with preserved formatting

## What's Been Implemented

### v1 (2026-01-13)
- Full backend API: upload, translate, progress, preview, download
- OpenAI o4-mini integration for AI translation
- PPTX text extraction and rebuild with formatting preservation
- Real-time progress tracking via MongoDB polling
- Swiss-style UI with responsive design

### v2 (2026-01-13)
- **DOCX support**: python-docx extraction/rebuild with paragraph & table handling
- **PDF support**: PyMuPDF extraction/rebuild with text block overlay
- **Visual Slide Preview**: LibreOffice→PDF→PNG conversion, side-by-side comparison
- **Thumbnail navigation**: Strip of clickable thumbnails for quick slide navigation
- **Preview toggle**: Switch between Visual Preview and Text Preview modes
- **Format pills**: Upload zone shows .pptx .docx .pdf with file type badge

## API Endpoints
- `POST /api/upload` - Upload .pptx/.docx/.pdf file
- `POST /api/translate/{job_id}` - Start translation
- `GET /api/progress/{job_id}` - Translation progress
- `GET /api/preview/{job_id}` - Preview translated text segments
- `GET /api/slides-info/{job_id}` - Slide image counts (original/translated)
- `GET /api/slides/{job_id}/{version}/{index}` - Serve slide preview images
- `GET /api/download/{job_id}` - Download translated file

## Testing Status
- Backend: 100% (27/27 tests passed)
- Frontend: 100% (all features functional)

## Backlog / P1
- Translation history/saved jobs
- Batch upload (multiple files)
- Custom glossary/terminology override

## Backlog / P2
- User accounts with translation history
- API rate limiting / usage tracking
- Translation memory for repeated phrases
