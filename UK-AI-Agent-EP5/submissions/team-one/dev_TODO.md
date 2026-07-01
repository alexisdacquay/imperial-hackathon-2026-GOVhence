# dev_TODO — GOVhence live pipeline (WIP handover)

> Developer working notes for branch **`feat/govhence-pipeline`**. This is NOT the curated backlog
> (that's `TODO.md`). `main` is clean at `7f5493a`. Working-first build of `PRD.md`, reusing
> bouncer/memory/audit + stdlib (Ponytail). Keep the name **`bouncer`** (= the PRD's DeterminExtractor).
> LLM roles are rule-based **stubs** behind a clean seam (no open-weight model wired here yet); **none
> makes the access decision** (absolute rule 2).

## Status — ✅ GREEN: **102 pass** · `python pipeline.py --demo` runs the full story · **5 increments done**
> (1) working scaffold · (2) relevance ranking + top-k cap · (3) salient content-word tags + proven
> memory loop · (4) security pass (injection blocked · total on adversarial input · write-time RBAC
> scoping) · (5) scripted `--demo`. Run one turn: `python pipeline.py bob "<msg>"`.
- [x] `bouncer.MemoryItem` += `tags` (relevance only, never access)   *(committed ae9e857)*
- [x] `users.json` += `shared` category (driver; exec via `*`)         *(committed ae9e857)*
- [x] `cli.load_items` reads `tags`
- [x] `cocoshamem.seed.json` — 7 seed memories (incl. `shared` / `financials` / `legal`)
- [x] `agents.py` — Classifier / Judge / Memoriser / Responder stubs + tag hygiene
- [x] `pipeline.py` — verify → classify → relevance pre-filter → **bouncer access filter (audited)** → MemoryLane → Responder; write-path Judge → Memoriser → append runtime store; + CLI
- [x] `.gitignore` += `cocoshamem.json` (runtime store; seed committed)
- [x] `test_pipeline.py`

## ✅ Fixed — the 1 red test
`agents.memorise()` now returns `None` for a query (`cls.kind == "query"`) — defensive; the Judge
gates it upstream too. Suite green (94).

## Remaining (next increments)
- **Wire a real open-weight model** behind the `agents.*` seam (BasedAPIs) — stubs stay as the offline fallback (M8).
- **Real semantic store** + embeddings for CocoShaMem (M7); the bouncer still filters results.
- **True async** write path (thread the write side; today the read path already completes before the write).
- Pipeline revocation demo (reuse `memory.revoked_ids`); richer tag-synonym reuse.
- Fold the pipeline into the docs (README / PRD status) before merging to `main`.
- Blocking hardening for production: **R1–R3** (see `TODO.md`).

## Key design decisions (autonomous best-guesses — revisit if wrong)
- relevance = message-tags ∩ item.tags; **ACCESS is unchanged** (`bouncer.check_item`), audited.
- Memoriser assigns the access category at WRITE time: `shared` default; `financials` / `legal` if sensitive.
- runtime memory-writes → git-ignored `cocoshamem.json`, seeded from committed `cocoshamem.seed.json`.
- role→department map in `agents.ROLE_DEPARTMENT` for user tags.
- **Security property that holds:** `mem-financials` is tagged `london`, so a "london" query makes it
  *relevant* to bob (a driver) yet the bouncer still **DENIES** it (financials ∉ bob) and logs the DENY.
