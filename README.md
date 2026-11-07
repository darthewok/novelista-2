# Autonovel / Novelista

An AI novel-writing assistant that runs on your own machine with your own model. You bring a key (Anthropic, OpenAI, OpenRouter) or a local server (LM Studio, Ollama); the app takes a story idea through seed, voice, world, characters, canon, outline and chapters, and puts every draft through guardrails built to catch the ways AI prose gives itself away.

The current app is **`novelista-v2/`**. `novelista/` is the earlier version kept for reference, and `autonovel-master/` is the command-line research pipeline the quality techniques were ported from.

```
novelista-v2/start.bat        Windows: double-click, browser opens on http://127.0.0.1:8000
novelista-v2/start.command    macOS: double-click (chmod +x once if Finder refuses)
```

Only prerequisite: Python 3.11+. No database, no Node at runtime, no CORS, no external fonts or scripts. One process serves the UI and the API; all state is JSON and Markdown under `novelista-v2/data/`.

---

## How it works

The book is built as layers, each one feeding the next, and each one a Markdown file you can edit by hand at any point.

| Step | Produces | Model task | What goes in |
|---|---|---|---|
| Seed | `seed.txt` | seed | your idea, or ten generated candidates |
| Voice | `voice.md` | voice | three trial openings in different registers; you pick one; the app turns it into exemplar passages, anti-exemplars, vocabulary wells and rhythm rules |
| World | `world.md` | foundation | seed + voice |
| Characters | `characters.md` | foundation | seed + world + voice |
| Canon | `canon.md` | canon | hard facts extracted from world + characters |
| Outline | `outline.md` | outline | everything above; `### Ch N: Title` headings become chapter rows |
| Chapters | `chapters/ch_NN.md` | draft / revise | see below |

**What a chapter draft actually sees.** The stable part of the prompt (craft rules, anti-slop lists, voice document, creative directives) is sent as a cached system prefix. The variable part carries the world, characters, canon, the running story summary with a structured *state* line (who is alive, where everyone is, what was agreed), this chapter's outline entry, the foreshadowing rows that plant or pay off here, the last 2,500 characters of the previous chapter marked *context only*, the first beats of the next chapter, a list of phrases already used in earlier chapters, and a *scope fence* listing every later chapter as off-limits. A POV lock is added when the outline names one.

**After every draft or revise**, three things happen automatically: a mechanical scan (no model call), a short summary call that updates `summary.md`, and a canon-extraction call that appends new facts. Every version of a chapter is kept; nothing is overwritten silently.

**Per-task models.** Settings holds one model per task. On Anthropic the defaults are Opus for outline, draft, revise and editor; Sonnet for foundation, voice and seed; Haiku for summary and canon (roughly $9 per 80k-word novel, $4 with the Economy preset). On a local server the detected models are offered in a dropdown and prefilled.

**Providers.** Anthropic through the official SDK; OpenAI, OpenRouter, LM Studio and any OpenAI-compatible endpoint through one shared branch; Ollama through its native API (so `num_ctx` and repetition penalties can be set). Keys stay in `data/settings.json` and never leave the machine except to the provider they belong to.

---

## Guardrails

Three layers, each catching what the others miss. Findings are quoted sentences with line numbers, never scores: a numeric "quality score" from a model judge collapses into a narrow band and tells you nothing.

### 1. Prevention in the prompt
- Merged anti-slop lists (54 Tier 1 banned words and phrases, 37 restricted, 25 fillers) plus structural rules: no "not just X but Y", triad cap, em-dash cap, no negation-contrast openers, no section-break crutch, 70% in-scene, varied chapter endings.
- Craft rules including the Stability Trap (let bad things stay bad, irreversible loss, withhold information), foreshadowing spacing, dialogue rules, and the ending rule (a new concrete action or image; not eyes closing, not walking through a door, not a repeated line).
- Context discipline: previous chapter marked context-only, voice marked style-reference-only, later chapters fenced off, used phrases listed as banned.

### 2. Mechanical detection (`backend/app/pipeline/slop_score.py`)
Runs in milliseconds after every draft and revise, reads its word lists from the same prompt file the model sees so the two can never drift, and cannot be charmed by fluent prose. 24 rules; errors block a chapter from being marked *polished*:

