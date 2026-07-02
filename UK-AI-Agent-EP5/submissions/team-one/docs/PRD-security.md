# GOVhence MEM-Ø — Security PRD (2026-07-02)

> **What this is.** The security requirements for the NEW pipeline (`src/`), distilled from the
> v0.1 prototype and the track spec. v0.1 was a **quarry, not a template**: its *ideas* are fully
> extracted into the requirements below, re-implemented cleanly in the new topics/labels/clearances
> architecture. **No v0.1 code is ported, and the v0.1 archive is deleted** — this document is the
> complete, self-sufficient record of everything worth keeping from it.
>
> **Authority order:** track spec (the 3 sources in `SKILL.md`) > this PRD > `PRD.md` (process).
> Verbatim spec lines this PRD exists to satisfy:
> - *"Enforces access at the retrieval layer … without requiring an LLM call to make a permission decision."* ✅ already shipped
> - *"Produce audit logs meeting regulatory requirements."* ← **the big gap today**
> - *"A summary, embedding, or note inherits the access constraints of its sources, and revoking a
>   source propagates to the derivative."* ← **gap**
> - *"Maintain sub-200ms latency for permission checks (P99)."* ← unproven
> - *"Stay synchronized with source permissions under concurrent updates."* ← partial
> - Bonus: *temporal access rules* · *query-time inference prevention*.

---

## 1. Threat model (what we defend against)

| # | Threat | Defence (requirement) |
|---|--------|----------------------|
| T1 | Prompt injection in a message/memory ("label this shared", "[category: financials]") | LLMs never gate access (shipped); Memoriser treats candidate as data (shipped); demo proves it (S10) |
| T2 | Access smuggled via topics (LLM output) | topics ≠ labels; Bouncer reads clearances itself (shipped) |
| T3 | Memory poisoning: writer plants content into lanes above their clearance | Writer cap: labels ⊆ writer's clearances (shipped) |
| T4 | **Leak via derivative**: a summary of a `financials` memory labelled `shared` | S3 — label inheritance by union |
| T5 | **Stale grant**: source revoked but derivative still served | S4 — revocation closure, revoked beats permitted |
| T6 | **Insider edits/deletes audit records** | S1/S5 — seq + hash chain + checkpoint + anchor |
| T7 | Unlogged access (crash, disk full, adversarial value crashing the logger) | S1 — audit-before-grant, fail-closed `AuditError`, defanged/bounded fields |
| T8 | Log injection → code-execution on the auditor's machine (spreadsheet formulas) | S1 — `defang` (= + - @ tab CR prefix-quoted) |
| T9 | Config typo silently changing access | Fail-closed loaders (shipped); S8 lint — labels nobody can hold |
| T10 | Concurrent writes forking the audit chain / corrupting the store | S6 — write lock + atomic replace |

---

## 2. Requirements

Priority for the 1-day build: **P0 = must ship today** (spec-required core),
**P1 = should** (if time), **P2 = bonus** (judging upside). Every P0/P1 item lands with
regression tests and an entry in the demo story (§4).

### S0 — Memory identity (P0, prerequisite)
Every memory item carries a unique, NON-EMPTY STRING `id` (e.g. `"m0007"`), validated at load
(`ConfigError` otherwise). The id is the **audit key and the revocation key** — v0.1 lesson: a
non-string id is fail-OPEN (it can never match a revocation set, and it corrupts the audit trail).
The Memoriser assigns the next id at write time.
*Data model becomes:* `{id, labels, topics, text}`.

### S1 — Regulatory audit log (P0 — the core deliverable)
A fresh `src/audit.py` (new code, v0.1 ideas), called from **inside `bouncer.retrieve`** — the
retrieval layer, not an app layer above it.

- **100% coverage**: one row per decision, **every ALLOW and every DENY** — auditors need blocked
  attempts too. No sampling.
