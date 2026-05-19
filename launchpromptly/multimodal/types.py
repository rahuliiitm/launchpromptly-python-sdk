"""
Shared types for the multimodal module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MediaPartSource(str, Enum):
    USER_UPLOAD = "user-upload"
    URL = "url"
    INLINE_BASE64 = "inline-base64"
    FILESYSTEM = "filesystem"


@dataclass
class MediaPart:
    """A single media item ready for scanning."""

    sha256: str
    mime_type: str
    size_bytes: int
    source: MediaPartSource
    data: bytes
    label: Optional[str] = None


@dataclass
class ImageScanResult:
    sha256: str
    mime_type: str
    nsfw_score: float
    nsfw_blocked: bool
    face_detected: bool
    extracted_text: Optional[str] = None
    cache_hit: bool = False
    scanner_mode: str = "prefilter_only"
    latency_ms: int = 0


@dataclass
class PdfScanResult:
    sha256: str
    extracted_text: str
    page_count: int
    pii_entities: list[dict] = field(default_factory=list)
    injection_score: float = 0.0
    injection_blocked: bool = False
    cache_hit: bool = False
    latency_ms: int = 0


@dataclass
class FileScanResult:
    sha256: str
    mime_type: str
    size_bytes: int
    allowed: bool
    reason: Optional[str] = None
