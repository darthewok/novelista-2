# Spec: Novelista v2 — no SQL, BYOK, bestseller-grade output

Status: draft v2 for approval. Companion to `tasks/todo.md` (the review). Paths relative to `novelista/`.

## 1. Goals

1. **Lean, local-first, stand-alone.** One person, one machine, no database. State is JSON and markdown on disk. One process serves both the API and the UI on `http://127.0.0.1:8000`, so there is no CORS, no second server, no Node at runtime, no external fonts, scripts or CDNs. Double-click a launcher on Windows or macOS and the browser opens on the app (section 4b).
2. **Bring your own key.** Providers: Anthropic (official SDK), any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Together, Mistral…), LM Studio, Ollama. Keys stay on the user's disk. The only network traffic the app makes is to the provider the user configured.
3. **Output quality at the level of a professionally edited commercial novel.** Every chapter can pass through mechanical and editorial guardrails against AI tells. The mechanical scan always runs; the editorial polish pass is opt-in (section 8). Quality is measured, not asserted.
4. Keep the pipeline, the job/SSE layer and the React components. Fix the Phase 1 review bugs as a by-product.

## 2. Non-goals

- No multi-user, no auth, no hosting.
- No numeric 1–10 "quality score" shown to the user. Scores from LLM judges collapse into a narrow band and mislead. We surface *findings* (quoted sentences, patterns, contradictions), not grades.
- No reader panel, no Elo tournament, no art, no audiobook.
- No single-Next.js rewrite. The Python pipeline stays. Next.js itself goes (section 4b): it needs a Node server at runtime, which contradicts stand-alone.
- No installer, code signing or auto-update in v2. A single-file executable per OS is v2.1 (section 4b).

## 3. Architecture after the change

```
backend/app/
  config.py        env defaults only (data_dir)
  settings.py      NEW: load/save data/settings.json; masks secrets for the UI
  store.py         NEW: Book dataclass <-> data/novels/<id>/book.json
  jobs.py          in-memory only; has_active(book_id, chapter)
  events.py        unchanged + terminal-job replay fix
  llm_client.py    provider switch; returns (text, stop_reason)
  pipeline/        + summary_gen, canon_gen, voice_gen, editor_pass, slop_score
  routers/         same URL surface, DB calls replaced by store.* calls
  main.py          mounts frontend/dist as static files with SPA fallback; no CORS middleware
frontend/          Vite + React single-page app; built output committed in frontend/dist
start.bat / stop.bat / start.command / stop.command   launchers (section 4b)
```

Deleted: `db.py`, `models.py`, `AppSettingsRow`, the `sqlalchemy` dependency, `data/novelista.db`, `recover_orphans`, `CORSMiddleware`, Next.js and its config, `app_start.bat` / `app_stop.bat` (replaced by the launchers).

## 4. Data layout

```
data/
  settings.json
  novels/<book_id>/
    book.json
    seed.txt  world.md  characters.md  voice.md  canon.md  outline.md  summary.md  mystery.md
    chapters/ch_01.md  ch_01.v0.md ...
    briefs/ch_01.md          editor findings + user notes, feeds revise
    reports/ch_01.json       mechanical scan results (slop_score output)
    uploads/<files>  uploads/_extracted.md
```

`book.json`:

```json
{
  "id": "uuid", "title": "…", "status": "draft|foundation|drafting|revising|complete",
  "audience": null, "book_type": null, "chapter_count": null, "target_words": null,
  "pov": null, "writing_style": null, "idea": null,
  "created_at": "2026-11-07T10:00:00Z", "updated_at": "…",
  "chapters": [
    {"number": 1, "title": "…", "status": "pending|drafted|polished|accepted|revising",
     "word_count": 0, "version": 0, "tells": 0}
  ]
}
```

`settings.json`:

