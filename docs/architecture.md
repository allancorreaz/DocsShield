# DocsShield Architecture

## Goals

DocsShield inspects untrusted documents before they are supplied to AI systems. The same inspection engine should be reusable by hosted and local/private deployments.

## Current implementation

The API currently provides:
- `GET /health`: process health check.
- `POST /v1/scans/pdf`: bounded upload and initial deterministic PDF inspection.
- PDF text-span extraction, font-size heuristics, light-text heuristics, page-boundary checks, and suspicious instruction pattern matching.
- SHA-256 fingerprint and structured findings with page locations.
- Unit and API tests for the initial detector set.

The PDF endpoint currently parses files inside the API process. It is a development baseline, not a hardened production service.

## Target components

### Web application
- Next.js and TypeScript.
- Handles user interaction, uploads, scan history, and evidence presentation.
- Does not parse untrusted document formats in the browser as a security boundary.

### API
- Python and FastAPI.
- Authenticates callers, validates upload metadata, creates scan jobs, and exposes results.
- Current PDF endpoint is synchronous and intended only for development.

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

1. Receive and validate file type using content inspection, not filename alone.
2. Enforce upload, page-count, and extraction limits.
3. Compute a cryptographic hash.
4. Inspect the package/format structure safely.
5. Extract text, metadata, styles, coordinates, and embedded objects.
6. Render pages in an isolated environment.
7. Run OCR where applicable.
8. Correlate extracted text with rendered visibility and geometry.
9. Apply deterministic detectors and classify findings.
10. Produce an evidence-based report with page/element location and detector details.
11. Record coverage, skipped checks, and limitations.

## Trust boundaries

- Uploaded files are untrusted.
- Extracted text is untrusted data.
- Text that resembles instructions must never alter scanner behavior.
- Parsers must not have network access by default.
- Production parsing must be isolated from the API and other tenants.
- Any future LLM-assisted classifier must receive document content as untrusted data and must not control tools or workflow decisions.
- A successful scan is not proof that a document is harmless.

## Initial PDF detector rules

| Detector ID | Signal | Initial severity | Important limitation |
|---|---|---|---|
| `pdf.visual.light_text` | Very light text color | Low | Background pixels are not yet compared |
| `pdf.geometry.tiny_text` | Font size below 3 pt | Medium | Legitimate footnotes may trigger |
| `pdf.geometry.off_page_text` | Span bounding box outside page | Medium | Some layouts intentionally bleed |
| `prompt.override_instructions` | Heuristic instruction override phrase | High | Pattern matching is not semantic proof |
| `prompt.role_manipulation` | Heuristic role/persona manipulation | High | False positives and false negatives possible |
| `prompt.data_exfiltration` | Heuristic request to reveal secrets | High | Context determines intent |
| `prompt.task_redirection` | AI-directed conditional instruction | High | Not every match is malicious |

Severity is a review priority, not a probability or legal conclusion. Confidence is represented separately.

## Initial DOCX inspection plan

Inspect ZIP package safely and parse OOXML parts:
- document body, headers, footers, footnotes, endnotes;
- runs and styles, including hidden text properties and font color;
- comments and tracked changes;
- text boxes and drawing objects;
- relationships and embedded files;
- metadata and custom XML where relevant.

## Non-goals for the first milestones

- Claiming perfect detection.
- Automatically sanitizing and replacing the original document.
- Sending confidential files to external AI services.
- Treating a single keyword match as proof of malicious intent.
