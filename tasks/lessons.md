# Lessons

## 2026-11-07 — v2 build
- Before an end-to-end run, kill every leftover server process on the ports you will use (`Get-NetTCPConnection -LocalPort ...`). A stale backend from an earlier agent's launcher test served old code and cost ~20 minutes of misdiagnosis.
- Functional `setState(prev => ...)` updaters run lazily; never compare `prev` against a ref you mutate in the same effect. Capture the old ref value first.
- Bash heredocs on this Windows setup mangle `
` and apostrophes inside Python source; use the Write/Edit tools for anything with escapes.
- When a subagent reads a backend contract that another subagent is still writing, expect "mismatch" reports that are already resolved; check the current code before acting on them.
- Scanner per-rule caps hide the worst failure mode (paragraph loops). Any "max N findings" rule needs a companion ratio metric that cannot be capped.
- A mechanical scan cannot judge quality; pair it with one strong-model critic read per run. The critic found the loop the scanner undercounted and the exemplar paste the scanner labelled as 6 findings.
- For small local models the decode-side knobs (repeat_penalty, repeat_last_n) matter more than any prompt wording; set them first, then tune prompts.
