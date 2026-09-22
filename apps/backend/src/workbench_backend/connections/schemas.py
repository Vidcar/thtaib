"""Public connection configuration never includes credential values."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ConnectionTool(BaseModel):
    id: str
    name: str
    remote_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


class ConnectionSnapshot(BaseModel):
    id: str
    name: str
    version: int
    kind: Literal["mcp", "public_web"]
    transport: Literal["http", "stdio", "builtin"]
    credential_ref: str | None = None
    tools: list[ConnectionTool] = Field(default_factory=list)


class ConnectionRecord(ConnectionSnapshot):
    enabled: bool = True
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    credential_present: bool = False
    last_tested_at: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class ConnectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["mcp", "public_web"]
    transport: Literal["http", "stdio", "builtin"]
    enabled: bool = True
    url: str | None = Field(default=None, max_length=2048)
    command: str | None = Field(default=None, max_length=2048)
    args: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def separate_transports(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Give this connection a name.")
        if self.kind == "public_web":
            if self.transport != "builtin" or self.url or self.command or self.args:
                raise ValueError("Public web uses the built-in search and page reader.")
        elif self.transport == "http":
            from urllib.parse import urlsplit
            parsed = urlsplit(self.url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
                raise ValueError("Use an HTTP(S) MCP address without credentials, query or fragment.")
            if self.command or self.args:
                raise ValueError("An HTTP address cannot launch a local process.")
        elif self.transport == "stdio":
            from pathlib import Path
            if not self.command or not Path(self.command).is_absolute() or self.url:
                raise ValueError("Choose an absolute executable path for a local MCP process.")
            if any(len(arg) > 4096 or "\x00" in arg for arg in self.args):
                raise ValueError("An MCP process argument is invalid.")
        else:
            raise ValueError("Choose an HTTP address or a local executable for MCP.")
        return self


class ConnectionUpdate(ConnectionWrite):
    expected_version: int = Field(ge=1)


class CredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: SecretStr = Field(min_length=1, max_length=16384)
