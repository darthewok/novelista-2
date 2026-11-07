# Novelista review — 2026-11-07

Deep-dive of `novelista/` (FastAPI + Next.js, Ollama). Baseline: 58 backend tests green, `tsc --noEmit` clean, no frontend tests exist.
Every item below was verified against the code. Paths are relative to `novelista/`.

## Phase 1 — Fix (bugs, data loss, security)

### Must fix
- [ ] **Ollama `num_ctx` never set** — `backend/app/llm_client.py:66` sends only temperature/num_predict. Ollama defaults to 4096 and drops the *oldest* tokens, i.e. the system prompt, directives and voice. Draft prompts are 8–12k tokens. Fix: `options.num_ctx` from a setting (default 32768).
- [ ] **Upload path traversal** — `backend/app/routers/uploads.py:40` does `d / file.filename`; `C:/evil.md` or `../../x.md` escapes the uploads dir (verified). Fix: `name = Path(file.filename).name`, 400 if it differs or starts with `_`.
- [ ] **Redraft destroys current chapter with no snapshot** — `routers/chapters.py:90` has no status guard, `pipeline/chapter_draft.py:124` overwrites `ch_NN.md`; versions list still claims "current vN". Fix: snapshot to `v{version}` + bump before drafting; 409 if `accepted`; frontend confirm when text exists.
- [ ] **SQLite write lock held across the whole LLM call** — `routers/chapters.py:170` flushes `status=revising` inside a `session_scope` that stays open for minutes. Any other write (accept, outline save, settings, next enqueue) hits "database is locked" and 500s. Fix: short session to set status, run LLM with no session, new session to write results. Same open-session-across-await pattern in draft and `foundation.py:66`.
- [ ] **Double-revise corrupts versions** — `chapters.py:154` snapshots at request time but reads `current_text` at run time. Two queued revises: rev-1 is lost, version stuck. Fix: snapshot + bump inside `run`; reject revise/draft if a job for that chapter is already queued/running.
- [ ] **UI settings ignored after backend restart** — `routers/settings.py:52` mirrors PUT into `env_settings` only; `main.py` lifespan never loads the DB row. "Test connection" uses the row, generation uses env default. Fix: load row 1 into `env_settings` in lifespan.
- [ ] **Unsaved editor edits silently lost** — `components/ArtifactEditor.tsx:28`, `outline/page.tsx:16`, `chapters/[n]/page.tsx:38` reset local text on every server refetch; no dirty flag, no `beforeunload`. Revise runs on the *server* copy, so edit then Revise without Save ignores the edits and then overwrites them. Fix: dirty flag + badge, `beforeunload` guard, auto-save before draft/revise.
- [ ] **Outline heading regex too strict** — `pipeline/outline_gen.py:94` only matches `Ch N:`. `### Chapter 1: X`, `**Ch 1: X**`, `Ch 1 — X` yield zero chapters and the job still reports done. Same regex in `chapter_draft._extract_outline_block`. Fix: `Ch(?:apter)?\.?\s*(\d+)\s*[:\-—–.]`, and publish a warning when specs is empty.

### Should fix
- [ ] Regenerate world/characters/outline overwrites saved artifact with no confirm and no history (`ArtifactEditor.tsx:33`, `outline/page.tsx:24`). Confirm when non-empty; keep `*.prev.md`.
- [ ] No error handling on any frontend mutation; failed POSTs are silent (`chapters/[n]/page.tsx:50-70`, `ArtifactEditor.tsx:33`, `settings/page.tsx:26`, `app/page.tsx:11`). Accept is enabled for `pending` chapters and silently 400s. Shared `useMutation` + one inline error line.
- [ ] Output truncation never detected — `llm_client.py` ignores `done_reason == "length"`; `chapter_draft.py:114` caps at 10k tokens regardless of target; short-story world/characters get 2500 tokens while the prompt asks for 1500–2500 words. Return `done_reason`, publish a warning event.
- [ ] Per-chapter word target is None when `chapter_count` blank, even after outline sets the count (`directives.py:134`, `outline.py:66` never writes `book.chapter_count`). Frontend then uses whole-book target as per-chapter target (`chapters/[n]/page.tsx:46`).
- [ ] Corrupt/encrypted PDF upload gives 500, file stays, every later upload 500s (`uploads.py:47,66`). Wrap extract in try/except, unlink on failure.
- [ ] Navigating away from a running job loses it; coming back lets you enqueue a duplicate (`useJobStream.ts:56`, `chapters/[n]/page.tsx:97`). Persist jobId, poll `api.getJob` (exists, unused) on mount, disable buttons while queued/running, show "waiting for another job".
- [ ] Timestamps serialize as naive UTC; browser reads as local (`models.py:5`, `schemas.py`). `field_serializer` attaching `+00:00`.
- [ ] Book status never advances; dashboard chip always "draft" (`BookCard.tsx:5`, `books.py:34`). Set it in pipeline or derive on client.
- [ ] Seed candidates never receive uploaded reference material (`routers/seed.py:56` omits `ref_text`).
- [ ] `_extract_candidate` splits only on `N. ` at line start (`seed.py:94`); `### 1.` / `**1.**` break "choose".
- [ ] Subscribing to a finished/unknown job hangs forever and leaks a queue (`events.py:25`). If job row is terminal, yield its status and return.
- [ ] No loading/error/404 states on book pages; `/chapters/abc` renders "Ch NaN" (`layout.tsx:19`, `chapters/[n]/page.tsx:12`).
- [ ] `BookPatch`/`SettingsPatch` unvalidated (`schemas.py:20`, `settings.py:21`): `target_words=-5` accepted and "~-5 words per chapter" lands in the prompt.
- [ ] No unique constraint on `(book_id, number)` (`models.py:91`), `MultipleResultsFound` 500 on concurrent outline saves.
- [ ] `GET /manuscript?accepted_only=true` overwrites `manuscript.md` with the filtered text (`books.py:88`).

