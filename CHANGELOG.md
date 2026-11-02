# Changelog

All notable changes to DocsShield will be documented here.

The project is in pre-alpha. Version tags and GitHub releases will be created only after the corresponding functionality has been implemented and validated.

## Unreleased

### Added
- Comprehensive README with project purpose, detection scope, Mermaid workflows, architecture, API usage, security model, and roadmap.
- Initial deterministic PDF inspection module using PyMuPDF.
- PDF upload endpoint with a 20 MiB request limit and PDF signature validation.
- SHA-256 file fingerprint and structured findings with page locations, evidence, severity, and confidence.
- Initial heuristics for very light text, tiny text, off-page text, and AI-directed instruction patterns.
- Synthetic PDF fixtures and automated API/detector tests.
- SPDX Apache-2.0 identifiers in Python source and test files.

### Changed
- API package version advanced to 0.2.0.
- Architecture documentation updated to distinguish implemented behavior from planned production components.

### Limitations
- PDF parsing is synchronous inside the API process and is not production-hardened.
- Light-text findings do not yet compare the text against rendered background pixels.
- OCR, rendered-page correlation, transparency inspection, and comprehensive PDF object forensics are not implemented.
- DOCX analysis, isolated workers, persistent storage, authentication, and web UI remain planned.
