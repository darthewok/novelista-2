from enum import Enum


class Audience(str, Enum):
    children = "children"
    teen = "teen"
    adult = "adult"


class BookType(str, Enum):
    short_story = "short_story"
    novel = "novel"


class POV(str, Enum):
    first_person = "first_person"
    third_limited = "third_limited"
    third_omniscient = "third_omniscient"


class WritingStyle(str, Enum):
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


class BookStatus(str, Enum):
    draft = "draft"
    foundation = "foundation"
    drafting = "drafting"
    revising = "revising"
    complete = "complete"


class ChapterStatus(str, Enum):
    pending = "pending"
    drafted = "drafted"
    polished = "polished"
    accepted = "accepted"
    revising = "revising"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"
