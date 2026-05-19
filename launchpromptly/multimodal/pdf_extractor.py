"""
PdfExtractor — lightweight local PDF text extraction.

Uses pypdf (pure Python) for text extraction; falls back gracefully
if not installed. The scanner service handles deep analysis (PII, injection).

Extracted text is wrapped in <untrusted source="user-pdf"> tags (spotlighting)
to prevent prompt injection via embedded PDF content.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from .types import MediaPart

MAX_PDF_BYTES = 100 * 1024 * 1024  # 100 MB
PDF_MAGIC = b"%PDF-"


@dataclass
class PdfExtractResult:
    text: str
    page_count: int
    spotlighted_text: str
    sha256: str
    allowed: bool
    reason: Optional[str] = None


class PdfExtractor:
    def __init__(self, max_bytes: int = MAX_PDF_BYTES) -> None:
        self.max_bytes = max_bytes

    async def extract(self, part: MediaPart) -> PdfExtractResult:
        sha256 = hashlib.sha256(part.data).hexdigest()

        if part.size_bytes > self.max_bytes:
            return PdfExtractResult(
                text="", page_count=0, spotlighted_text="",
                sha256=sha256, allowed=False,
                reason=f"PDF too large: {part.size_bytes} bytes",
            )

        if not self._verify_magic(part.data):
            return PdfExtractResult(
                text="", page_count=0, spotlighted_text="",
                sha256=sha256, allowed=False,
                reason="Not a valid PDF (magic bytes mismatch)",
            )

        try:
            text, page_count = self._extract_text(part.data)
        except Exception as exc:
            return PdfExtractResult(
                text="", page_count=0, spotlighted_text="",
                sha256=sha256, allowed=True,
                reason=f"Extraction failed: {exc}",
            )

        spotlighted = self._spotlight(text, "user-pdf")
        return PdfExtractResult(
            text=text,
            page_count=page_count,
            spotlighted_text=spotlighted,
            sha256=sha256,
            allowed=True,
        )

    def _verify_magic(self, data: bytes) -> bool:
        return data[:5] == PDF_MAGIC

    def _spotlight(self, text: str, source: str) -> str:
        return f'<untrusted source="{source}">\n{text}\n</untrusted>'

    def _extract_text(self, data: bytes) -> tuple[str, int]:
        try:
            from pypdf import PdfReader  # type: ignore
            import io

            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages
            texts = []
            for page in pages:
                try:
                    texts.append(page.extract_text() or "")
                except Exception:
                    texts.append("")
            return "\n".join(texts), len(pages)
        except ImportError:
            return "", 0
