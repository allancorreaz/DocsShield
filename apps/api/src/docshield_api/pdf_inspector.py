"""Deterministic first-pass PDF inspection. Documents are always untrusted data."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from typing import Any

import fitz

MAX_PAGES = 250
MAX_TEXT_CHARS = 2_000_000
MIN_FONT_SIZE_PT = 3.0
LIGHT_COLOR_THRESHOLD = 0xEEEEEE

PROMPT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prompt.override_instructions", re.compile(
        r"\b(ignore|disregard|override|forget)\b.{0,100}\b(previous|prior|above|system|developer|all)\b.{0,40}\b(instructions?|prompts?|rules?)\b",
        re.IGNORECASE | re.DOTALL)),
    ("prompt.role_manipulation", re.compile(
        r"\b(you are now|act as|pretend to be)\b.{0,100}\b(system|developer|administrator|assistant|model)\b",
        re.IGNORECASE | re.DOTALL)),
    ("prompt.data_exfiltration", re.compile(
        r"\b(reveal|print|output|disclose|expose)\b.{0,100}\b(secret|secrets|password|credentials|api key|system prompt)\b",
        re.IGNORECASE | re.DOTALL)),
    ("prompt.task_redirection", re.compile(
        r"\b(if|when)\b.{0,100}\b(ai|assistant|language model|llm)\b.{0,100}\b(then|must|should)\b",
        re.IGNORECASE | re.DOTALL)),
)


class PDFInspectionError(ValueError):
    """Raised when a PDF cannot be inspected within configured limits."""


def _iter_spans(page: fitz.Page) -> Iterator[dict[str, Any]]:
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            yield from line.get("spans", [])


def _finding(*, detector_id: str, title: str, severity: str, confidence: str,
             page_number: int, text: str, bbox: list[float] | None,
             explanation: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "detector_id": detector_id, "title": title, "severity": severity,
        "confidence": confidence, "page": page_number,
        "text_excerpt": text[:300], "bbox": bbox,
        "explanation": explanation, "evidence": evidence or {},
    }


def inspect_pdf(data: bytes) -> dict[str, Any]:
    """Inspect PDF spans and return findings with explicit coverage limitations."""
    if not data.startswith(b"%PDF-"):
        raise PDFInspectionError("The uploaded file does not have a valid PDF signature.")

    sha256 = hashlib.sha256(data).hexdigest()
    findings: list[dict[str, Any]] = []
    extracted_chars = 0
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PDFInspectionError("The PDF could not be parsed.") from exc

    try:
        if document.is_encrypted:
            raise PDFInspectionError("Password-protected PDFs are not supported yet.")
        if document.page_count < 1:
            raise PDFInspectionError("The PDF contains no pages.")
        if document.page_count > MAX_PAGES:
            raise PDFInspectionError(f"The PDF exceeds the {MAX_PAGES}-page inspection limit.")

        for page_index, page in enumerate(document):
            page_number = page_index + 1
            rect = page.rect
            for span in _iter_spans(page):
                text = str(span.get("text", ""))
                if not text.strip():
                    continue
                extracted_chars += len(text)
                if extracted_chars > MAX_TEXT_CHARS:
                    raise PDFInspectionError("Extracted text exceeds the configured limit.")

                raw_bbox = span.get("bbox")
                bbox = [round(float(v), 2) for v in raw_bbox] if raw_bbox else None
                font_size = float(span.get("size", 0.0))
                color = int(span.get("color", 0))
                if 0 < font_size < MIN_FONT_SIZE_PT:
                    findings.append(_finding(
                        detector_id="pdf.geometry.tiny_text", title="Very small text",
                        severity="medium", confidence="high", page_number=page_number,
                        text=text, bbox=bbox,
                        explanation=f"Font size is below the {MIN_FONT_SIZE_PT:g} pt heuristic threshold; legitimate small print may also trigger.",
                        evidence={"font_size_pt": round(font_size, 2)}))

                if color >= LIGHT_COLOR_THRESHOLD:
                    findings.append(_finding(
                        detector_id="pdf.visual.light_text", title="Very light text",
                        severity="low", confidence="medium", page_number=page_number,
                        text=text, bbox=bbox,
                        explanation="Text color is close to white. Background pixels are not yet compared, so invisibility is not confirmed.",
                        evidence={"text_color": f"#{color:06X}"}))

                if bbox:
                    x0, y0, x1, y1 = bbox
                    if x0 < rect.x0 or y0 < rect.y0 or x1 > rect.x1 or y1 > rect.y1:
                        findings.append(_finding(
                            detector_id="pdf.geometry.off_page_text", title="Text extends outside the page",
                            severity="medium", confidence="high", page_number=page_number,
                            text=text, bbox=bbox,
                            explanation="Text bounding box extends beyond page boundaries; this may be intentional layout content.",
                            evidence={"page_rect": [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]}))

                normalized = " ".join(text.split())
                for detector_id, pattern in PROMPT_PATTERNS:
                    match = pattern.search(normalized)
                    if match:
                        findings.append(_finding(
                            detector_id=detector_id, title="Potential AI-directed instruction",
                            severity="high", confidence="medium", page_number=page_number,
                            text=normalized, bbox=bbox,
                            explanation="Text matches a heuristic pattern associated with AI task redirection; human review is required.",
                            evidence={"matched_text": match.group(0)[:200]}))

        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        highest = max((f["severity"] for f in findings), key=lambda v: order[v], default="none")
        return {
            "status": "completed",
            "file": {"format": "pdf", "sha256": sha256, "size_bytes": len(data), "page_count": document.page_count},
            "summary": {"findings_count": len(findings), "highest_severity": highest, "extracted_characters": extracted_chars},
            "findings": findings,
            "coverage": {
                "text_spans": True, "font_color_heuristic": True, "font_size_heuristic": True,
                "page_geometry": True, "prompt_pattern_heuristics": True,
                "rendered_pixel_comparison": False, "ocr": False,
                "pdf_object_forensics": False, "transparency_analysis": False,
            },
            "limitations": [
                "Light text is not confirmed invisible because background pixels are not compared.",
                "Pattern matching can produce false positives and false negatives.",
                "OCR, rendered-page correlation, transparency and comprehensive PDF object analysis are not implemented.",
                "No findings does not certify that a document is safe.",
            ],
        }
    finally:
        document.close()