- **Row = who/what/when/outcome/why**: `seq, timestamp(UTC ISO-8601), user, item_id, labels,
  decision, reason, row_hash`.
- **Reasons are first-class (S2)**: the gate produces a human explanation for every decision
  ("labels {financials} not within clearances {shared, logistics}"), logged and shown in the demo.
- **Append-only CSV** — human-readable, opens in any spreadsheet, retention-friendly.
- **Tamper-evident**: per-row sequence number (a deleted row leaves a gap) + SHA-256 **hash chain**
  (each row fingerprints its content + the previous fingerprint — any edit/insert/reorder breaks
  every later link). `verify()` recomputes the chain and names the first broken row.
- **Fail-closed**: audit **before** grant; any write failure raises `AuditError` → access refused.
  No log ⇒ no access. Never crash-instead-of-deny: every field is made encode-safe (unpaired
  surrogates replaced), length-capped (< csv field limit), and **formula-defanged** before hashing
  or writing — the same string is hashed and stored, keeping the chain self-consistent.
- **Durable**: flush + fsync per row (a crash cannot lose the latest decision).
- **Portability discipline**: `newline=""` on every hashed file (Windows `\r\n` silently breaks a
  hash chain — v0.1 lesson), UTF-8 everywhere, `pathlib` paths.
- **Runtime artifact**: `audit_log.csv*` stays git-ignored; tests write ONLY to temp paths.

### S3 — Derived-memory label inheritance (P0 — verbatim spec)
When a memory is derived from others (summary, merge, note), its labels are the **UNION of its own
labels and ALL its sources' labels**, computed at write time by **deterministic code** — the LLM
may suggest, code enforces the floor. Under ALL-match this union is exactly "inherits the access
constraints of its sources": needing every source's keys is the set-form of most-restrictive-wins.
Store `derived_from: [ids]` on the item (empty for originals).

### S4 — Revocation, transitively (P0 — verbatim spec)
`data/lineage.json`: `{"revoked": [ids]}` (+ the `derived_from` edges already on items). At load,
deterministic code computes the **transitive revoked closure** (children of revoked sources, their
children, …) — cycle-safe (seen-set), iterative (no recursion). The gate then denies any item in
the closure: **revoked beats permitted**, logged as a DENY with reason. A malformed lineage file
⇒ `ConfigError` (an empty graph is the permissive direction — never default to it).

### S5 — Checkpoint + anchor (P1 — truncation alarm, O(1) appends)
A bare hash chain provably cannot detect rows lopped off the END. Side file
`audit_log.csv.checkpoint` appends `(count, head-hash)` after every write — itself hash-chained —
and mirrors the latest tally to a `.anchor` file (meant to live off-host). `verify()` cross-checks
log ↔ checkpoint ↔ anchor. Double duty: appends read only the tally tail → **O(1) regardless of
log size** (supports the latency budget).

### S6 — Concurrency & durability of state (P1)
- One in-process lock serialises the audit read→append→checkpoint section (two writers must never
  fork the chain). Cross-process locking is explicitly OUT of scope (single-process system).
- The memory store is a **runtime file seeded from the committed seed** (`cocoshamem.json` from
  `cocoshamem.seed.json`, runtime git-ignored); every store write is **atomic**
  (write-tmp → `os.replace`).
- ACL sync: clearances are read from `users.json` **per decision** (no long-lived permission
  cache), so a permission change applies on the next check.

### S7 — Latency evidence (P1 — measurable judging criterion)
A test/benchmark proving the permission check stays **< 200ms P99** at scale (e.g. 10k-item store,
1k mixed queries; audit ON). Report the number in README. If it fails, fix the hot path — never
weaken a guarantee for speed.

