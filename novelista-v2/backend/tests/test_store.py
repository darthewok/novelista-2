from __future__ import annotations
import json
import time
from pathlib import Path


def test_create_get_roundtrip():
    from app import store
    from app.enums import Audience, POV, ChapterStatus
    b = store.create_book(title="T", idea="an idea", audience=Audience.adult, pov="first_person")
    d = Path(b.dir_path)
    for sub in ("chapters", "briefs", "uploads", "reports"):
        assert (d / sub).is_dir()
    assert (d / "seed.txt").read_text(encoding="utf-8") == "an idea"
    assert b.created_at.endswith("Z")

    b.chapters.append(store.ChapterRec(number=1, title="One"))
    b.chapters[0].status = ChapterStatus.polished
    store.save_book(b)
    raw = json.loads((d / "book.json").read_text(encoding="utf-8"))
    assert "dir_path" not in raw
    assert raw["audience"] == "adult" and raw["pov"] == "first_person" and raw["book_type"] is None
    assert raw["chapters"][0]["status"] == "polished"

    g = store.get_book(b.id)
    assert g == b
    assert g.audience is Audience.adult and g.pov is POV.first_person
    assert g.chapter(1).title == "One" and g.chapter(2) is None


def test_list_sorted_and_skips_dirs_without_json():
    from app import store
    from app.config import settings
    a = store.create_book(title="A")
    b = store.create_book(title="B")
    (settings.novels_dir / "not-a-book").mkdir()
    assert [x.title for x in store.list_books()] == ["B", "A"]
    time.sleep(0.001)
    store.save_book(a)
    assert [x.title for x in store.list_books()] == ["A", "B"]


def test_save_bumps_updated_at_and_leaves_no_tmp():
    from app import store
    b = store.create_book(title="T")
    before = b.updated_at
    time.sleep(0.001)
    store.save_book(b)
    assert b.updated_at > before
    assert store.get_book(b.id).updated_at == b.updated_at
    assert not list(Path(b.dir_path).glob("*.tmp"))


def test_delete():
    from app import store
    b = store.create_book(title="T")
    store.delete_book(b.id)
    assert not Path(b.dir_path).exists()
    assert store.get_book(b.id) is None


def test_bad_ids_rejected():
    import pytest
    from app import store
    for bad in ("..", "../x", "", "abc", "C:/x"):
        assert store.get_book(bad) is None
        with pytest.raises(ValueError):
            store.delete_book(bad)
