"""Bounds for still images passed from local tools to a vision model."""

from __future__ import annotations

import base64
import binascii
from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 8_000_000  # Match retained-asset admission before checkpoint offload.
MAX_IMAGE_PIXELS = 32_000_000
MAX_TOOL_IMAGE_BYTES_PER_REQUEST = 32 * 1024 * 1024
IMAGE_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


def validate_image_bytes(raw: bytes, mime_type: str) -> None:
    """Reject unsupported, oversized, malformed, or mislabeled image bytes."""

    expected_format = IMAGE_FORMATS.get(mime_type)
    if expected_format is None:
        raise ValueError("Only PNG, JPEG, and WebP images can be sent to the model.")
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image must be nonempty and at most {MAX_IMAGE_BYTES} bytes.")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != expected_format:
                raise ValueError("Image bytes do not match the stated file type.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError(f"Image exceeds the {MAX_IMAGE_PIXELS}-pixel limit.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Image could not be verified.") from exc


def validate_image_data_url(url: str) -> int:
    """Validate a tool-provided inline image before adding it to model input."""

    header, separator, encoded = url.partition(",")
    if not separator or not header.startswith("data:") or not header.endswith(";base64"):
        raise ValueError("Tool images must contain inline base64 image data.")
    mime_type = header[5:-7].lower()
    if mime_type not in IMAGE_FORMATS:
        raise ValueError("Only PNG, JPEG, and WebP tool images are supported.")
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError(f"Tool image exceeds the {MAX_IMAGE_BYTES}-byte limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError("Tool image contains invalid base64 data.") from exc
    validate_image_bytes(raw, mime_type)
    return len(raw)