```json
{
  "provider": "anthropic",
  "providers": {
    "anthropic":  {"api_key": "sk-ant-…"},
    "openai":     {"api_key": "sk-…", "base_url": "https://api.openai.com/v1"},
    "openrouter": {"api_key": "sk-or-…", "base_url": "https://openrouter.ai/api/v1"},
    "lmstudio":   {"api_key": "lm-studio", "base_url": "http://localhost:1234/v1"},
    "ollama":     {"base_url": "http://localhost:11434", "num_ctx": 32768}
  },
  "models": {
    "outline":    "claude-opus-5-5",
    "draft":      "claude-opus-5-5",
    "revise":     "claude-opus-5-5",
    "editor":     "claude-opus-5-5",
    "foundation": "claude-sonnet-5-5",
    "voice":      "claude-sonnet-5-5",
    "seed":       "claude-sonnet-5-5",
    "summary":    "claude-haiku-5-5",
    "canon":      "claude-haiku-5-5"
  },
  "quality": {"auto_polish": false, "max_polish_passes": 1, "tells_threshold": 3}
}
```

Rules:
- `store.save(book)` writes `book.json.tmp` then `os.replace`. Bump `updated_at`.
- `Book` is a plain dataclass with the attribute names the pipeline already reads, so `directives.py` and the generators need no edits for the storage swap.
- `dir_path` is derived, not stored. Enums move to `enums.py`.
- Outline sync becomes a pure function `sync_chapters(book, specs) -> book`.
- One-off `scripts/migrate_sqlite.py` reads the old DB and writes `book.json` per book.
- Secrets never leave the machine except to the provider they belong to. GET `/api/settings` returns keys masked (`sk-ant-…1234`); a masked or empty value on PUT means "unchanged".

## 4b. Stand-alone runtime and launchers

**One origin.** FastAPI serves the built frontend from `frontend/dist` at `/`, with every unknown non-`/api` path falling back to `index.html` (client-side routing). The API stays under `/api`. Same origin means no CORS middleware, no proxy rewrites, and the browser's `EventSource` for job streams works unchanged. The server binds `127.0.0.1` only.

**Frontend becomes a Vite + React SPA.** Next.js is replaced because its app router needs a Node server at runtime and its static export cannot do `/books/[id]` routes without pre-rendering every id. The move is mechanical: the 12 pages become routes in `react-router` (hash-free, history routing with the SPA fallback above), `next/link` → `Link`, `useParams`/`useRouter` → the router's equivalents, `next/navigation` gone. Components, hooks, `lib/api.ts`, `lib/sse.ts`, Tailwind config and all styling are unchanged. The build output (`frontend/dist`, a few hundred KB) is committed, so a user never needs Node; Node is only needed by whoever edits the UI.

**No external resources.** `globals.css` uses the system font stack only (drop the `Inter` name). No CDN scripts, no Google Fonts, no icon fonts; icons are inline SVG. A build-time check greps `frontend/dist` for `https?://` and fails the build if any URL other than the provider placeholders in the settings form appears.

**Runtime requirements.** Python 3.11+ on the machine. That is the only prerequisite. First launch creates `backend/.venv` and installs the pinned dependencies (fastapi, uvicorn, httpx, anthropic, pypdf, python-multipart, sse-starlette); later launches skip that. Everything else is the user's own provider: Anthropic or an OpenAI-compatible endpoint over the network, or LM Studio / Ollama on the same machine.

**Launchers** (double-clickable, at `novelista/`):

| File | Does |
|---|---|
| `start.bat` | Finds `py -3.11+` or `python`; creates `.venv` and installs on first run; starts uvicorn minimised, binding `127.0.0.1:8000`; writes the PID to `.run/pid`; waits for `/api/health`; opens the default browser. |
| `stop.bat` | Kills the PID from `.run/pid`, then anything listening on `:8000` as a fallback. `--full` also stops Ollama if it was started by us. |
| `start.command` | macOS equivalent: `python3` check with a plain-English message if missing, venv + install on first run, `nohup uvicorn … &`, PID file, health wait, `open http://127.0.0.1:8000`. Marked executable; Finder double-click opens Terminal and runs it. |
| `stop.command` | Kills the PID, then `lsof -ti :8000` as fallback. |

