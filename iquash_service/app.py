import asyncio
import json
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from docling.document_converter import DocumentConverter

MAX_UPLOAD_BYTES = int(os.getenv('IQUASH_DOCLING_MAX_UPLOAD_BYTES', str(30 * 1024 * 1024)))
API_KEY = os.getenv('IQUASH_DOCLING_API_KEY', '').strip()

app = FastAPI(title='iQuash Docling Service', version='1.0.0', docs_url=None, redoc_url=None)

_converter: DocumentConverter | None = None
_converter_lock = Lock()
_inference_lock = asyncio.Lock()


class PageResult(BaseModel):
    page_index: int
    text: str
    labels: list[str] = []


class ParseResponse(BaseModel):
    engine: str
    document_type: Literal['pdf', 'image']
    page_count: int
    markdown: str
    pages: list[PageResult]
    structured: dict[str, Any] | None = None


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not API_KEY:
        raise HTTPException(status_code=503, detail='Docling service API key is not configured')
    if authorization != f'Bearer {API_KEY}':
        raise HTTPException(status_code=401, detail='Unauthorized')


def get_converter() -> DocumentConverter:
    global _converter
    if _converter is None:
        with _converter_lock:
            if _converter is None:
                _converter = DocumentConverter()
    return _converter


def _document_dict(document: Any) -> dict[str, Any]:
    for attr in ('export_to_dict', 'model_dump', 'dict'):
        candidate = getattr(document, attr, None)
        try:
            if not callable(candidate):
                continue
            if attr == 'model_dump':
                value = candidate(mode='json')
            else:
                value = candidate()
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return {}


def _page_count(document: Any, structured: dict[str, Any]) -> int:
    pages = getattr(document, 'pages', None)
    if isinstance(pages, (dict, list, tuple)):
        return max(1, len(pages))
    structured_pages = structured.get('pages')
    if isinstance(structured_pages, (dict, list, tuple)):
        return max(1, len(structured_pages))
    return 1


def _page_content(document: Any, page_count: int, markdown: str) -> list[PageResult]:
    text_by_page: dict[int, list[str]] = {}
    labels_by_page: dict[int, list[str]] = {}
    try:
        iterator = document.iterate_items()
        for entry in iterator:
            item = entry[0] if isinstance(entry, tuple) else entry
            text = getattr(item, 'text', None)
            label = getattr(item, 'label', None)
            prov = getattr(item, 'prov', None) or []
            page_no = None
            if prov:
                page_no = getattr(prov[0], 'page_no', None)
            try:
                page_no = int(page_no) if page_no is not None else None
            except (TypeError, ValueError):
                page_no = None
            if page_no is None or page_no < 1:
                continue
            if isinstance(text, str) and text.strip():
                text_by_page.setdefault(page_no, []).append(text.strip())
            if label is not None:
                label_text = str(label).strip()
                if label_text:
                    labels = labels_by_page.setdefault(page_no, [])
                    if label_text not in labels:
                        labels.append(label_text)
    except Exception:
        pass

    pages: list[PageResult] = []
    for page_no in range(1, page_count + 1):
        page_text = '\n'.join(text_by_page.get(page_no, [])).strip()
        if page_count == 1 and not page_text:
            page_text = markdown.strip()
        pages.append(
            PageResult(
                page_index=page_no - 1,
                text=page_text,
                labels=labels_by_page.get(page_no, [])[:50],
            )
        )
    return pages


def _convert(path: str, include_structured: bool) -> ParseResponse:
    result = get_converter().convert(path)
    document = result.document
    markdown = document.export_to_markdown()
    structured = _document_dict(document)
    page_count = _page_count(document, structured)
    suffix = Path(path).suffix.lower()
    return ParseResponse(
        engine='Docling',
        document_type='pdf' if suffix == '.pdf' else 'image',
        page_count=page_count,
        markdown=markdown,
        pages=_page_content(document, page_count, markdown),
        structured=structured if include_structured else None,
    )


@app.get('/health')
def health() -> dict[str, Any]:
    return {
        'ok': True,
        'service': 'iquash-docling',
        'engine': 'Docling',
        'converter_loaded': _converter is not None,
        'auth_configured': bool(API_KEY),
    }


@app.post('/v1/parse', response_model=ParseResponse, dependencies=[Depends(require_api_key)])
async def parse_document(file: UploadFile = File(...), include_structured: bool = False) -> ParseResponse:
    mime = (file.content_type or '').lower()
    is_pdf = mime == 'application/pdf'
    is_image = mime.startswith('image/')
    if not (is_pdf or is_image):
        raise HTTPException(status_code=415, detail='Only PDF and image files are supported')

    suffix = Path(file.filename or '').suffix.lower() or ('.pdf' if is_pdf else '.jpg')
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail='Empty file')
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail='File exceeds Docling upload limit')

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            temp_path = tmp.name
        async with _inference_lock:
            return await asyncio.to_thread(_convert, temp_path, include_structured)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f'Docling could not parse this document: {type(exc).__name__}') from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
