from __future__ import annotations
import uuid
from datetime import datetime, timezone

def _utcnow():
    return datetime.now(timezone.utc)
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Audience(str, PyEnum):
    children = "children"
    teen = "teen"
    adult = "adult"


class BookType(str, PyEnum):
    short_story = "short_story"
    novel = "novel"


class POV(str, PyEnum):
    first_person = "first_person"
    third_limited = "third_limited"
    third_omniscient = "third_omniscient"


class WritingStyle(str, PyEnum):
    clinical = "clinical"
    poetic = "poetic"
    cyberpunk = "cyberpunk"
    anthropological = "anthropological"
    new_wave = "new_wave"
    high_epic = "high_epic"
    satirical = "satirical"
    visceral = "visceral"
    suburban_suspense = "suburban_suspense"
    grindhouse_pulp = "grindhouse_pulp"


class BookStatus(str, PyEnum):
    draft = "draft"
    foundation = "foundation"
    drafting = "drafting"
    revising = "revising"
    complete = "complete"


class JobStatus(str, PyEnum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class ChapterStatus(str, PyEnum):
    pending = "pending"
    drafted = "drafted"
    accepted = "accepted"
    revising = "revising"


class Book(Base):
    __tablename__ = "books"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[BookStatus] = mapped_column(Enum(BookStatus), default=BookStatus.draft)
    audience: Mapped[Audience | None] = mapped_column(Enum(Audience), nullable=True)
    book_type: Mapped[BookType | None] = mapped_column(Enum(BookType), nullable=True)
    chapter_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pov: Mapped[POV | None] = mapped_column(Enum(POV), nullable=True)
    writing_style: Mapped[WritingStyle | None] = mapped_column(Enum(WritingStyle), nullable=True)
    idea: Mapped[str | None] = mapped_column(Text, nullable=True)
    dir_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="book", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ChapterStatus] = mapped_column(Enum(ChapterStatus), default=ChapterStatus.pending)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    current_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    book: Mapped[Book] = relationship(back_populates="chapters")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_id: Mapped[str | None] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    book: Mapped[Book | None] = relationship(back_populates="jobs")


class AppSettingsRow(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    ollama_url: Mapped[str] = mapped_column(String(512))
    model: Mapped[str] = mapped_column(String(255))
    default_chapter_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_target_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
