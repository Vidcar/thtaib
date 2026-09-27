"""Authenticated Chat browser contracts. Worker addresses never cross this boundary."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class BrowserRuntimeStatus(BaseModel):
    supported: bool
    installed: bool
    node_version: str | None = None
    playwright_mcp_version: str | None = None
    chrome_available: bool = False
    chrome_version: str | None = None
    reason: str | None = None

class BrowserViewport(StrictModel):
    width: int = Field(default=1440, ge=240, le=3840)
    height: int = Field(default=900, ge=240, le=2160)

class BrowserTab(BaseModel):
    page_id: str
    title: str = ""
    url: str = "about:blank"

class BrowserDialog(BaseModel):
    type: str
    message: str
    default_value: str = ""

class BrowserFileChooser(BaseModel):
    multiple: bool = False

class BrowserDownload(BaseModel):
    asset_id: str
    name: str
    url: str

class BrowserSessionStatus(BaseModel):
    thread_id: str
    state: Literal["active", "lost", "closed"]
    worker: BrowserRuntimeStatus
    session_id: str | None = None
    tabs: list[BrowserTab] = Field(default_factory=list)
    active_page_id: str | None = None
    revision: int = 0
    viewport: BrowserViewport = Field(default_factory=BrowserViewport)
    control: Literal["agent", "taking_control", "user"] = "agent"
    dialog: BrowserDialog | None = None
    file_chooser: BrowserFileChooser | None = None
    downloads: list[BrowserDownload] = Field(default_factory=list)
    error: str | None = None

class BrowserControlRequest(StrictModel):
    action: Literal["take", "return"]

class BrowserResetRequest(StrictModel):
    confirmed: Literal[True]

class NavigateAction(StrictModel):
    type: Literal["navigate"]
    url: str = Field(min_length=1, max_length=8192)

class SimpleAction(StrictModel):
    type: Literal["back", "forward", "reload"]

class SelectTabAction(StrictModel):
    type: Literal["select_tab", "close_tab"]
    page_id: str = Field(min_length=1, max_length=100)

class NewTabAction(StrictModel):
    type: Literal["new_tab"]
    url: str | None = Field(default=None, max_length=8192)

class ResizeAction(BrowserViewport):
    type: Literal["resize"]

class PointerAction(StrictModel):
    type: Literal["pointer"]
    event: Literal["move", "down", "up", "click", "wheel"]
    x: float = Field(ge=0, le=3840)
    y: float = Field(ge=0, le=2160)
    button: Literal["left", "middle", "right"] = "left"
    delta_x: float = Field(default=0, ge=-10000, le=10000)
    delta_y: float = Field(default=0, ge=-10000, le=10000)

class KeyAction(StrictModel):
    type: Literal["key"]
    key: str = Field(min_length=1, max_length=100)

class TextAction(StrictModel):
    type: Literal["text"]
    text: str = Field(max_length=20000)

class DialogAction(StrictModel):
    type: Literal["dialog"]
    accept: bool
    prompt_text: str | None = Field(default=None, max_length=20000)

class UploadAction(StrictModel):
    type: Literal["upload"]
    asset_ids: list[str] = Field(default_factory=list, max_length=32)
    project_paths: list[str] = Field(default_factory=list, max_length=32)

BrowserAction = Annotated[NavigateAction | SimpleAction | SelectTabAction | NewTabAction | ResizeAction | PointerAction | KeyAction | TextAction | DialogAction | UploadAction, Field(discriminator="type")]

class BrowserActionRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=100)
    page_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)
    action: BrowserAction
