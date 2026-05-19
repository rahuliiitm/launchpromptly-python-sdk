"""
LaunchPromptly SDK — Multimodal module (Python)

Provides MediaPart extraction and scanning for:
  - Images (MIME type, magic byte check, EXIF strip, NSFW + face via scanner)
  - PDFs  (text extraction via pypdf, deep scan via scanner)
  - Files (extension + MIME validation, hash dedup)

Architecture:
  - SDK handles: MIME validation, magic byte check, size limits, EXIF strip, SHA-256 deduplicate
  - Scanner handles: OCR, NSFW, face detection, PDF deep-text, PII on extracted text
"""

from .file_extractor import FileExtractor
from .image_prefilter import ImagePrefilter
from .pdf_extractor import PdfExtractor
from .scanner import MultimodalScanner
from .types import (
    FileScanResult,
    ImageScanResult,
    MediaPart,
    MediaPartSource,
    PdfScanResult,
)

__all__ = [
    "MediaPart",
    "MediaPartSource",
    "ImageScanResult",
    "PdfScanResult",
    "FileScanResult",
    "ImagePrefilter",
    "PdfExtractor",
    "FileExtractor",
    "MultimodalScanner",
]