Both start scripts print one line per step and stay readable by someone who has never opened a terminal. If port 8000 is taken, they try 8001–8010 and open whichever worked. LM Studio and Ollama are not started by the launcher; the Settings page says "start LM Studio's server first" when the connection test fails.

**Single-file executable (v2.1).** PyInstaller one-file build per OS with `frontend/dist` bundled as data, producing `Novelista.exe` and `Novelista.app`. Removes the Python prerequisite. Deferred because it needs a build on each OS and testing on a clean machine; the launcher path above already gives a double-click start for anyone with Python.

## 5. Providers: `llm_client.complete`

```python
async def complete(*, system, user, task: str, max_tokens=16000,
                   stream_cb=None, creativity="medium") -> tuple[str, str]
```

- `task` picks `settings.models[task]`. `creativity` is `low | medium | high` and maps per provider: Anthropic → `output_config.effort` (`low` for extraction, `medium` for prose, `high` for outline and editor); OpenAI-compatible/LM Studio → `temperature` 0.3 / 0.8 / 1.0; Ollama → same temperatures plus `num_ctx`.
- Returns `(text, stop_reason)` normalised to `"end" | "length" | "refusal"`. `"length"` publishes `{"type":"warning"}` to the job (truncation detection). `"refusal"` raises with a readable message.
- Always streams.

**Anthropic** — official `anthropic` package, `AsyncAnthropic(api_key=…)`:

```python
async with client.messages.stream(
    model=model, max_tokens=max_tokens, system=system,
    messages=[{"role": "user", "content": user}],
    output_config={"effort": effort},
) as stream:
    async for delta in stream.text_stream:
        if stream_cb: await stream_cb(delta)
    final = await stream.get_final_message()
```

No `temperature` (current models reject it), no `thinking` param (adaptive by default). `AuthenticationError` → "Invalid API key, check Settings". Prompt caching: the stable prefix (craft rules, anti-slop, voice, world, characters) goes in `system` with `cache_control` so a 24-chapter draft pays for it once per 5 minutes, not 24 times.

**OpenAI-compatible** (`openai`, `openrouter`, `lmstudio`, or a custom entry with its own `base_url`) — one branch, raw `httpx` against `POST {base_url}/chat/completions` with `stream: true`, parsing `data:` SSE lines. ~40 lines, no new dependency. LM Studio is this branch with `base_url` defaulting to `http://localhost:1234/v1` and any non-empty key. `finish_reason: "length"` → `"length"`.

**Ollama** — current native client plus `options.num_ctx` and `done_reason`.

`POST /api/settings/test` per provider: Anthropic `client.models.list()`, OpenAI-compatible `GET /models`, Ollama `/api/tags`; reports which configured model ids are present.

Tests: existing `httpx.MockTransport` covers Ollama and the OpenAI-compatible SSE shape. Anthropic gets a fake injected through `set_client()` whose `messages.stream` yields canned deltas. One test per provider asserts the request body shape (effort vs temperature, num_ctx present for Ollama only).

## 6. Router changes (same URLs, same JSON shapes)

