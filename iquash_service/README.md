# iQuash Docling Service

Private secondary document parser for iQuash.

Docling is used after or alongside PaddleOCR to provide an independent parse of PDFs and document images, including layout, reading order, tables, page structure and normalized Markdown.

## Endpoints

- `GET /health`
- `POST /v1/parse`

Authentication uses:

`Authorization: Bearer $IQUASH_DOCLING_API_KEY`

The parse response contains full Markdown, page count, per-page extracted text/labels and optional structured Docling JSON.

## Required environment

- `IQUASH_DOCLING_API_KEY` — long private secret shared with the iQuash backend.
- `PORT` — supplied by the container platform.
- `IQUASH_DOCLING_MAX_UPLOAD_BYTES` — optional, defaults to 30 MiB.

## Role in iQuash

1. PaddleOCR — primary OCR/layout engine.
2. Docling — secondary parser and independent cross-check.
3. iQuash Legal Intelligence — legal-document/type/jurisdiction/completeness consistency layer.

The service is intentionally separate from the Vercel Next.js application because local document models are too large for a normal serverless function.
