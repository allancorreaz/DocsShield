# SPDX-License-Identifier: Apache-2.0
"""Deterministic first-pass PDF inspection.

Documents are always treated as untrusted data. The analyzer never executes
document instructions, embedded scripts, or external resources.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from statistics import median
from typing import Any

import fitz

MAX_PAGES = 250
MAX_TEXT_CHARS = 2_000_000
MAX_RENDER_PIXELS = 16_000_000
MIN_FONT_SIZE_PT = 3.0
LIGHT_COLOR_THRESHOLD = 0xEEEEEE
LOW_CONTRAST_THRESHOLD = 1.5
RENDER_SCALE = 1.0

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


def _srgb_channel(value: float) -> float:
    channel = value / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    red, green, blue = (_srgb_channel(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(
    foreground: tuple[float, float, float],
    background: tuple[float, float, float],
) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _estimated_background(
    pixmap: fitz.Pixmap,
    bbox: list[float],
    sample_bytes: bytes,
) -> tuple[float, float, float] | None:
    """Estimate local background from a narrow ring outside a text span."""
    if pixmap.n < 3:
        return None

    x0 = int(bbox[0] * RENDER_SCALE - pixmap.x)
    y0 = int(bbox[1] * RENDER_SCALE - pixmap.y)
    x1 = int(bbox[2] * RENDER_SCALE - pixmap.x)
    y1 = int(bbox[3] * RENDER_SCALE - pixmap.y)
    if x1 <= x0 or y1 <= y0:
        return None

    width, height = pixmap.width, pixmap.height
    ring = 3
    left, right = max(0, x0 - ring), min(width - 1, x1 + ring)
    top, bottom = max(0, y0 - ring), min(height - 1, y1 + ring)
    if right <= left or bottom <= top:
        return None

    points: list[tuple[int, int]] = []
    stride = max(1, (right - left + bottom - top) // 256)
    for x in range(left, right + 1, stride):
        if y0 - ring >= 0:
            points.append((x, max(0, y0 - ring)))
        if y1 + ring < height:
            points.append((x, min(height - 1, y1 + ring)))
    for y in range(top, bottom + 1, stride):
        if x0 - ring >= 0:
            points.append((max(0, x0 - ring), y))
        if x1 + ring < width:
            points.append((min(width - 1, x1 + ring), y))

    if len(points) < 8:
        return None

    samples: list[list[int]] = [[], [], []]
    for x, y in points:
        offset = (y * width + x) * pixmap.n
        for channel in range(3):
            samples[channel].append(sample_bytes[offset + channel])

    return tuple(float(median(channel)) for channel in samples)


def _rgb_from_pdf_color(color: int) -> tuple[float, float, float]:
    return (
        float((color >> 16) & 0xFF),
        float((color >> 8) & 0xFF),
        float(color & 0xFF),
    )


def inspect_pdf(data: bytes) -> dict[str, Any]:
    """Inspect PDF text spans and return evidence-based findings.

    The current renderer estimates background color from a small pixel ring
    around each text span. This is a heuristic, not a full semantic analysis
    of transparency, blend modes, clipping paths, or complex backgrounds.
    """
    if not data.startswith(b"%PDF-"):
        raise PDFInspectionError("The uploaded file does not have a valid PDF signature.")

    sha256 = hashlib.sha256(data).hexdigest()
    findings: list[dict[str, Any]] = []
    extracted_chars = 0
    rendered_pages = 0
    skipped_render_pages = 0

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
            pixmap: fitz.Pixmap | None = None
            pixmap_samples: bytes | None = None
            if rect.width > 0 and rect.height > 0 and rect.width * rect.height <= MAX_RENDER_PIXELS:
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False)
                    pixmap_samples = pixmap.samples
                    rendered_pages += 1
                except Exception:
                    skipped_render_pages += 1
            else:
                skipped_render_pages += 1

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
                        explanation="Text color is close to white. Local background comparison is evaluated separately.",
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

                    if pixmap is not None:
                        background = _estimated_background(pixmap, bbox, pixmap_samples or b"")
                        if background is not None:
                            foreground = _rgb_from_pdf_color(color)
                            ratio = _contrast_ratio(foreground, background)
                            if ratio < LOW_CONTRAST_THRESHOLD:
                                findings.append(_finding(
                                    detector_id="pdf.visual.low_contrast_text",
                                    title="Text has very low estimated contrast",
                                    severity="high",
                                    confidence="medium",
                                    page_number=page_number,
                                    text=text,
                                    bbox=bbox,
                                    explanation=(
                                        "The text color has a very low contrast ratio against "
                                        "the estimated local background sampled around its "
                                        "bounding box. Review the rendered page to confirm."
                                    ),
                                    evidence={
                                        "text_color": f"#{color:06X}",
                                        "estimated_background_rgb": [round(v) for v in background],
                                        "estimated_contrast_ratio": round(ratio, 3),
                                        "threshold": LOW_CONTRAST_THRESHOLD,
                                    },
                                ))

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
            "summary": {
                "findings_count": len(findings),
                "highest_severity": highest,
                "extracted_characters": extracted_chars,
            },
            "findings": findings,
            "coverage": {
                "text_spans": True,
                "font_color_heuristic": True,
                "font_size_heuristic": True,
                "page_geometry": True,
                "prompt_pattern_heuristics": True,
                "rendered_pixel_comparison": rendered_pages > 0,
                "rendered_pages": rendered_pages,
                "skipped_render_pages": skipped_render_pages,
                "ocr": False,
                "pdf_object_forensics": False,
                "transparency_analysis": False,
            },
            "limitations": [
                "Background color is estimated from a narrow pixel ring and may be inaccurate near images, gradients, borders, or overlapping elements.",
                "The contrast heuristic does not fully analyze transparency, blend modes, clipping paths, or text rendering modes.",
                "Pattern matching can produce false positives and false negatives.",
                "OCR, comprehensive PDF object analysis, and embedded-file inspection are not implemented.",
                "No findings does not certify that a document is safe.",
            ],
        }
    finally:
        document.close()