| Router | Change |
|---|---|
| `books.py` | `store.*`. `GET /manuscript?accepted_only` stops writing `manuscript.md`; only `/export` does. |
| `seed.py` | Pass `ref_text` to candidates. Candidate split accepts `### 1.` / `**1.**`. |
| `foundation.py` | Generate map gains `canon` and `voice`. Regenerate copies the old file to `<kind>.prev.md` first. |
| `outline.py` | Pure `sync_chapters`; set `chapter_count` when null; tolerant heading regex; `warning` event when zero chapters parse. |
| `chapters.py` | Draft: snapshot + version bump when a file exists; 409 if accepted or a job is active for this chapter. Revise: snapshot + bump inside `run`. After draft and revise: run the **polish pipeline** (section 8) then `summary` and `canon` appends. New `POST /{n}/editor` (editor pass on demand) and `POST /{n}/tighten` (adversarial cut). `GET /{n}/report` returns `reports/ch_NN.json`. |
| `uploads.py` | `Path(file.filename).name`; 400 if it differs or starts with `_`. Extraction wrapped; failed file unlinked. |
| `settings.py` | Provider block, per-task models, quality block. Masking as above. |
| `stream.py` | Terminal job on subscribe → one status event and return. |
| `jobs.py` | In-memory `Job` dataclass; `has_active`. New `POST /api/books/{id}/draft-all` enqueues pending chapters in order (serialised by the existing semaphore), with a `chapter` field on events so the UI can show "3 of 24". |

Schemas: copy `Field` constraints from `BookCreate` to `BookPatch`; validate `base_url` and `num_ctx >= 2048`.

## 7. Pipeline changes

All in v2 unless marked.

