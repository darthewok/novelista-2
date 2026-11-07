from __future__ import annotations


def _book(**kw):
    from app.models import Book
    b = Book(
        id="t", title="T", dir_path="/tmp",
        audience=kw.get("audience"),
        book_type=kw.get("book_type"),
        pov=kw.get("pov"),
        writing_style=kw.get("writing_style"),
        chapter_count=kw.get("chapter_count"),
        target_words=kw.get("target_words"),
        idea=None,
    )
    return b


def test_empty_book_produces_empty_directives():
    from app.pipeline.directives import build_directives
    assert build_directives(_book()) == ""


def test_every_pov_renders():
    from app.pipeline.directives import build_directives
    from app.models import POV
    for pov in POV:
        out = build_directives(_book(pov=pov))
        assert "CREATIVE DIRECTIVES" in out
        assert len(out) > 50


def test_every_writing_style_renders():
    from app.pipeline.directives import build_directives
    from app.models import WritingStyle
    for s in WritingStyle:
        out = build_directives(_book(writing_style=s))
        assert "CREATIVE DIRECTIVES" in out
        assert len(out) > 50


def test_targets_line_uses_per_chapter_math():
    from app.pipeline.directives import build_directives
    out = build_directives(_book(chapter_count=10, target_words=20000))
    assert "target chapters: 10" in out
    assert "target total words: 20,000" in out
    assert "2,000 words per chapter" in out


def test_grindhouse_and_coben_are_present():
    from app.pipeline.directives import build_directives
    from app.models import WritingStyle
    assert "Grindhouse" in build_directives(_book(writing_style=WritingStyle.grindhouse_pulp))
    assert "Coben" in build_directives(_book(writing_style=WritingStyle.suburban_suspense))


def test_combined_block_contains_all_set_fields():
    from app.pipeline.directives import build_directives
    from app.models import Audience, BookType, POV, WritingStyle
    out = build_directives(_book(
        audience=Audience.teen,
        book_type=BookType.novel,
        pov=POV.first_person,
        writing_style=WritingStyle.cyberpunk,
        chapter_count=12,
        target_words=60000,
    ))
    assert "teen" in out
    assert "first-person" in out
    assert "Cyberpunk" in out
    assert "novel" in out
    assert "12" in out
