# DocsShield

**Document security scanner for hidden content and prompt-injection risks.**

DocsShield is an open-source project designed to inspect documents before they are supplied to AI systems. Its goal is to identify hidden, visually deceptive, or otherwise suspicious content and produce evidence-based findings that a person can review.

> **Project status: early development / pre-alpha.** The initial repository foundation is being established. No document scanning capability should be considered production-ready yet.

## Why DocsShield?

A document may contain text that is not apparent during ordinary visual review: white text on a white background, tiny text, off-page objects, hidden layers, comments, tracked changes, or invisible Unicode characters. When an AI system extracts or processes that content, it may encounter instructions that a human reviewer did not see.

DocsShield aims to reduce this risk by inspecting both document structure and rendered appearance, then correlating the findings.

## Project principles

- **Evidence first:** findings must include the source, location, detection method, and supporting evidence.
- **No execution of document instructions:** document content is untrusted data, never instructions for the scanner.
- **Privacy by design:** support local/private processing and avoid sending document contents to third-party AI services.
- **Layered detection:** combine structural inspection, text extraction, rendering, OCR, and correlation.
- **Honest risk reporting:** no scan can guarantee that a document is safe. Reports must explain coverage and limitations.
- **Human review:** suspicious findings are presented for review; automated results do not replace professional judgment.

## Initial scope

### First formats
1. PDF — structural and visual inspection.
2. DOCX — package/XML inspection, text, styles, comments, and revision metadata.

### Planned formats
- XLSX
- PPTX
- PNG, JPEG, and TIFF
- Additional document and message formats after threat-model review.

## Planned architecture

- **Web application:** Next.js + TypeScript.
- **API and inspection engine:** Python + FastAPI.
- **Background processing:** Celery + Redis.
- **Metadata and audit records:** PostgreSQL.
- **Object storage:** local storage for private deployments; S3-compatible storage for hosted deployments.
- **Document processing:** isolated workers with resource limits and no network access by default.

The web and local deployments will use the same inspection engine.

## Repository layout

```text
apps/
  api/              FastAPI application
core/
  analyzers/        Format-specific analyzers
  detectors/        Detection rules
  extraction/       Text and metadata extraction
  rendering/        Document rendering
  correlation/      Cross-check extracted and visible content
  risk/             Risk classification
  reporting/        Evidence-based reports
workers/            Asynchronous processing
tests/
  fixtures/         Safe test documents and adversarial fixtures
  unit/
  integration/
  security/
docs/               Architecture, threat model, and development notes
```

The layout will be introduced incrementally as each component becomes testable.

## Development status

| Capability | Status |
|---|---|
| Repository foundation | In progress |
| API health endpoint | Initial scaffold |
| PDF inspection | Planned |
| DOCX inspection | Planned |
| Visual/text correlation | Planned |
| OCR integration | Planned |
| Risk scoring | Planned |
| Web dashboard | Planned |
| Local deployment | Planned |
| Security benchmark corpus | Planned |

## Running locally

The initial API scaffold requires Python 3.11 or newer.

```bash
cd apps/api
python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS**
```bash
source .venv/bin/activate
```

Install dependencies and run the API:

```bash
pip install -e ".[dev]"
uvicorn docshield_api.main:app --reload
```

Health check: `http://127.0.0.1:8000/health`

## Security

Please do not upload confidential documents, production legal records, or sensitive personal data to this early-development project. The initial scaffold is not a hardened document-processing service.

For vulnerability reports, see [SECURITY.md](SECURITY.md).

## License

DocsShield is distributed under the [Apache License 2.0](LICENSE).

## Disclaimer

DocsShield is a security-assistance tool under development. A clean scan does not prove that a document is harmless or free from prompt injection. Detection can produce false positives and false negatives. Always review important documents and use defense-in-depth controls in downstream AI systems.
