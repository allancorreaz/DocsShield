# Initial Architecture

## Goals

DocsShield must inspect untrusted documents without treating document content as executable instructions. The same inspection engine should be reusable by hosted and local deployments.

## Components

### Web application
- Next.js and TypeScript.
- Handles user interaction, uploads, scan history, and evidence presentation.
- Does not parse untrusted document formats in the browser as a security boundary.

### API
- Python and FastAPI.
- Authenticates callers, validates upload metadata, creates scan jobs, and exposes results.
- Does not perform long-running parsing inside request handlers.

### Inspection workers
- Celery workers backed by Redis.
- Process files in isolated containers or processes with strict CPU, memory, file-size, page-count, and execution-time limits.
- No outbound network access during document parsing by default.
- Use temporary directories with safe filenames and cleanup.

### Storage
- PostgreSQL stores users, scan metadata, findings, audit events, and processing state.
- Local filesystem storage for local deployments.
- S3-compatible object storage for hosted deployments.
- Original files and derived artifacts must have explicit retention and deletion policies.

## Inspection pipeline

1. Receive and validate the file type using content inspection, not filename alone.
2. Compute a cryptographic hash and preserve the original as immutable evidence.
3. Inspect the container/package structure safely.
4. Extract text, metadata, styles, coordinates, and embedded objects.
5. Render pages in an isolated environment.
6. Run OCR where applicable.
7. Correlate extracted text with rendered visibility and geometry.
8. Apply deterministic detectors and classify findings.
9. Produce an evidence-based report with page/element location and detector details.
10. Record coverage, skipped checks, and limitations.

## Trust boundaries

- Uploaded files are untrusted.
- Extracted text is untrusted data.
- Text that resembles instructions must never alter scanner behavior.
- Any future LLM-assisted classifier must receive document content as quoted/untrusted data and must not control tools or workflow decisions.
- A successful scan is not proof that a document is safe.

## Initial format scope

### PDF
Inspect text spans, font size, color, opacity, bounding boxes, clipping, optional-content groups, annotations, form fields, attachments, metadata, and rendered appearance.

### DOCX
Inspect the ZIP package safely, XML parts, runs and styles, hidden text properties, font color, comments, tracked changes, headers, footers, footnotes, endnotes, text boxes, and embedded objects.

## Non-goals for the first milestone

- Claiming perfect detection.
- Automatically sanitizing and replacing the original document.
- Sending confidential files to external AI services.
- Treating a single keyword match as proof of malicious intent.
