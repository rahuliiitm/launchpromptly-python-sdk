"""
ImagePrefilter — fast local checks before hitting the ML scanner.

Performs:
  1. MIME type validation against allowlist
  2. Magic byte verification
  3. File size limits
  4. JPEG EXIF stripping (removes APP0/APP1 segments)

All checks complete in < 1 ms with no network or ML calls.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Optional, Set

from .types import MediaPart

MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 MB

ALLOWED_IMAGE_MIMES: Set[str] = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/webp", "image/avif", "image/bmp", "image/tiff",
}

MAGIC_BYTES: list[tuple[str, bytes]] = [
    ("image/jpeg", bytes([0xFF, 0xD8, 0xFF])),
    ("image/png",  bytes([0x89, 0x50, 0x4E, 0x47])),
    ("image/gif",  bytes([0x47, 0x49, 0x46])),
    ("image/webp", bytes([0x52, 0x49, 0x46, 0x46])),
    ("image/bmp",  bytes([0x42, 0x4D])),
]


@dataclass
class PrefilterResult:
    allowed: bool
    reason: Optional[str] = None
    stripped_data: Optional[bytes] = None


class ImagePrefilter:
    def __init__(
        self,
        allowed_mimes: Optional[Set[str]] = None,
        max_bytes: int = MAX_IMAGE_BYTES,
    ) -> None:
        self.allowed_mimes = allowed_mimes or ALLOWED_IMAGE_MIMES
        self.max_bytes = max_bytes

    def check(self, part: MediaPart) -> PrefilterResult:
        if part.mime_type not in self.allowed_mimes:
            return PrefilterResult(allowed=False, reason=f"MIME type not allowed: {part.mime_type}")
        if part.size_bytes > self.max_bytes:
            return PrefilterResult(allowed=False, reason=f"Image too large: {part.size_bytes} bytes (max {self.max_bytes})")
        if not self._verify_magic_bytes(part.data, part.mime_type):
            return PrefilterResult(allowed=False, reason=f"Magic bytes do not match declared MIME type {part.mime_type}")

        stripped = self._strip_exif(part.data, part.mime_type)
        return PrefilterResult(allowed=True, stripped_data=stripped)

    def _verify_magic_bytes(self, data: bytes, declared_mime: str) -> bool:
        for mime, prefix in MAGIC_BYTES:
            if mime == declared_mime:
                return data[: len(prefix)] == prefix
        return True  # unknown mime — allow

    def _strip_exif(self, data: bytes, mime: str) -> bytes:
        if mime not in ("image/jpeg", "image/jpg"):
            return data
        return self._strip_jpeg_exif(data)

    def _strip_jpeg_exif(self, data: bytes) -> bytes:
        """Remove JFIF/EXIF APP0/APP1 segments from a JPEG buffer."""
        SOI = 0xFFD8
        APP0 = 0xFFE0
        APP1 = 0xFFE1

        if len(data) < 2 or struct.unpack(">H", data[:2])[0] != SOI:
            return data

        result = bytearray(data[:2])  # keep SOI
        offset = 2

        while offset < len(data) - 1:
            if data[offset] != 0xFF:
                break
            if offset + 2 > len(data):
                break
            marker = struct.unpack(">H", data[offset : offset + 2])[0]
            if marker in (APP0, APP1):
                if offset + 4 > len(data):
                    break
                seg_len = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
                offset += 2 + seg_len
                continue
            result.extend(data[offset:])
            break

        return bytes(result)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
