"""Request bodies (responses are plain JSON rows from the repository)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    user_id: str
    password: str = Field(default="demo", description="Mock login: any non-empty password")


class TransitionIn(BaseModel):
    action: str
    reason_code: str | None = None
    comment: str | None = None


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class AssignIn(BaseModel):
    user_id: str


class BomLineEditIn(BaseModel):
    design_qty: float | None = Field(default=None, ge=0)
    spare_qty: float | None = Field(default=None, ge=0)
    reason_code: str
    comment: str | None = None


class BomLineAddIn(BaseModel):
    sector: str
    catalog_key: str
    design_qty: float = Field(ge=0)
    spare_qty: float = Field(default=0, ge=0)
    action: str = "Install"
    reason_code: str
    comment: str | None = None


class RfiAnswerIn(BaseModel):
    answer: str = Field(min_length=1)


class RunIn(BaseModel):
    site_ids: list[str] | None = None
