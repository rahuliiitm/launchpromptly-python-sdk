"""
FileExtractor — converts raw file inputs into typed MediaPart objects.

Handles:
  - bytes + explicit MIME
  - file path (infers MIME from extension)
  - base64 data URIs
  - URL fetching (with timeout + size limits)

Enforces a global file-type blocklist for executables, archives, etc.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
import os
import re
from typing import Optional

from .types import MediaPart, MediaPartSource

MAX_URL_BYTES = 50 * 1024 * 1024
FETCH_TIMEOUT_S = 10

EXTENSION_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif",
    ".bmp": "image/bmp", ".tiff": "image/tiff", ".tif": "image/tiff",
    ".pdf": "application/pdf",
}

BLOCKED_MIMES = {
    "application/x-msdownload", "application/x-executable",
    "application/x-dosexec", "application/x-sharedlib",
    "application/x-elf", "application/zip", "application/x-tar",
    "application/x-rar-compressed", "application/x-7z-compressed",
    "text/x-shellscript",
}


class FileExtractor:
    async def from_bytes(self, data: bytes, mime_type: str, label: Optional[str] = None) -> MediaPart:
        self._guard_mime(mime_type)
        return self._build_part(data, mime_type, MediaPartSource.INLINE_BASE64, label)

    async def from_path(self, file_path: str, mime_type: Optional[str] = None) -> MediaPart:
        with open(file_path, "rb") as f:
            data = f.read()
        inferred = mime_type or self._mime_from_path(file_path)
        self._guard_mime(inferred)
        return self._build_part(data, inferred, MediaPartSource.FILESYSTEM, os.path.basename(file_path))

    async def from_data_uri(self, data_uri: str) -> MediaPart:
        match = re.match(r"^data:([^;]+);base64,(.+)$", data_uri, re.DOTALL)
        if not match:
            raise ValueError("Invalid data URI format")
        mime, b64 = match.group(1), match.group(2)
        data = base64.b64decode(b64)
        self._guard_mime(mime)
        return self._build_part(data, mime, MediaPartSource.INLINE_BASE64)

    async def from_url(self, url: str, expected_mime: Optional[str] = None) -> MediaPart:
        try:
            import aiohttp  # type: ignore
        except ImportError:
            raise ImportError("aiohttp is required for URL fetching: pip install aiohttp")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_S)) as session:
            async with session.get(url) as resp:
                if resp.status >= 400:
                    raise ValueError(f"HTTP {resp.status} fetching {url}")
                content_type = expected_mime or resp.content_type or "application/octet-stream"
                mime_type = content_type.split(";")[0].strip()
                self._guard_mime(mime_type)
                data = await resp.read()
                if len(data) > MAX_URL_BYTES:
                    raise ValueError(f"URL content too large: {len(data)} bytes (max {MAX_URL_BYTES})")
                return self._build_part(data, mime_type, MediaPartSource.URL, url)

    def _guard_mime(self, mime: str) -> None:
        if mime in BLOCKED_MIMES:
            raise ValueError(f"MIME type blocked for security: {mime}")

    def _mime_from_path(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        return EXTENSION_MIME_MAP.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"

    def _build_part(
        self,
        data: bytes,
        mime_type: str,
        source: MediaPartSource,
        label: Optional[str] = None,
    ) -> MediaPart:
        return MediaPart(
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type=mime_type,
            size_bytes=len(data),
            source=source,
            data=data,
            label=label,
        )