| Severity | Rules |
|---|---|
| error | Tier 1 words/phrases · copied text (10-word run repeated in-chapter or from an earlier chapter) · exemplar copy (8-word run from `voice.md`) · paragraph loop (unique-paragraph ratio below 0.9) · artefacts (non-Latin script, LaTeX, Markdown bold, outline meta-words like "camera pans" or "the metaphor") · chapter under 200 words · "not just X but Y" twice or more |
| warning | restricted-word repeats · filler phrases · em-dash density · triads · negation-contrast openers · "the way X did" · transition-opener ratio · metronomic sentence rhythm · uniform paragraph lengths · section breaks · telling patterns and stock body clichés · adverb dialogue tags · emotion self-naming · stated theme · "felt" density · POV break · repeated chapter-ending shape · cross-chapter phrase echoes (with an allow-list for the book's own refrains) |

The chapter page shows every finding; clicking one jumps the editor to the line.

### 3. Editorial judgment (`editor_pass.py`, editor model)
A structured read with the whole book in mind: weakest sentences, AI patterns, canon violations, missed beats, repetitions across chapters, over-explained subtext, flat scenes, what to keep, and up to five concrete revisions. Rendered as a five-section revision brief (PROBLEM / KEEP / CHANGE / VOICE RULES / TARGET) that opens with the scanner's banned-phrase hits, line-numbered, so even a small model gets exact targets.

### The polish loop (opt-in)
**Polish** = editor pass → brief → revise with the brief → rescan → mechanical line fix that rewrites only the flagged sentences and deletes verbatim duplicates → rescan. A chapter is marked *polished* only when zero errors remain. Available as a button per chapter, a checkbox on *Draft all*, or `auto_polish` in Settings (off by default). **Tighten** runs the adversarial cut: the model quotes about 10% of the words it would remove, classified FAT / REDUNDANT / OVER-EXPLAIN / GENERIC / TELL, and only exact matches are applied. **Fix tells** runs the line fix alone.

---

## Where smaller models hit the wall

Measured on a real run (two six-chapter cyberpunk novels generated entirely through the UI on Ollama with `qwen3.5:4b`, then a Sonnet-class model on a third). Full numbers in [`novelista-v2/QUALITY.md`](novelista-v2/QUALITY.md).

| | 4B local, before tuning | 4B local, after tuning | Sonnet-class |
|---|---|---|---|
| Tells per 1,000 words (scanner) | 8.3 | 6.2, and 0.8 on a redraft with the loop guard | chapter 1: in band, no errors |
| Voice trials | two of three identical, all three spoiled the ending | distinct, opening only | three genuinely different registers, nothing spoiled |
| Ending spoiled in chapter 1 | yes | no | no |

What the 4B model could not be prompted out of, and what the pipeline does about it:

- **Paragraph loops.** One seven-paragraph block repeated nine times in a chapter; a per-rule finding cap hid it. Fix: an uncappable unique-paragraph ratio, `repeat_penalty` / `repeat_last_n` set on the request, in-chapter de-duplication, and one automatic redraft. On the next run the looping chapter came back clean, at the cost of clipped prose (the penalty is a setting, ease it if the voice turns choppy).
- **Verbatim regurgitation.** The previous chapter's tail, the voice exemplar and whole paragraphs get re-pasted, especially late in the book when the model "runs out". Labels help a little; the copied-text and exemplar-copy rules catch what slips through, and the line fix deletes in-chapter duplicates without a model call.
- **Continuity.** A character died four times across six chapters; objects teleport; inside/outside logic drifts. The structured State line and canon de-duplication reduce it, but a 4B model does not track state across 2,000 words. This is the clearest "needs a stronger model" item.
- **Refrains and catchphrases.** The book's own motifs get overused (one simile eleven times). The used-phrase list in the prompt is ignored by small models; the scanner flags it and the brief lists it.
- **Voice.** First person survives; a specific register (dialect cadence, clipped beats) mostly does not past chapter 2.
- **Length.** Chapters land 25% under or 35% over target; the band wording helps, the loop guard's redraft fires on the short side.
- **Editor pass on a small model** still produces a usable brief (the JSON parsed, the notes were sensible), but the *revise* ignores it. That is why the mechanical line fix exists: it needs the model to rewrite one sentence at a time, which a 4B model can do.

Practical guidance: a 4B model is enough to exercise the app; a 30B-class local model or a cloud key is where the output becomes something you would hand to a reader. Keep summary and canon on a cheap model regardless, they are extraction tasks.

---

## Repository layout

```
novelista-v2/        the app (backend/, frontend/, start/stop launchers, QUALITY.md, README.md)
novelista/           v1, for reference (Next.js + SQLite)
autonovel-master/    the original CLI research pipeline and its craft documents
tasks/               the review that started this, the spec, the build log, lessons learned
```

Development: `cd novelista-v2/backend && .venv\Scripts\python -m pytest` (158 tests); `cd novelista-v2/frontend && npm run build` (fails if any external URL enters the bundle; the built `dist/` is committed so users never need Node).