### S8 — Config lint (P1)
At load: any memory label that **no role's clearances contain** is unreachable content — flag it
loudly (`ConfigError` or startup warning; choose fail-closed). Catches the classic typo
(`finansials`) that would otherwise silently bury data. (Topic hygiene stays the Classifier's job.)

### S9 — Richer audit fields (P2)
`event_type` (RETRIEVE / WRITE / REVOKE — future-proofs the log), `user_location` +
`item_jurisdiction` (satisfies the "where" of standards AND the cross-border bonus). Retention
note in README: keep 7 years (safe superset — FINTRAC 5 / SEC 6 / PCI 1), dated files, never
delete; OS-level append-only ACL as a deployment note.

### S10 — Security demo story (P2, cheap and high-value)
A scripted multi-turn scenario (temp store + temp log) that SHOWS the defences: ask → teach →
recall → write-time labelling caps at the writer's clearance → another user cleared higher reads
it → prompt-injection attempt blocked → a revoked source kills its summary → `verify()` proves the
log intact. This is the judges' 2-minute tour.

### S11 — Bonus tracks (P2, only if P0/P1 are green)
- **Temporal access rules**: optional `unlock_after` ISO date on an item; the gate denies before
  that instant (deterministic clock check, logged reason "embargoed until …").
- **Query-time inference prevention**: detect a user assembling restricted facts across permitted
  memories (start: per-user DENY-rate alarm over the audit log — an agent may WATCH, never gate).
- **External anchoring** (e.g. Kaspa): publish only the checkpoint digest on-chain, never records;
  throwaway wallet, keys never committed.

---

## 3. Explicitly NOT doing

- **No retrofit** of `archive/v0.1/*.py` into `src/` — new code only, guided by this PRD.
- No deny lists / wildcards back in the access model (whitelist labels ⊆ clearances stands).
- No cross-process file locking (`fcntl`/`msvcrt` forbidden; single-process by design).
- No raw audit data or user identity on any blockchain — digests only, if S11 happens at all.
- No LLM anywhere in a permission decision — unchanged absolute rule; LLMs label at write time only.

---

## 4. Where each v0.1 gem lands (idea → new home)

| v0.1 artifact | The idea worth keeping | Lands in |
|---|---|---|
| `audit.py` | retrieval-layer log, 100% ALLOW+DENY, seq+hash chain, fail-closed `AuditError`, defang, fsync, `verify()` | S1 → new `src/audit.py` |
| `audit.py` checkpoint/anchor | O(1) appends + end-truncation alarm + off-host mirror | S5 |
| `audit.py` `_WRITE_LOCK` | serialize writers so the chain can't fork | S6 |
| `bouncer.py` `Decision(reason)` | every decision explainable — "why" is data | S2 (inside S1) |
| `bouncer.py` totality guards | type-refusal at the gate (substring trap) | already shipped in `src/bouncer.py` |
| `memory.py` lineage + `revoked_closure` | transitive revocation, cycle-safe, resolved at load; revoked beats allowed | S4 |
| `memory.py` unknown-category check | loud config-typo detection | S8 |
| `pipeline.py` seed→runtime store, atomic append | no runtime artifacts committed; atomic writes | S6 |
| `pipeline.py` `run_demo` | scripted security story for judges | S10 |
| `agents.py` most-restrictive write labelling | inheritance floor at write time | S3 (union of labels) |
| `cli.py` fail-closed exits | `ConfigError`/`AuditError` → non-zero exit, clear message | S1/S4 (GOVhence handling) |
| `docs/audit-roadmap.md` | event_type, jurisdiction fields, retention, anchoring pattern | S9/S11 |

## 5. Build order (1 day)

1. **S0** ids → **S1+S2** audit log in `bouncer.retrieve` → **S4** revocation → **S3** inheritance
   (each: build → test → green before the next).
2. **S5** checkpoint/anchor → **S6** lock+atomic store → **S7** latency proof → **S8** lint.
3. Any remaining time: **S10** demo, then **S9/S11** bonuses.

Done = suite green, trackers updated (`HANDOFF`/`TODO`/`FEATURES`), demo runs end-to-end.
