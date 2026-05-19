"""
MultimodalScanner — orchestrates SDK-side pre-processing + scanner service calls.

For images: prefilter → scanner /scan/image (NSFW, face, OCR)
For PDFs:   local text extract → scanner /scan/pdf (PII, injection on text)
For files:  type validation only

Deduplication: session-level dict of sha256 → verdict.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .image_prefilter import ImagePrefilter, compute_sha256
from .pdf_extractor import PdfExtractor
from .types import FileScanResult, ImageScanResult, MediaPart, PdfScanResult


class MultimodalScanner:
    def __init__(
        self,
        scanner_client: Optional[Any] = None,
        nsfw_threshold: float = 0.85,
        block_faces: bool = False,
        max_image_bytes_for_scanner: int = 20 * 1024 * 1024,
    ) -> None:
        self._scanner_client = scanner_client
        self._nsfw_threshold = nsfw_threshold
        self._block_faces = block_faces
        self._max_image_bytes = max_image_bytes_for_scanner
        self._prefilter = ImagePrefilter()
        self._pdf_extractor = PdfExtractor()
        self._session_cache: dict[str, Any] = {}

    async def scan_image(self, part: MediaPart) -> ImageScanResult:
        t0 = time.monotonic()

        if part.sha256 in self._session_cache:
            return self._session_cache[part.sha256]  # type: ignore[return-value]

        precheck = self._prefilter.check(part)
        if not precheck.allowed:
            return ImageScanResult(
                sha256=part.sha256, mime_type=part.mime_type,
                nsfw_score=0.0, nsfw_blocked=False, face_detected=False,
                cache_hit=False, scanner_mode="prefilter_only",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        effective_data = precheck.stripped_data or part.data
        effective_sha = compute_sha256(effective_data) if precheck.stripped_data else part.sha256

        if self._scanner_client is None or len(effective_data) > self._max_image_bytes:
            result = ImageScanResult(
                sha256=effective_sha, mime_type=part.mime_type,
                nsfw_score=0.0, nsfw_blocked=False, face_detected=False,
                cache_hit=False, scanner_mode="prefilter_only",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            self._session_cache[part.sha256] = result
            return result

        try:
            raw = await self._scanner_client.scan_file(effective_data, part.mime_type)
            nsfw_score = float(raw.get("nsfwScore", 0.0))
            face_detected = bool(raw.get("faceDetected", False))
            result = ImageScanResult(
                sha256=effective_sha, mime_type=part.mime_type,
                nsfw_score=nsfw_score,
                nsfw_blocked=nsfw_score >= self._nsfw_threshold or (self._block_faces and face_detected),
                face_detected=face_detected,
                extracted_text=raw.get("extractedText"),
                cache_hit=bool(raw.get("cacheHit", False)),
                scanner_mode="scanner",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            self._session_cache[part.sha256] = result
            return result
        except Exception:
            result = ImageScanResult(
                sha256=effective_sha, mime_type=part.mime_type,
                nsfw_score=0.0, nsfw_blocked=False, face_detected=False,
                cache_hit=False, scanner_mode="prefilter_only",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return result

    async def scan_pdf(self, part: MediaPart) -> PdfScanResult:
        t0 = time.monotonic()

        if part.sha256 in self._session_cache:
            return self._session_cache[part.sha256]  # type: ignore[return-value]

        extracted = await self._pdf_extractor.extract(part)

        if not extracted.allowed:
            return PdfScanResult(
                sha256=part.sha256, extracted_text="", page_count=0,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        if self._scanner_client is None or not extracted.text:
            result = PdfScanResult(
                sha256=part.sha256,
                extracted_text=extracted.spotlighted_text,
                page_count=extracted.page_count,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            self._session_cache[part.sha256] = result
            return result

        try:
            raw = await self._scanner_client.scan_text(extracted.spotlighted_text)
            result = PdfScanResult(
                sha256=part.sha256,
                extracted_text=extracted.spotlighted_text,
                page_count=extracted.page_count,
                pii_entities=raw.get("piiEntities", []),
                injection_score=float(raw.get("injectionScore", 0.0)),
                injection_blocked=bool(raw.get("blocked", False)),
                cache_hit=bool(raw.get("cacheHit", False)),
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            self._session_cache[part.sha256] = result
            return result
        except Exception:
            result = PdfScanResult(
                sha256=part.sha256,
                extracted_text=extracted.spotlighted_text,
                page_count=extracted.page_count,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return result

    async def scan_file(self, part: MediaPart) -> FileScanResult:
        return FileScanResult(
            sha256=part.sha256,
            mime_type=part.mime_type,
            size_bytes=part.size_bytes,
            allowed=True,
        )

    def clear_session_cache(self) -> None:
        self._session_cache.clear()