1. **Context for drafting** (`chapter_draft.py`): system = craft + anti-slop + structural rules + voice (cached); user = world, characters, canon, `summary.md`, this chapter's outline block, foreshadowing lines for this chapter, previous chapter tail (2500 chars), next chapter's first beats. `_extract_outline_block` stops at the ledger heading.
2. **Context for revising** (`chapter_revise.py`): same as draft plus the brief (`briefs/ch_NN.md`) and the current text. The brief is the mechanism; user notes are appended to it.
3. **`summary_gen.py`** (task `summary`, Haiku): "Ch N — what happened / what changed / open threads" ≤120 words, upserted into `summary.md`.
4. **`canon_gen.py`** (task `canon`, Haiku, creativity low): world + characters → hard facts; after each chapter, new facts appended under a `## Ch N` heading.
5. **`voice_gen.py`** (task `voice`, Sonnet): generates three trial openings in different registers from seed + world; the user picks one in the UI (or picks "let the model choose"); a second call writes voice.md Part 2: exemplar paragraphs, anti-exemplars, vocabulary wells, sentence-rhythm rules. Without this, every book sounds like the same default narrator, which is the most recognisable AI tell at book length.
6. **`editor_pass.py`** (task `editor`, Opus, creativity high): structured JSON, no score. Fields: `weakest_sentences[]` (quote + why), `ai_patterns[]` (quote + pattern name), `canon_violations[]`, `missed_beats[]`, `repetitions[]` (phrases/images reused from earlier chapters, given `summary.md` and canon), `over_explained[]` (places where the subtext is stated), `top_revisions[]` (≤5, concrete). Rendered into `briefs/ch_NN.md` as PROBLEM / KEEP / CHANGE / VOICE RULES / TARGET.
7. **`slop_score.py`**: port of the reference `evaluate.py` mechanical scanner, no LLM. Tier-1/2/3 word and phrase counts, "not just X but Y", em-dash density, sentence-length coefficient of variation, paragraph-length uniformity, transition-opener ratio, triadic lists, "He did not…" openers, "the way X did Y", section-break count, telling patterns ("felt a sense of", "couldn't help but"), fiction tells (breath they didn't know they were holding, etc.), repeated chapter-ending shapes across the book. Output: JSON with per-finding quote, line, rule, severity. Saved to `reports/ch_NN.json`; `tells` count stored on the chapter.
8. **`adversarial_cut.py`** (task `editor`, Opus) + `apply_cuts`: "cut 10% without losing anything" → list of quoted passages classified FAT / REDUNDANT / OVER-EXPLAIN / GENERIC / TELL. `apply_cuts` removes exact or whitespace-normalised matches, skips ambiguous ones, reports what it could not find. Exposed as the Tighten button. Over-writing is the second most recognisable AI tell after voice.
9. **Prompt assets**: `anti_slop.md` merged from the reference ANTI-SLOP.md (tier-1 words, tier-3 fillers, structural patterns) and CRAFT.md's fiction-tells list; `craft.md` regains the Stability Trap block ("let bad things stay bad; irreversible loss; withhold information"), the show-don't-tell operational list, and the dialogue rules (imperfect, interrupted, people don't answer the question asked). `mystery.md` (author-only secret) is passed to outline only. Budget: system prefix ≤ 6k tokens; it is cached.
10. **Manuscript editor letter** (task `editor`, Opus, 1M context): the whole manuscript plus canon and outline → a letter as a literary critic then as a professor of fiction, with specific actionable items tied to chapters. Exposed as `POST /api/books/{id}/review`, output to `reports/manuscript_review.md`. *v2.1.*
11. **`build_outline_from_chapters`**: regenerate `outline.md` from prose once chapters diverge. *v2.1.*

## 8. Quality bar and guardrails

The reference pipeline's lesson is that quality comes from three layers, and that each catches what the others miss. All three are in v2.

**Layer 1 — prompt-side prevention.** The merged anti-slop and structural rules, the Stability Trap, the voice document with exemplars, canon and running summary in every call. This is cheap and prevents most tier-1 tells and most continuity errors.

**Layer 2 — mechanical detection (`slop_score`, no LLM).** Runs automatically after every draft and revise, in milliseconds. It cannot be charmed by fluent prose. The chapter page shows a "Tells" panel: each finding with the quoted sentence highlighted in the editor and the rule that fired. The count sits on the chapter list.

**Layer 3 — editorial judgment (`editor_pass`, Opus).** Reads with the whole book in mind (summary + canon), catches repetition across chapters, over-explanation, flat scenes, missed beats. Its output is the revision brief.

**The polish pipeline**: draft → slop_score → editor_pass → one revise with the generated brief → slop_score again → status `polished`. It is **opt-in**. Three ways to run it:
- A **Polish** button on the chapter page, which runs it on the current text (the common case: read the draft, decide it is worth polishing).
- A **"polish each chapter" checkbox** on Draft all.
- `quality.auto_polish` in Settings, off by default. When on, every draft and revise is followed by one polish pass automatically.

One pass maximum per run (`max_polish_passes`); the user accepts or asks for more. Every pass is a version in the history, so nothing is hidden. The mechanical `slop_score` scan is not part of the opt-in: it always runs after every draft and revise because it is free and instant, and the Tells panel is always visible.

**Hard rules enforced by the pipeline, not by hoping:**
- Tier-1 words and phrases (delve, tapestry, testament, "a testament to", "sent shivers", "couldn't help but", the breath they didn't know they were holding, etc.) are flagged as errors; a chapter cannot be marked `polished` while any remain.
- "Not just X, but Y" more than once per chapter: error.
- Em-dashes above 1 per 150 words: warning. Triadic lists above 3 per chapter: warning.
- Sentence-length CV below 0.45 (metronomic rhythm) or paragraph lengths within a narrow band: warning.
- Chapter ending that repeats the shape of the previous two endings (one-line zinger, rhetorical question, "and then everything changed"): warning.
- Any canon contradiction reported by the editor pass: error, blocks `polished`.
- Dialogue beats: more than 40% of dialogue lines carrying an adverbial tag or an action-beat-then-emotion ("she said, feeling…"): warning.

**Drafting process rules in the system prompt** (from the reference, kept short): at least 70% of the chapter in-scene; at most two section breaks; end on an image or an action, never on a summary; the POV character does not name their own emotion more than twice per chapter; subtext over statement; every scene changes something irreversibly or it is cut.

**Measured, not asserted.** Section 9 has the acceptance tests. Beyond them, a one-page `QUALITY.md` records, per generated test book, the tells per 1000 words before and after polish, so a prompt change can be shown to help or hurt.

## 9. Acceptance criteria

- `grep -r sqlalchemy backend/app` is empty; backend tests green with a temp `data_dir` fixture only.
- On a clean Windows machine with only Python installed: double-click `start.bat`, the browser opens on the dashboard, every page loads, a job streams. Same on a clean Mac with `start.command`. `stop.*` leaves nothing listening on the port.
- `grep -rE "https?://" frontend/dist` matches only the provider placeholder URLs from the settings form. The app works with the network cable unplugged when the provider is LM Studio or Ollama.
- `main.py` contains no `CORSMiddleware`; `GET /books/<id>/chapters/3` on the backend port returns `index.html`.
- Each provider's request body is asserted by a test (effort vs temperature, `num_ctx` for Ollama only, `base_url` honoured for LM Studio).
- Full flow from the UI on Anthropic and on LM Studio: create → seed → voice (pick a register) → world → characters → canon → outline → draft ch 1 → polish → accept → export.
- Draft on a chapter with existing text produces `v0` and version 1; two Revise clicks produce `v0`, `v1`, version 2, second job sees the first's output.
- Upload named `../../x.md` returns 400 and writes nothing.
- Backend restart keeps the UI-chosen provider and models.
- A draft that hits the token cap shows the warning.
- `slop_score` unit tests: a planted paragraph of tier-1 tells returns every one with the correct line; a clean paragraph returns zero.
- A chapter with a planted tier-1 word cannot reach `polished`; after the auto-polish pass on a real draft, the tier-1 count is zero and total tells per 1000 words dropped.
- `editor_pass` on a chapter with a planted canon contradiction (eye colour changed) reports it in `canon_violations`.

## 10. Work breakdown and delegation

Fable 5.1 (this session) owns the spec, sequencing, review of every diff, the prompt wording for the editor pass, and the end-to-end quality check. Everything else goes to a cheaper subagent to save tokens. Effort is the Agent tool's effort setting.

| # | Task | Files | Size | Delegate to | Why |
|---|---|---|---|---|---|
| 1 | `store.py`, `enums.py`, `settings.py`, atomic save; delete DB modules | backend/app | M | **Opus**, high | Shapes every router |
| 2 | `llm_client.py` four providers, creativity mapping, stop_reason, test fakes | llm_client.py, tests/_llm_mock.py | M | **Opus**, high | SDK and SSE surfaces, error mapping, caching |
| 3 | `jobs.py` in-memory + `has_active` + draft-all; `events.py`; `stream.py` | backend/app | S | **Sonnet** | Routine |
| 4 | Routers books/seed/foundation/outline/settings on `store.*` | routers | M | **Sonnet** | Mechanical translation, URLs fixed |
| 5 | `chapters.py` snapshot/version/409 + polish pipeline wiring + editor/tighten/report routes | chapters.py | M | **Opus**, high | Concurrency and data-loss paths |
| 6 | `uploads.py` hardening | 1 file | S | **Haiku** | Two guards |
| 7 | `scripts/migrate_sqlite.py` | 1 file | S | **Haiku** | Rows to JSON |
| 8 | Rewrite test fixtures; add the acceptance tests in section 9 | tests | M | **Sonnet** | Pattern-following |
| 9 | Draft/revise context assembly (7.1, 7.2) | 2 files | S | **Sonnet** | Prompt assembly |
| 10 | `summary_gen`, `canon_gen`, `voice_gen` (7.3–7.5) | 3 new files + routers | M | **Sonnet** | Same shape as existing gens |
| 11 | `slop_score.py` port from reference `evaluate.py` + unit tests | 1 new file | M | **Sonnet** | Regex tables, exactness matters |
| 12 | `anti_slop.md`, `craft.md` merges from the reference repo | prompts/*.md | S | **Haiku** | Copying lists |
| 13 | `editor_pass.py`, `adversarial_cut.py` + `apply_cuts` | 2 new files | M | **Opus**, high | The judgment layer; prompt wording reviewed by Fable |
| 14 | **Next.js → Vite + React SPA**: router, 12 pages, remove Next deps, system font, build-time URL check, commit `dist` | frontend/* | M | **Sonnet** | Mechanical port of 23 imports; components untouched |
| 15 | `main.py` static mount + SPA fallback, remove CORS; port fallback 8000–8010 | main.py | S | **Haiku** | ~15 lines |
| 16 | Launchers `start.bat`, `stop.bat`, `start.command`, `stop.command` | novelista/ | S | **Sonnet** | Shell quoting on two OSes is where Haiku slips |
| 17 | Frontend settings page (provider, keys, models table, quality toggles incl. auto-polish) | settings page, api.ts | M | **Sonnet** | Form work |
| 18 | Frontend dirty flag, confirms, job awareness, error line, draft-all progress with polish checkbox | 5 files | M | **Sonnet** | UI plumbing |
| 19 | Frontend Tells panel + editor highlighting + brief editor + Polish and Tighten buttons | chapter page, new component | M | **Sonnet** | UI |
| 20 | Voice-picker UI (three openings, choose one) | new page | S | **Sonnet** | UI |
| 21 | Delete frontend test deps, a11y attributes | package.json, 6 tsx | S | **Haiku** | Mechanical |
| 22 | End-to-end run on Anthropic and LM Studio from the launchers on both OSes; generate one test book; fill `QUALITY.md`; review every diff | all | — | **Fable** | Verification is not delegated |

Sequencing: 1 → 2 → (3, 6, 7, 12 parallel) → 4 → 5 → 8 → (9, 10, 11 parallel) → 13 → 14 → (15, 16 parallel) → (17, 18, 19, 20, 21 parallel) → 22. Parallel groups share no files. Task 14 precedes the UI tasks so they are written once, against the router that ships.

Token note: Haiku and Sonnet tasks are roughly 70% of the diff by line count. The four Opus tasks are where a wrong abstraction or a weak prompt costs a second pass.

## 11. App-side model tiering and cost

Defaults favour quality where it shows. Rough cost for one 80k-word novel on Anthropic (24 chapters, ~15k cached input and ~5k output per call):

| Task | Default | Calls per book | Approx. cost |
|---|---|---|---|
| outline | Opus 5.5 | 1 | < $0.20 |
| draft + one polish revise | Opus 5.5 | 48 | ~$6 |
| editor pass | Opus 5.5 | 24 | ~$2 |
| foundation, voice, seed | Sonnet 5.5 | ~6 | < $0.30 |
| summary, canon | Haiku 5.5 | 48 | < $0.10 |

About $9 per full novel at Opus quality, roughly $4 with draft/revise on Sonnet. Prompt caching is what keeps the input side small; without it the draft line triples. All of this is a table in Settings; an "economy" button sets draft/revise/editor to Sonnet.

For LM Studio and Ollama the same table holds local model names. The guardrails in section 8 matter most there: a local 30B model produces more tier-1 tells per 1000 words, and the mechanical scanner plus one polish pass is what closes the gap.

## 12. Decisions taken (change if you disagree)

- Keys in plain text in the git-ignored `data/settings.json`. No keychain.
- Job history not persisted; version files and `summary.md` are the history.
- Editor pass and adversarial cut run on the `editor` model only; they are never run on Haiku, since weak judgment there produces confident wrong briefs.
- Auto-polish is off by default and one pass when on. The Polish button is the expected way to use it. More passes are the user's choice per chapter, because the second pass has diminishing returns and a real cost.
- Vite + React replaces Next.js. Alternatives considered: Next static export (cannot serve `/books/[id]` without pre-rendering ids), keeping the Next server (needs Node at runtime, a second process and CORS). The SPA is the only option that satisfies "one process, one origin, no Node".
- The built `frontend/dist` is committed to the repo so users never run a build. It is regenerated by whoever edits the UI.
- Python remains a prerequisite in v2. The PyInstaller single-file build that removes it is v2.1.
- Manuscript-level review (7.10) and outline-from-chapters (7.11) are v2.1, after a test book has been generated end to end.