### Dead code
- [ ] `vitest`, `@testing-library/*`, `jsdom` in `package.json` with zero test files; `npm test` fails. Delete or add one smoke test.
- [ ] Unused API fns: `patchBook`, `chooseSeed`, `getJob`, `listUploads`, `deleteUpload` (`lib/api.ts`). Most become used by Phase 3 items.
- [ ] `default_chapter_count` / `default_target_words` settings stored and read nowhere.
- [ ] `canon.md` and `briefs/` are plumbed (editable, exported, `brief=` param) but nothing generates or reads them.
- [ ] `darkMode: "class"` plumbing with no light theme.

## Phase 2 — Add (pipeline quality, ranked by value/effort)

The reference `autonovel-master` pipeline gets its quality from continuity + anti-slop + evaluation. Novelista ported foundation + draft but dropped most of the continuity layer. For a local 35B model these are the ones worth porting:

1. [ ] **Running `summary.md`** (S, high) — after each draft/revise, one ~200-token call appends "Ch N: happened / changed / open threads". Inject into draft + revise prompts. Right now ch 12 knows nothing of ch 3–10 except the outline and the last 1500 chars of ch 11.
2. [ ] **Revise prompt context** (S, high) — `chapter_revise.py` sends voice + anti-slop + characters + current text only. Add prev tail, next head, this chapter's outline block, world, summary. Reference passes all of these.
3. [ ] **Canon** (M, high) — `canon_gen.py` (world + characters to hard facts, temp 0.2) via the existing `/{kind}/generate` map; post-chapter "new facts" append; inject into draft/revise.
4. [ ] **Merge the reference anti-slop lists** (S, high) — `prompts/anti_slop.md` has 13 phrases + 16 words. Missing: tier-1 bare words (delve/testament/tapestry…), the whole tier-3 filler list, "not just X but Y", em-dash cap, triadic lists, "He did not…", "the way X did Y", section-break crutch, 70% in-scene, varied chapter endings. Text only, keep under ~1.5k tokens.
5. [ ] **Port `slop_score` regexes into `evaluate_light.py`** (S, med-high) — sentence-length CV, em-dash density, telling patterns, fiction tells, structural tics. No LLM, no deps; the one judge a 35B model cannot fool.
6. [ ] **Revision brief** (S-M, med-high) — `brief_gen.py` producing PROBLEM / KEEP / CHANGE / VOICE RULES / TARGET from evaluate output + user notes, saved to `briefs/chNN.md`, editable, consumed by the existing `brief=` param.
7. [ ] **Voice Part 2 generator** (M, med-high) — `voice_default.md` Part 2 is four "(pending)" headers injected verbatim into every draft. Generate 3 trial openings in different registers, user picks, second call writes exemplars/anti-exemplars/vocabulary wells.
8. [ ] **Stability Trap block + foreshadowing ledger injection** (S, med) — add the reference's "let bad things stay bad" block to outline + draft prompts; extract the ledger the outline already emits and pass "plant / pay off in this chapter" lines to the draft prompt. Also `_extract_outline_block` for the last chapter currently includes the ledger table.
9. [ ] ePub export via pandoc or `ebooklib` (S, med). Skip PDF/LaTeX, art, audiobook (paid APIs / Opus-class judgment).
10. [ ] Optional `mystery.md` passed only to outline_gen (S, med). Optional separate `judge_model` setting (S, low).

Do NOT port: numeric 1–10 LLM scoring, keep/discard thresholds, reader panel, Elo tournament, Opus dual-persona review. A 35B self-judge collapses to a 2-point band; the human-in-the-loop accept is the right replacement.

## Phase 3 — QoL (frontend)

1. [ ] Ctrl/Cmd+S saves on every editor; Escape closes the diff overlay.
2. [ ] Voice and Canon pages (`<ArtifactEditor kind="voice">` already works) + uploads card on the seed page (backend exists, no UI; `req()` forces JSON so uploads need raw `fetch(FormData)`).
3. [ ] "Draft next pending" / "Draft all" on the chapters index with a running-job banner (backend already serializes).
4. [ ] Prev/next chapter links in the chapter header.
5. [ ] Per-candidate "Use" buttons on seed page (currently pastes all 10; `chooseSeed` exists unused).
6. [ ] Inline book rename (`patchBook` exists unused).
7. [ ] Real diff highlighting (word-level LCS, ~40 lines) + "Restore this version". Right pane currently shows unsaved editor text labelled "current (vN)".
8. [ ] Settings Save feedback; re-probe Ollama after save (banner only probes once on root mount).
9. [ ] Word-count/target column + status filter on chapters index; tick on stepper phases whose artifact is non-empty.
10. [ ] Replace `alert()` on outline save with inline text; `<Link>` instead of `<a>` in root nav.
11. [ ] A11y: `htmlFor`/`id` on all editors, `aria-pressed` on POV/style toggles, `role="dialog"` + Escape on diff overlay, `role="progressbar"`.

## Suggested order
Phase 1 must-fix (one PR, about half a day) → Phase 2 items 1, 2, 4, 5 (prompt/text-heavy, one PR) → Phase 3 items 1–3 → rest.

## Review
(filled in after implementation)
