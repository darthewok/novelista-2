"""One-off: migrate book metadata from the old Novelista SQLite DB into per-book book.json files.

Usage:
  python scripts/migrate_sqlite.py --db <novelista.db> --src <old data/novels> --dest <new data/novels> [--dry-run]
"""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

SUBDIRS = ("chapters", "briefs", "uploads", "reports")
BOOK_STATUS = {"draft", "foundation", "drafting", "revising", "complete"}
AUDIENCE = {"children", "teen", "adult"}
BOOK_TYPE = {"short_story", "novel"}
POV = {"first_person", "third_limited", "third_omniscient"}
CHAPTER_STATUS = {"pending", "drafted", "accepted", "revising"}


def iso_z(value):
    """'2026-04-17 10:00:00.123456' (naive UTC) -> '2026-04-17T10:00:00Z'."""
    if value is None:
        return None
    return datetime.fromisoformat(value).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(value, allowed, label, warnings):
    if value is None:
        return None
    v = str(value).lower()
    if v not in allowed:
        warnings.append(f"{label}: unexpected value {value!r}")
    return v


def read_db(db_path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        books = []
        for b in conn.execute("SELECT * FROM books ORDER BY created_at"):
            chapters = conn.execute(
                "SELECT * FROM chapters WHERE book_id = ? ORDER BY number", (b["id"],)
            ).fetchall()
            books.append((dict(b), [dict(c) for c in chapters]))
        settings = [dict(s) for s in conn.execute("SELECT ollama_url, model FROM app_settings")]
    finally:
        conn.close()
    return books, settings


def build_book(b, chapters, warnings):
    if b["chapter_count"] is not None and b["chapter_count"] != len(chapters):
        warnings.append(f"chapter_count={b['chapter_count']} but {len(chapters)} chapter rows")
    return {
        "id": b["id"],
        "title": b["title"],
        "status": norm(b["status"], BOOK_STATUS, "status", warnings),
        "audience": norm(b["audience"], AUDIENCE, "audience", warnings),
        "book_type": norm(b["book_type"], BOOK_TYPE, "book_type", warnings),
        "chapter_count": b["chapter_count"],
        "target_words": b["target_words"],
        "pov": norm(b["pov"], POV, "pov", warnings),
        "writing_style": b["writing_style"],
        "idea": b["idea"],
        "created_at": iso_z(b["created_at"]),
        "updated_at": iso_z(b["updated_at"]),
        "chapters": [
            {
                "number": c["number"],
                "title": c["title"],
                "status": norm(c["status"], CHAPTER_STATUS, "chapter status", warnings),
                "word_count": c["word_count"],
                "version": c["version"],
                "tells": 0,
            }
            for c in chapters
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="Migrate old Novelista SQLite books to book.json folders.")
    ap.add_argument("--db", required=True, help="path to old novelista.db")
    ap.add_argument("--src", required=True, help="old data/novels directory")
    ap.add_argument("--dest", required=True, help="new data/novels directory")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written, touch nothing")
    args = ap.parse_args()

    src, dest = Path(args.src), Path(args.dest)
    books, settings = read_db(args.db)
    migrated = skipped = 0

    for b, chapters in books:
        bid = b["id"]
        warnings = []
        data = build_book(b, chapters, warnings)
        s_dir, d_dir = src / bid, dest / bid

        if d_dir.exists():
            print(f"SKIP {bid} ({b['title']}): destination already exists: {d_dir}")
            skipped += 1
            continue

        has_src = s_dir.is_dir()
        if not has_src:
            warnings.append(f"source folder missing: {s_dir}; creating an empty book folder")

        print(f"{'[dry-run] ' if args.dry_run else ''}MIGRATE {bid} ({b['title']}) -> {d_dir}")
        if args.dry_run:
            print(f"  would copy {s_dir} -> {d_dir}" if has_src else "  (no source folder to copy)")
            print(f"  would create subdirs: {', '.join(SUBDIRS)}")
            print("  would write book.json:")
            print("  " + json.dumps(data, indent=2, ensure_ascii=False).replace("\n", "\n  "))
        else:
            if has_src:
                shutil.copytree(s_dir, d_dir)
            else:
                d_dir.mkdir(parents=True)
            for sub in SUBDIRS:
                (d_dir / sub).mkdir(exist_ok=True)
            (d_dir / "book.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"  wrote {d_dir / 'book.json'}")
        for w in warnings:
            print(f"  WARNING: {w}")
        migrated += 1

    verb = "would be migrated (dry run, nothing written)" if args.dry_run else "migrated"
    print(f"\nSummary: {migrated} books {verb}, {skipped} skipped.")

    if settings:
        s = settings[0]
        print(f"\nEnter these in the new Settings page: Ollama URL = {s['ollama_url']}, model = {s['model']}")


if __name__ == "__main__":
    main()
