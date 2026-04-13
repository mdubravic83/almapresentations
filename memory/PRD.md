# PRD - SlideTranslate: AI PPTX Translator

## Original Problem Statement
Build a web app where users upload a .pptx presentation and get it translated to a language of their choice using OpenAI o4-mini. Features: upload, language selection (popular list + custom), tone selection (formal/academic/general), progress bar, preview, download.

## Architecture
- **Backend**: FastAPI + python-pptx + OpenAI o4-mini + MongoDB
- **Frontend**: React + Tailwind CSS + Custom CSS (Swiss design)
- **Database**: MongoDB for job tracking and segment storage

## User Flow
1. Upload .pptx file (drag & drop or browse)
2. Select target language (17 preset + custom input)
3. Choose translation tone (Formal / Academic / General)
4. Click "Translate" → progress bar shows real-time progress
5. Preview translated text side-by-side (original vs. translated)
6. Download translated .pptx with preserved formatting

## What's Been Implemented (2026-01-13)
- Full backend API: upload, translate, progress, preview, download
- OpenAI o4-mini integration for AI translation
- PPTX text extraction and rebuild with formatting preservation
- Real-time progress tracking via MongoDB polling
- Swiss-style UI with Outfit + IBM Plex Sans fonts
- Responsive design for mobile/desktop
- Error handling and validation

## API Endpoints
- `POST /api/upload` - Upload .pptx file
- `POST /api/translate/{job_id}` - Start translation
- `GET /api/progress/{job_id}` - Translation progress
- `GET /api/preview/{job_id}` - Preview translated segments
- `GET /api/download/{job_id}` - Download translated .pptx

## Testing Status
- Backend: 100% (9/9 tests passed)
- Frontend: 95% (all features functional)

## Backlog / P1
- Support for .pdf and .docx formats
- Translation history/saved jobs
- Batch upload (multiple files)
- Custom glossary/terminology override

## Backlog / P2
- User accounts with translation history
- API rate limiting / usage tracking
- Translation memory for repeated phrases
- Side-by-side slide visual preview (not just text)
