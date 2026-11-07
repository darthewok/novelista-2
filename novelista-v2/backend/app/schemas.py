from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from .enums import Audience, BookType, POV, WritingStyle, BookStatus, ChapterStatus, JobStatus


class BookCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=255)
    idea: Optional[str] = None
    audience: Optional[Audience] = None
    book_type: Optional[BookType] = None
    chapter_count: Optional[int] = Field(default=None, ge=1, le=200)
    target_words: Optional[int] = Field(default=None, ge=500, le=2_000_000)
    pov: Optional[POV] = None
    writing_style: Optional[WritingStyle] = None


class BookPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    idea: Optional[str] = None
    audience: Optional[Audience] = None
    book_type: Optional[BookType] = None
    chapter_count: Optional[int] = Field(default=None, ge=1, le=200)
    target_words: Optional[int] = Field(default=None, ge=500, le=2_000_000)
    pov: Optional[POV] = None
    writing_style: Optional[WritingStyle] = None
    status: Optional[BookStatus] = None


class ChapterOut(BaseModel):
    model_config = {"from_attributes": True}
    number: int
    title: Optional[str]
    status: ChapterStatus
    word_count: int
    version: int
    tells: int = 0


class BookOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    title: str
    status: BookStatus
    audience: Optional[Audience]
    book_type: Optional[BookType]
    chapter_count: Optional[int]
    target_words: Optional[int]
    pov: Optional[POV]
    writing_style: Optional[WritingStyle]
    idea: Optional[str]
    dir_path: str
    created_at: str
    updated_at: str
    chapters: list[ChapterOut] = []


class JobOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    book_id: Optional[str]
    kind: str
    status: JobStatus
    created_at: datetime
    finished_at: Optional[datetime]
    error: Optional[str]


class SeedChoose(BaseModel):
    text: Optional[str] = None
    index: Optional[int] = None


class SeedText(BaseModel):
    text: str
