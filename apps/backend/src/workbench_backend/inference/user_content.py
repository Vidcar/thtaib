"""Validated current-user input; never an alternate system/history channel."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TextContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=1_000_000)


class ImageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=12_000_000)
    detail: Literal["auto", "low", "high"] = "auto"

    @field_validator("url")
    @classmethod
    def actual_image_bytes(cls, value: str) -> str:
        header, separator, encoded = value.partition(",")
        allowed = {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}
        if not separator or header not in allowed:
            raise ValueError("Images must contain PNG, JPEG or WebP data, not a URL, attachment ID or host path.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid image base64 data.") from exc
        valid = (
            header == "data:image/png;base64" and data.startswith(b"\x89PNG\r\n\x1a\n")
            or header == "data:image/jpeg;base64" and data.startswith(b"\xff\xd8\xff")
            or header == "data:image/webp;base64" and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        )
        if not valid:
            raise ValueError("Image content does not match its declared media type.")
        return value


class ImageContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["image_url"] = "image_url"
    image_url: ImageContent


UserContentBlock = Annotated[TextContentBlock | ImageContentBlock, Field(discriminator="type")]


def user_message_content(task: str, blocks: list[UserContentBlock] | None) -> str | list[dict]:
    if not blocks:
        return task
    content = [{"type": "text", "text": task}] if task.strip() else []
    return content + [block.model_dump(mode="json") for block in blocks]
