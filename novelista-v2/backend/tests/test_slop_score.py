from __future__ import annotations
import random
import re
import time
from pathlib import Path

_BR = re.compile(r"\[[^\]]*\]")

CLEAN = """The kettle had gone cold by the time Marta came back from the yard. She poured it anyway and drank standing at the window, watching the neighbour's boy chase a hen across the frost.

"You're late," said her brother from the doorway. He had slept in his boots again.

"The well rope snapped." She set the cup down. "I spliced it, but it won't last the week."

He grunted and went to look at the stove. The door hung crooked on one hinge, and a thin line of smoke leaked from the seam. Nobody had fixed it since their father died. Nobody had said they would.

Outside, the hen escaped under the fence and the boy sat down hard in the mud and laughed. Marta watched him until her own mouth twitched. It surprised her. She turned away before her brother could notice.

At noon the carter came with flour and a letter. The letter was from the bank, and she put it in her apron pocket without opening it. Her brother asked what it said. She told him it was about the roof. He did not ask again, which meant he knew.

They ate bread and cold mutton at the table, with the shutters half closed against the glare off the snow. A clock ticked somewhere in the wall, though the clock itself had been sold years ago. Marta could never find the sound.

When the plates were clean she went out to the shed and took down the saw. The blade was rusted at one end. She worked the file along it for an hour, and her fingers lost their feeling, and the afternoon went grey and quiet around her. By dusk the teeth were bright. She hung the saw back on its nail and stood a while in the dark, listening to the hens settle."""


def _scan(text, **kw):
    from app.pipeline import slop_score
    return slop_score.scan(text, **kw)


def _rules(r, name):
    return [f for f in r["findings"] if f["rule"] == name]


def _book(chapters=None, **kw):
    from app import store
    b = store.create_book(title="T", **kw)
    for n, t in (chapters or {}).items():
        (Path(b.dir_path) / "chapters" / f"ch_{n:02d}.md").write_text(t, encoding="utf-8")
    return b


def test_tier_lists_parsed_from_markdown():
    from app.pipeline import slop_score as s
    assert len(s.TIER1_ENTRIES) >= 15
    assert len(s.TIER2_ENTRIES) >= 15 and len(s.TIER3_ENTRIES) >= 10
    assert "delve" in s.TIER1_ENTRIES and "synergize" in s.TIER1_ENTRIES
    assert not any("(" in e for e in s.TIER1_ENTRIES)


def test_planted_tier1_each_found_on_correct_line():
    from app.pipeline import slop_score as s
    lines = [f"Marta paused. {_BR.sub('fear', e)} and the stove ticked." for e in s.TIER1_ENTRIES]
    r = _scan("\n".join(lines))
    got = {f["line"] for f in _rules(r, "tier1")}
    assert not [e for i, e in enumerate(s.TIER1_ENTRIES, 1) if i not in got]
    assert all(f["severity"] == "error" for f in _rules(r, "tier1"))
    assert r["metrics"]["tier1_count"] >= len(s.TIER1_ENTRIES)


def test_clean_paragraph_is_clean():
    r = _scan(CLEAN)
    assert r["error_count"] == 0 and r["warning_count"] <= 1, r["findings"]


def test_tier2_repeat_only():
    one = _scan("The palpable silence held. " + CLEAN)
    two = _scan("The palpable silence held. A palpable chill followed. " + CLEAN)
    assert not _rules(one, "tier2")
    assert len(_rules(two, "tier2")) == 1 and two["metrics"]["tier2_repeats"] == 1


def test_not_just_but_counts():
    a = "It was not just a door, but a warning."
    assert [f["severity"] for f in _rules(_scan(a), "not_just_but")] == ["warning"]
    r2 = _scan(a + " She was not only tired, but done.")
    assert [f["severity"] for f in _rules(r2, "not_just_but")] == ["error", "error"]


def test_em_dash_density():
    base = "word " * 148
    assert not _rules(_scan(base + "a — b."), "em_dash_density")
    r = _scan(base + "a — b -- c.")
    assert _rules(r, "em_dash_density") and r["metrics"]["em_dash_per_150"] > 1


