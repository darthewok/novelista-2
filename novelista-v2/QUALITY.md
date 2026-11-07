# Quality log

Records what the guardrails catch, so a prompt or scanner change can be shown to help or hurt. Add a row per generated test chapter: tells per 1000 words before and after polish.

## Guardrails in place (v2)

1. Prompt-side: merged anti-slop lists (54 Tier 1 entries, 37 Tier 2, 25 Tier 3 fillers, structural rules), craft rules with the Stability Trap, voice document with exemplars, canon and running summary in every draft and revise call.
2. Mechanical scanner (`backend/app/pipeline/slop_score.py`, no LLM): 18 rules. Tier 1 words and canon contradictions are errors and block `polished`. The scanner reads its word lists from `prompts/anti_slop.md`, so the prompt and the scanner cannot drift.
3. Editor pass (`editor_pass.py`, editor model): quoted findings, never a score; rendered as a five-section revision brief.

## Runs

| Date | Provider | Chapter | Words | Tells/1000 before | After polish | Notes |
|---|---|---|---|---|---|---|
| 2026-11-07 | fake provider (canned prose, 2 planted Tier 1 phrases) | ch 1 | 159 | 19.0 (3 errors: 2 tier1, 1 short-chapter) | n/a (fake editor returns prose, not JSON; brief fell back; errors remained; status correctly stayed `drafted`) | Both planted phrases ("delve into", "a testament to") caught with line numbers. |
| 2026-11-07 | Ollama qwen3.5:4b | Chrome Trigger, 6 ch | 12,135 | 8.3 (54 errors, 47 warnings; copied_text 27, repeated_phrase 25, exemplar_copy 14, tier1 11) | ch 4 polish: 10 -> 10 tells; brief had no scanner input, revise ignored tier-1 phrases | Pipeline v2.0 prompts. Critic: exemplar pasted into ch 1, ending spoiled in ch 1, whole paragraphs copied across chapters, Rex dies four times, outline meta-words in prose, LaTeX in outline. Rescanned with the v2.1 scanner for comparability. |
| 2026-11-07 | Ollama qwen3.5:4b | The White Forge, 6 ch | 11,140 | 6.2 (34 errors, 35 warnings; repeated_phrase 25, copied_text 24, exemplar_copy 6, tier1 4) | ch 3 polish: 16 -> 14 tells, tier-1 cleared by slop_fix, copied_text remained | Pipeline v2.1 (scope fence, state line, used-phrase list, POV lock, scanner-fed brief, slop_fix, 6 new rules). Critic: ch 1-2 clean of exemplar, ending not spoiled early, openings vary; but ch 5 is ~80% a looping paragraph block, exemplar moved to ch 5, refrains still repeat. Verdict: marginally better; biggest remaining problem is verbatim regurgitation (decode-side loops). |

| 2026-11-07 | Ollama qwen3.5:4b | The White Forge ch 5 redraft (was 59 paragraphs / 13 unique) | 1,185 | 0.8 (0 errors, 1 short-chapter warning) | n/a | Pipeline v2.2: repeat_penalty 1.15 + repeat_last_n -1, paragraph-loop guard, motif allow-list, in-chapter dedupe. No loop, no copies; prose turned clipped and the chapter came in short — the penalty is a calibration knob (`providers.ollama.repeat_penalty`), try 1.1 if prose reads choppy. |

Next lever applied after run 2: `repeat_penalty` 1.15 / `repeat_last_n` -1 on Ollama, `frequency_penalty` 0.3 on OpenAI-compatible, motif allow-list, in-chapter dedupe, paragraph-loop guard with one automatic redraft. A stronger model (Sonnet/Opus via key, or a 30B+ local model) is expected to remove the loop class entirely; the 4B numbers are the floor, not the target.
