# dev_TODO — GOVhence live pipeline (WIP handover)

> Developer working notes for branch **`feat/govhence-pipeline`**. This is NOT the curated backlog
> (that's `TODO.md`). `main` is clean at `7f5493a`. Working-first build of `PRD.md`, reusing
> bouncer/memory/audit + stdlib (Ponytail). Keep the name **`bouncer`** (= the PRD's DeterminExtractor).
> LLM roles are rule-based **stubs** behind a clean seam (no open-weight model wired here yet); **none
> makes the access decision** (absolute rule 2).

## Status of increment 1 — NOT green yet: `python -m pytest -q` → **93 pass, 1 FAIL**
- [x] `bouncer.MemoryItem` += `tags` (relevance only, never access)   *(committed ae9e857)*
- [x] `users.json` += `shared` category (driver; exec via `*`)         *(committed ae9e857)*
- [x] `cli.load_items` reads `tags`
- [x] `cocoshamem.seed.json` — 7 seed memories (incl. `shared` / `financials` / `legal`)
- [x] `agents.py` — Classifier / Judge / Memoriser / Responder stubs + tag hygiene
- [x] `pipeline.py` — verify → classify → relevance pre-filter → **bouncer access filter (audited)** → MemoryLane → Responder; write-path Judge → Memoriser → append runtime store; + CLI
- [x] `.gitignore` += `cocoshamem.json` (runtime store; seed committed)
- [x] `test_pipeline.py`

## FIRST thing to fix — the 1 red test
`test_pipeline.py::test_memoriser_rejects_a_bare_query` fails: `agents.memorise()` doesn't reject a
query on its own (it only checks length + tags). In the real flow the **Judge** gates this (memorise
is only called when `judge_write_candidate` is True, which already rejects queries), so pick one:
- **(a) recommended:** make `agents.memorise` return `None` when `cls.kind == "query"` — one defensive line, then re-run.
- (b) change the test to feed a statement (memorise trusts the Judge upstream).

## Then (increment 2+)
- Eyeball the CLI: `python pipeline.py bob "where can I get a sandwich in London?"` and
  `python pipeline.py bob "The London office moved to Friar Street."`
- True **async** write path (thread the write side; today it runs after the answer is composed).
- Tag-hygiene beyond case/space (near-dup reuse, e.g. `weekend`/`week-end` via `agents.SYNONYMS`).
- Wire a real **open-weight** model behind the `agents.*` seam (BasedAPIs); stubs stay as the offline fallback.
- Run the SKILL **milestone gate** each slice (reality-check · adversarial stress · security review).

## Key design decisions (autonomous best-guesses — revisit if wrong)
- relevance = message-tags ∩ item.tags; **ACCESS is unchanged** (`bouncer.check_item`), audited.
- Memoriser assigns the access category at WRITE time: `shared` default; `financials` / `legal` if sensitive.
- runtime memory-writes → git-ignored `cocoshamem.json`, seeded from committed `cocoshamem.seed.json`.
- role→department map in `agents.ROLE_DEPARTMENT` for user tags.
- **Security property that holds:** `mem-financials` is tagged `london`, so a "london" query makes it
  *relevant* to bob (a driver) yet the bouncer still **DENIES** it (financials ∉ bob) and logs the DENY.
