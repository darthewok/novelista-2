"""Composes the CREATIVE DIRECTIVES block injected at the top of every system prompt.

Single source of truth for audience / POV / writing_style / book_type / word-target / chapter-count
steering. Imported by every pipeline/*_gen.py module.
"""
from __future__ import annotations
from typing import Optional

from ..store import Book
from ..enums import Audience, POV, WritingStyle, BookType


POV_DIRECTIVES: dict[POV, str] = {
    POV.first_person: (
        "Narrate in first-person (I/we), past tense unless the scene demands otherwise. "
        "Voice must be intimate, biased, immediate — the reader sees only what the narrator "
        "notices and believes. Lean into the narrator's blind spots."
    ),
    POV.third_limited: (
        "Narrate in third-person limited past tense, locked to a single POV character per scene. "
        "The reader knows only what that POV knows. No head-hopping within a scene."
    ),
    POV.third_omniscient: (
        "Narrate in third-person omniscient. The narrator may move between minds and know things "
        "no single character knows, but with restraint — pick each vantage deliberately and "
        "hold a consistent narrative voice."
    ),
}


STYLE_DIRECTIVES: dict[WritingStyle, str] = {
    WritingStyle.clinical: (
        "Clinical / 'Hard' style (Asimov, Clarke, Weir). Prioritize logic, technical accuracy, "
        "and clarity. Prose is precise and objective; voice is that of a scientist or observer "
        "reporting facts. Dry, intellectual, grounded, efficient. Avoid ornate metaphor."
    ),
    WritingStyle.poetic: (
        "Poetic / Raygun Gothic style (Bradbury, Delany). Sensory, nostalgic, metaphor-dense. "
        "Prose aspires to high-art; mood over mechanism. Evocative rather than mechanistic."
    ),
    WritingStyle.cyberpunk: (
        "Cyberpunk / Neon-Noir style (Gibson, Sterling, Morgan). Fast-paced, cynical, 'crunchy'. "
        "Technical jargon as slang. Low-life-meets-high-tech. Fragmented sentences. Sensory "
        "overload: ozone, wet pavement, burnt plastic."
    ),
    WritingStyle.anthropological: (
        "Anthropological / Social style (Le Guin, Butler). Clean, calm, deeply observant of "
        "culture, language, and ritual. Treat the alien or the other as a society to understand, "
        "not a monster to fight. Thoughtful, quiet, profound."
    ),
    WritingStyle.new_wave: (
        "New Wave / Experimental style (Ellison, Ballard). Break the rules — stream-of-consciousness, "
        "strange formatting, surreal imagery. Dark, psychological, focused on internal breakdown. "
        "Jarring."
    ),
    WritingStyle.high_epic: (
        "High-Epic / Mythopoeic style (Tolkien). Elevated, formal, reverent. Deep time. "
        "Setting-as-character. Archaic sentence rhythm; weight of history; a clear moral North Star. "
        "Use archaic structures sparingly but deliberately."
    ),
    WritingStyle.satirical: (
        "Satirical / Humanist style (Pratchett). Conversational, witty, profoundly observant of "
        "human (and alien) stupidity. Sharp metaphors explaining complex ideas. Find the mundane "
        "inside the magical. Occasional knowing wink to the reader. Humorous, wise, subversive."
    ),
    WritingStyle.visceral: (
        "Visceral / Naturalistic style (Martin). Grounded in the dirt. Heavy sensory detail: food, "
        "heraldry, cold, hunger, blood. Un-heroic, political, brutal. Power has cost."
    ),
    WritingStyle.suburban_suspense: (
        "Suburban Suspense / Twist-Master style (Harlan Coben). Everyman protagonist whose life is "
        "upended by a secret from the past. Clean, functional, invisible prose that serves plot "
        "over voice. Rapid-fire dialogue, short chapters, ticking-clock pacing. Relatable and "
        "addictive."
    ),
    WritingStyle.grindhouse_pulp: (
        "Grindhouse Pulp / Hyper-Violent style (Anonymous — 'The Book With No Name' / Bourbon Kid). "
        "Tarantino-in-space: cinematic, dark, pitch-black humor. Sprawling cast of quirky, often "
        "disposable characters and a legendary unstoppable anti-hero. Short, sharp, punchy "
        "sentences. Cool factor and visceral action over introspection."
    ),
}


AUDIENCE_DIRECTIVES: dict[Audience, str] = {
    Audience.children: (
        "Audience: children (approx 8–12). Simple vocabulary. No graphic violence, no sex, no drug "
        "use. Clear moral stakes. Protagonists the reader can root for."
    ),
    Audience.teen: (
        "Audience: teen / YA (approx 13–17). Coming-of-age themes welcome. Restrained violence. "
        "No explicit sex. Voice can be sardonic, vulnerable, or both."
    ),
    Audience.adult: (
        "Audience: adult. Full range of content permitted when it serves the story — "
        "violence, sex, drug use, and difficult themes are on the table."
    ),
}


BOOK_TYPE_SUMMARY: dict[BookType, str] = {
    BookType.short_story: "Book type: short story (single-scene or single-arc; tight focus).",
    BookType.novel: "Book type: novel (multi-chapter, multi-arc structure).",
}


def build_directives(book: Book) -> str:
    """Return the CREATIVE DIRECTIVES block (empty string if nothing set)."""
    lines: list[str] = []
    if book.audience is not None:
        lines.append(f"- {AUDIENCE_DIRECTIVES[book.audience]}")
    if book.pov is not None:
        lines.append(f"- {POV_DIRECTIVES[book.pov]}")
    if book.writing_style is not None:
        lines.append(f"- {STYLE_DIRECTIVES[book.writing_style]}")
    if book.book_type is not None:
        lines.append(f"- {BOOK_TYPE_SUMMARY[book.book_type]}")

    target_fragments: list[str] = []
    if book.chapter_count is not None:
        target_fragments.append(f"target chapters: {book.chapter_count}")
    if book.target_words is not None:
        target_fragments.append(f"target total words: {book.target_words:,}")
        if book.chapter_count:
            per_ch = book.target_words // max(1, book.chapter_count)
            target_fragments.append(f"~{per_ch:,} words per chapter")
    if target_fragments:
        lines.append("- Targets: " + "; ".join(target_fragments) + ".")

    if not lines:
        return ""
    return "CREATIVE DIRECTIVES:\n" + "\n".join(lines) + "\n"


def per_chapter_word_target(book: Book) -> Optional[int]:
    if book.target_words and book.chapter_count:
        return book.target_words // max(1, book.chapter_count)
    if book.target_words and not book.chapter_count:
        return None
    return None
