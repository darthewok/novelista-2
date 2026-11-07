// Human-readable labels + "vibe" previews for the seed form dropdowns.

export const POV_OPTIONS = [
  { value: "first_person", label: "First person (I / we)", vibe: "Intimate, biased, immediate. Great for unreliable narrators and deep emotional journeys." },
  { value: "third_limited", label: "Third-person limited", vibe: "Close to one character's thoughts. Builds tension while keeping secrets hidden." },
  { value: "third_omniscient", label: "Third-person omniscient", vibe: "God-like perspective. Setting-first stories where the world matters more than one mind." },
] as const;

export const STYLE_OPTIONS = [
  { value: "clinical",           label: "Clinical / Hard SF",        authors: "Asimov, Clarke, Weir",                     vibe: "Dry, intellectual, grounded, efficient. Prose as precise observation." },
  { value: "poetic",             label: "Poetic / Raygun Gothic",    authors: "Bradbury, Delany",                         vibe: "Dreamy, nostalgic, vivid. Prose as high art." },
  { value: "cyberpunk",          label: "Cyberpunk / Neon-Noir",     authors: "Gibson, Sterling, Morgan",                 vibe: "Gritty, cynical, urban, high-velocity. Low-life meets high-tech." },
  { value: "anthropological",    label: "Anthropological / Social",  authors: "Le Guin, Butler",                          vibe: "Thoughtful, observant, quiet, profound. Cultures, not monsters." },
  { value: "new_wave",           label: "New Wave / Experimental",   authors: "Ellison, Ballard",                         vibe: "Aggressive, surreal, jarring, psychological. Rules are suggestions." },
  { value: "high_epic",          label: "High-Epic / Mythopoeic",    authors: "Tolkien",                                  vibe: "Legendary, sweeping, ancient, rhythmic. Setting as character." },
  { value: "satirical",          label: "Satirical / Humanist",      authors: "Pratchett",                                vibe: "Humorous, wise, cynical-yet-hopeful, subversive." },
  { value: "visceral",           label: "Visceral / Naturalistic",   authors: "Martin",                                   vibe: "Gritty, political, sensual, brutal. Power has cost." },
  { value: "suburban_suspense",  label: "Suburban Suspense",         authors: "Harlan Coben",                             vibe: "Relatable, addictive, suspenseful, domestic. Secrets from the past upend ordinary lives." },
  { value: "grindhouse_pulp",    label: "Grindhouse Pulp",           authors: "Anonymous — 'Book With No Name' / Bourbon Kid", vibe: "Raw, fast, irreverent, bloody. Tarantino-in-space." },
] as const;

export const AUDIENCE_OPTIONS = [
  { value: "children", label: "Children (8–12)" },
  { value: "teen",     label: "Teen / YA (13–17)" },
  { value: "adult",    label: "Adult" },
] as const;

export const BOOK_TYPE_OPTIONS = [
  { value: "short_story", label: "Short story" },
  { value: "novel",       label: "Novel" },
] as const;
