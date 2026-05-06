# PRD - SlideTranslate: AI Document Translator & PDF Editor

## Original Problem Statement
Build a web app where users upload a .pptx presentation and get it translated using OpenAI o4-mini. Later expanded to support .docx and .pdf formats, plus visual slide preview. Additionally, a standalone PDF editor (sejda.com style) for editing invoices and documents - click-to-edit existing text, add new text, and whiteout (covering content).

## Architecture
- **Backend**: FastAPI + python-pptx + python-docx + PyMuPDF + OpenAI o4-mini + MongoDB
- **Frontend**: React + Custom CSS (Swiss design, Outfit + IBM Plex Sans fonts) + Fabric.js v7 (PDF editor canvas)
- **Tools**: LibreOffice (headless PPTX/DOCX→PDF), pdftoppm (PDF→PNG), tesseract-ocr (OCR)
- **Database**: MongoDB for job tracking and segment storage

## User Flow - Translation
1. Upload .pptx, .docx, or .pdf (drag & drop or browse)
2. Select target language (17 preset + custom input)
3. Choose translation tone (Formal / Academic / General)
4. Click "Translate" → progress bar shows real-time progress
5. Toggle between Visual Preview (side-by-side slides) and Text Preview
6. Download translated file with preserved formatting

## User Flow - PDF Editor
1. Click "PDF Editor" button in header
2. Upload PDF file (max 50MB, up to 20 pages)
3. **Double-click on existing text** → text becomes editable in-place (preserves font/style)
4. Edit text directly, then click away to confirm
5. Use Text tool to add NEW text anywhere (font size, color, bold, italic)
6. Use Whiteout tool to draw rectangle covering content (customizable color)
7. Undo/Delete actions available
8. Save edits → Download edited PDF

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

### v3 (2026-02-05)
- **OCR for image-based PDFs**: tesseract-ocr integration with design preservation
- **Docker deployment**: Dockerfile.backend, docker-compose.yml, .env.example
- **Unicode support**: LiberationSans font for Croatian/extended characters

### v4 (2026-02-05)
- **PDF Editor** (sejda.com style):
  - Upload PDF, render pages as images at 2x quality
  - Fabric.js v7 canvas overlay for interactive editing
  - Text tool: add/edit text with font size, color, bold, italic
  - Whiteout tool: draw rectangles to cover content with custom color
  - Undo/Delete functionality
  - Save edits to backend (PyMuPDF applies changes to actual PDF)
  - Download edited PDF
  - Page navigation for multi-page documents
  - **Click-to-edit existing text**: Backend extracts text blocks with positions/font info, frontend creates clickable hit areas, double-click activates inline editing
  - **Replace edit type**: Whiteouts original text bbox and inserts new text at same position with same font size/style
  - **Precise coordinate mapping**: pdfToCanvas = (imageWidth / pdfWidth) * displayScale

## API Endpoints - Translation
- `POST /api/upload` - Upload .pptx/.docx/.pdf file
- `POST /api/translate/{job_id}` - Start translation
- `GET /api/progress/{job_id}` - Translation progress
- `GET /api/preview/{job_id}` - Preview translated text segments
- `GET /api/slides-info/{job_id}` - Slide image counts
- `GET /api/slides/{job_id}/{version}/{index}` - Serve slide preview images
- `GET /api/download/{job_id}` - Download translated file

## API Endpoints - PDF Editor
- `POST /api/editor/upload` - Upload PDF for editing (returns job_id, page_count, page_dims)
- `GET /api/editor/page/{job_id}/{page_num}` - Get page as PNG image (2x resolution)
- `GET /api/editor/text-blocks/{job_id}/{page_num}` - Extract text with positions, font, color, bold/italic
- `POST /api/editor/save/{job_id}` - Apply edits (text/whiteout/replace) and save PDF
- `GET /api/editor/download/{job_id}` - Download edited PDF

## Testing Status
- Backend: 100% (15/15 editor tests passed)
- Frontend: 100% (15/15 editor flow steps passed)

## Backlog / P0
- Handle long replacement text that overflows original bbox (auto-expand)
- Add zoom in/out for editor canvas

## Backlog / P1
- Translation history/saved jobs
- Batch upload (multiple files)
- Custom glossary/terminology override
- Refactor PdfEditor.js into smaller components (Toolbar, Canvas, Upload)

## Backlog / P2
- User accounts with translation history
- API rate limiting / usage tracking
- Translation memory for repeated phrases
- Refactor server.py into modules (pdf_utils.py, ocr_utils.py, editor_utils.py)
- Cleanup temp files in /tmp/pdf_editor periodically
