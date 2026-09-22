"""Local, bounded inspection of retained originals; no network or executable content."""

from __future__ import annotations

import base64
import csv
import io
import json
import warnings
import zipfile

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from workbench_backend.assets.schemas import AssetExtraction, ExtractedSection

IMAGE_TYPES = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
DOCUMENT_TYPES = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_IMAGE_BYTES = 8_000_000
MAX_DOCUMENT_BYTES = 16_000_000
MAX_IMAGE_PIXELS = 32_000_000
MAX_EXTRACTED_CHARS = 2_000_000
MAX_EXTRACTED_SECTIONS = 10_000


def inspect_image(content: bytes, content_type: str) -> tuple[int, int]:
    if content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Choose a PNG, JPEG or WebP image.")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Images can be up to 8 MB each.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format != IMAGE_TYPES[content_type]:
                    raise ValueError("Image bytes do not match the file type.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds 32 megapixels.")
                dimensions = image.size
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                if getattr(image, "n_frames", 1) > 1:
                    raise ValueError("Choose a still image; animated images are not supported.")
                return dimensions
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, f"Cannot read this image: {exc}") from exc


def image_thumbnail(content: bytes) -> str:
    with Image.open(io.BytesIO(content)) as image:
        thumbnail = ImageOps.exif_transpose(image).convert("RGB")
        thumbnail.thumbnail((480, 320), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        thumbnail.save(buffer, format="WEBP", quality=82)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def extract_document(content: bytes, content_type: str) -> AssetExtraction:
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, "Documents can be up to 16 MB each.")
    sections: list[ExtractedSection] = []
    total = 0

    def append(source: str, text: str) -> None:
        nonlocal total
        # Labels and per-section records also occupy retained state. A JSON
        # array of tiny values must not become millions of database objects.
        total += len(text) + len(source) + 32
        if total > MAX_EXTRACTED_CHARS:
            raise HTTPException(413, "This document contains too much text. Split it into smaller files.")
        if text.strip():
            if len(sections) >= MAX_EXTRACTED_SECTIONS:
                raise HTTPException(413, "This document contains too many sections or rows. Split it into smaller files.")
            sections.append(ExtractedSection(source=source, text=text))

    try:
        if content_type == "application/pdf":
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ValueError("Unlock this PDF before attaching it.")
            if len(reader.pages) > 500:
                raise ValueError("PDFs can contain up to 500 pages.")
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > 16_000_000:
                    raise ValueError(f"Page {number} is too complex to extract locally.")
                append(f"Page {number}", page.extract_text() or "")
            parser = f"pypdf {pypdf.__version__}"
        elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            import docx
            from docx.table import Table
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 64_000_000:
                    raise ValueError("The expanded document exceeds 64 MB.")
            document = docx.Document(io.BytesIO(content))
            for number, block in enumerate(document.iter_inner_content(), 1):
                if isinstance(block, Table):
                    for row, cells in enumerate(block.rows, 1):
                        append(f"Table {number}, row {row}", " | ".join(cell.text for cell in cells.cells))
                else:
                    append(f"Paragraph {number}", block.text)
            parser = f"python-docx {docx.__version__}"
        elif content_type == "text/csv":
            for number, row in enumerate(csv.reader(io.StringIO(content.decode("utf-8-sig"))), 1):
                append(f"Row {number}", " | ".join(row))
            parser = "Python csv"
        elif content_type == "application/json":
            value = json.loads(content.decode("utf-8-sig"))
            if isinstance(value, dict):
                for key, item in value.items():
                    append("/" + str(key).replace("~", "~0").replace("/", "~1"), json.dumps(item, ensure_ascii=False, indent=2))
            elif isinstance(value, list):
                for number, item in enumerate(value):
                    append(f"/{number}", json.dumps(item, ensure_ascii=False, indent=2))
            else:
                append("/", json.dumps(value, ensure_ascii=False))
            parser = "Python json"
        else:
            raise HTTPException(415, "Unsupported document type.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Cannot extract this document: {str(exc)[:300]}") from exc
    return AssetExtraction(parser=parser, sections=sections, status="complete" if sections else "no_text",
        note=None if sections else "No selectable text found. Scanned pages need OCR, which is not available here.")


def extraction_text(extraction: AssetExtraction) -> str:
    return "\n\n".join(f"[{section.source}]\n{section.text}" for section in extraction.sections)