def test_triads():
    r = _scan("She bought apples, pears, and plums. " * 4)
    assert _rules(r, "triads") and r["metrics"]["triad_count"] == 4
    assert not _rules(_scan("She bought apples, pears, and plums. " * 3), "triads")


def test_sentence_rhythm():
    flat = " ".join(["The old dog ran to the red barn." for _ in range(40)])
    assert _rules(_scan(flat), "sentence_rhythm")
    lens = [3, 18, 7, 25, 5, 12, 2, 20, 9, 4]
    varied = " ".join(" ".join(f"w{i}x{j}" for j in range(lens[i % 10])) + "." for i in range(40))
    r = _scan(varied)
    assert not _rules(r, "sentence_rhythm") and r["metrics"]["sentence_len_cv"] > 0.45


def test_dialogue_tags():
    bad = "\n".join('"Go away," she said angrily.' for _ in range(4))
    good = "\n".join('"Go away," she said.' for _ in range(4))
    assert _rules(_scan(bad), "dialogue_tags")
    assert not _rules(_scan(good), "dialogue_tags")
    feel = "\n".join('"Go," she said, feeling sick.' for _ in range(3))
    assert _rules(_scan(feel), "dialogue_tags")


def test_telling():
    r = _scan("She felt a sense of dread. He couldn't help but stare. In that moment she was feeling sad.")
    assert len(_rules(r, "telling")) >= 4


def test_negation_the_way_sections_emotion():
    assert _rules(_scan("He did not move at all. He waited.\nShe wasn't ready yet. She stood."), "negation_contrast")
    assert _rules(_scan("The way he rushed ended. the way she waited ended. The way it fell ended and the way it burned ended."), "the_way")
    assert _rules(_scan("a\n\n***\n\nb\n\n---\n\nc\n\n* * *\n\nd"), "section_breaks")
    assert _rules(_scan("I was afraid. He felt angry. She was sad. I felt relieved."), "emotion_naming")


def test_repeated_phrase_across_chapters():
    b = _book({1: "Dawn came slowly. The rusted iron gate groaned open."})
    r = _scan(CLEAN.replace("Outside,", "Outside, the rusted iron gate groaned shut."), book=b, chapter=2)
    msgs = [f["message"] for f in _rules(r, "repeated_phrase")]
    assert any("rusted iron gate groaned" in m for m in msgs) and len(msgs) <= 5
    assert not _rules(_scan(CLEAN, book=b, chapter=1), "repeated_phrase")


def test_chapter_ending_three_one_liners():
    body = CLEAN.rsplit("\n\n", 1)[0]
    b = _book({1: body + "\n\nIt was over.", 2: body + "\n\nWho would know?"})
    r = _scan(body + "\n\nNothing would ever be the same.", book=b, chapter=3)
    assert _rules(r, "chapter_ending")
    b2 = _book({1: body + "\n\nIt was over.", 2: CLEAN})
    assert not _rules(_scan(body + "\n\nNothing.", book=b2, chapter=3), "chapter_ending")


def test_word_count_rules():
    assert [f["severity"] for f in _rules(_scan("Too short."), "word_count")] == ["error"]
    b = _book(target_words=24000, chapter_count=8)  # 3000 per chapter
    big = _scan(" ".join(["word"] * 5000) + ".", book=b, chapter=1)
    assert [f["severity"] for f in _rules(big, "word_count")] == ["warning"]
    assert not _rules(_scan(CLEAN, book=_book(), chapter=1), "word_count")


def test_6000_words_under_200ms():
    from app.pipeline import slop_score as s
    rnd = random.Random(1)
    vocab = [f"w{i}" for i in range(400)] + ["delve", "palpable", "said", "she", "the", "way", "not"]
    sents = [" ".join(rnd.choice(vocab) for _ in range(rnd.randint(4, 24))) + "." for _ in range(450)]
    text = "\n\n".join(" ".join(sents[i:i + 5]) for i in range(0, 450, 5))
    assert len(text.split()) > 5500
    s.scan(text)
    t = time.perf_counter()
    r = s.scan(text)
    assert time.perf_counter() - t < 0.2
    assert r["metrics"]["tells_per_1000"] > 0
