# GOVhence MEM-Ø — TODO / Roadmap

> Master backlog. Easy to find for humans and AI: this is `TODO.md` at the project root.
> Status legend: `[ ]` not started · `[~]` in progress · `[x]` done.
> Each item is numbered and self-contained. Audit-log deep notes live in [ToDo_audit-log.md](ToDo_audit-log.md).

---

## Already done (for context)
- [x] **D1** Deterministic bouncer — strict exact-match, fail-closed access control.
- [x] **D2** Append-only audit log at the access layer (who/what/when/outcome/why, UTC).
- [x] **D3** Tamper-evidence v1: per-row sequence number + SHA-256 hash chain + `verify()`.
- [x] **D4** Fail-closed logging (no log → no access) + spreadsheet-injection defang.
- [x] **D5** Role-based config in `users.json` (allow / deny / wildcard), validated + fail-closed.
- [x] **D6** Lineage revocation — revoke a source → propagates to all derived items (`lineage.json`).
- [x] **D7** 52 automated tests; blog-style README.

---

## New backlog (numbered)

### 🔴 Priority — security hardening (from the 2026-06-30 adversarial red-team + stress harness)
> Surfaced by the multi-agent red-team and the adversarial stress harness (39k+ cases).
> Listed FIRST: these are correctness / availability gaps in the audit + access core.
> (The end-truncation gap found alongside these is already CLOSED by the checkpoint/anchor.)
- [ ] **R1. Concurrent audit writes are not serialized (seq-race).** Two callers writing to the
  same log at once both read the same last seq+hash (no lock) → duplicate seq → the hash chain
  forks and `verify()` breaks permanently, and both accesses are served before any verify runs.
  The O(1) checkpoint did NOT fix this. Fix: serialize writers — a single-writer queue, SQLite
  WAL, or the sharded-chains-+-Merkle-root design (which also scales and pairs with #1 anchoring).
  **Not a file lock.** (Spec: *"stay synchronized with source permissions under concurrent updates."*)
- [ ] **R2. Audit write is not TOTAL on two adversarial values (crashes instead of failing closed).**
  (a) A field larger than Python's CSV limit (~131 072 bytes) raises `csv.Error` on the next read —
  not an `OSError`, so it escapes `AuditError`, crashes `cli.main` (which catches only
  ConfigError/AuditError), and permanently bricks reading the log. (b) An unpaired UTF-16 surrogate
  (e.g. `\ud800`) as a category raises `UnicodeEncodeError` on hash/CSV write — same uncaught-crash
  path. Fix (cheap, like the loader-totality fix): cap field length and wrap the write so ANY failure
  becomes `AuditError` (fail closed), never a raw exception.
- [ ] **R3. Derived memory does NOT inherit its source's access constraints (possible leak).** Today
  only REVOCATION propagates down the lineage; a derived item (summary/embedding) is gated purely by
  its OWN tag. So a summary tagged `schedules` derived from a `financials` source is served to a user
  who may NOT see financials. The spec explicitly requires: *"a summary, embedding, or note inherits
  the access constraints of its sources."* Fix: at WRITE time (Scribe, #6/#8) the derived unit must
  carry the MOST-RESTRICTIVE tag across itself + all its sources. Directly relates to the
  content-channel gap documented in #8.

### Integrity & non-repudiation (crypto-chain)
- [ ] **1. Crypto-chain certification of logs.** Strengthen the audit log so records are
  **non-corruptible, non-changeable, and non-refutable**. The current SHA-256 hash chain (D3)
  makes tampering *detectable*; this item adds **non-repudiation** — each record (or each daily
  batch) is **cryptographically signed** so a record cannot be forged or denied later.
  Approach: HMAC (shared secret) first as the stdlib-simple option, then optionally asymmetric
  signatures, then external **anchoring** (publish only the chain's latest hash to an outside
  place — a separate append-only file now, a chain like Kaspa later). Anchor the *hash only*,
  never raw records. (See [ToDo_audit-log.md](ToDo_audit-log.md) for the standards basis.)

### Autonomous security agents
- [ ] **2. "Police" agent — continuous security/rules scanner.** A standing agent that watches
  activity around security and the rules and flags violations: attempted access patterns, repeated
  denials, config drift, anything breaking the absolute rules. It does NOT make access decisions
  (the deterministic bouncer keeps that) — it *monitors and alerts*. Output is itself logged.
- [ ] **3. "Whistle-blower" agent — anomaly scanner over the logs, on its own crypto-chain.**
  Scans the audit log for anomalies and writes its findings to a **separate, independently
  crypto-chained** alert log. Key property: **the message cannot be killed even if the messenger
  is.** If the whistle-blower process is stopped/tampered, or its findings are deleted, the gap is
  detectable (sequence + chain), and ideally the alert chain is anchored/mirrored outside the
  host so "accidentally killing the messenger" cannot erase the message. Tamper-evident by design.
- [ ] **9. "Whitehat" agent — LIVE, ongoing penetration testing in production.** A standing agent
  that continuously exercises the running system — **not just a pre-prod robustness test, but live
  during real production.** It behaves in two modes, interleaved:
  - **a) Normal user** — gentle, ordinary, well-behaved access (the baseline). Proves the happy path
    keeps working under a real, varied load.
  - **b) Attacker** — actively probes for weaknesses: malformed/injection inputs, fail-open attempts,
    boundary escapes, repeated/abusive queries. **Crashing is acceptable; finding a HIDDEN issue is
    far better than a false negative.** The whole point is to surface latent leaks/holes *before* a
    real attacker does — silence is failure if a hole exists.
  - **Guiding principle — verify by trying, not by trusting.** A real guard does not glance at the
    chained gate and believe it is locked; they *rattle it*. The whitehat physically tries the locks
    rather than asserting they hold — active verification, every round.
  - **Proof-of-presence (RFID-tap analogy).** Like a security guard who must tap RFID tokens
    dispersed around the building to *prove the rounds were actually walked*, the whitehat must leave
    **crypto-chained fingerprints** in the file and in the log at each checkpoint — a tamper-evident,
    non-repudiable trail showing *what it did, where, and when*. If the whitehat skips a round, goes
    silent, or is killed/disabled, the **missing taps are detectable** (sequence + chain gap), so
    "the watchdog was quietly switched off" cannot pass unnoticed.
  - **Demonstrable behaviour.** The agent must be able to *show* it is doing both jobs: a stream of
    benign activity AND a stream of attacks, each fingerprinted, each landing in the audit/alert
    trail — so an auditor (or judge) can see the live red-team is genuinely running, not faked.
  - Relates to #2 (police = monitor/alert), #3 (whistle-blower = anomaly + uncloseable message),
    #1 (crypto-chain), and #4 (the stress/demo generator supplies its attack payloads). Together
    these four form a continuous, self-proving, tamper-evident security harness *inside* the product.

### Robustness, stress-test & demo data
- [ ] **4. Randomised user/data generator (robustness + demo).** One module that generates
  randomised source-user data and queries with a *mindful* mix of:
  - innocent mistakes (typical low-IT-skill user error: wrong case, stray spaces, typos),
  - malicious input (wrong/special characters, emojis, prompt-injection attempts — "ignore previous
    instructions", repeated queries, special chars).
  Goal: **harden** the system and **prove** it holds. Two modes share the generator:
  - **Stress-test mode:** large scale, hammer the system — it must HOLD, with **zero false
    negatives** (no leak ever slips through). All leaks should already be caught beforehand.
  - **Demo mode:** small, **human-readable**, interesting — a curated variety of good accesses and
    good rejections (including injection attempts cleanly rejected). Same generator, different
    scale + curation.

### GUI / visuals
- [ ] **5. Modern, sleek GUI showing the interaction pipeline (demo + normal mode).**
  Progress-bar / staged visual of each interaction:
  1) user logged in → 2) user mapped to profile + ACL/RBAC → 3) LLM (real / scripted-demo /
  judge-live) uses the shared memory and writes to it → 4) **Scribe** (our agent — rename, see #6)
  annotates the new memory with our defined tags → 5) the AI reads, with limited access →
  6) a visual signal showing the access decision and the check result (ALLOW/DENY, why).
- [ ] **10. GUI — live Whitehat panel (show the pen-test, don't hide problems).** A distinct GUI
  area that surfaces the Whitehat agent (#9) in real time:
  - **Progress & stages** — what the whitehat is doing right now (normal-user round vs attack round),
    its activity stream, and its "RFID-tap" proof-of-presence checkpoints as they land.
  - **Pen-test activities & results** — each probe attempted and its outcome (held / crashed /
    leak-found), with running counts.
  - **Issues found are SHOWN, never hidden.** Surface every problem the whitehat finds — open a
    visible "Issues" list with severity + repro, linked to the audit/alert trail. Transparency is the
    point: a green board that hides a real hole is a failure; an honest red flag is a success.
  - Ties to #9 (whitehat), #2/#3 (police/whistle-blower feed it), and #5 (same GUI pipeline).
  - *Why it matters:* demonstrates to judges/auditors that the live red-team is genuinely running
    and that the system reports its own weaknesses honestly — the opposite of security theatre.

### Naming
- [ ] **6. Rename the tagging/annotation agent to "Scribe".** The write-time agent that classifies
  content and writes category tags onto memory. "Scribe" reads better than current naming. Apply
  across code, README, and the skill. (No agent-naming exists in code yet, so this is clean.)

### Lightweight leak detector
- [ ] **7. Size/length check as a cheap leak tripwire (no re-hash, no LLM).** Re-checking access
  with an LLM is slow; re-hashing every read costs CPU. Instead, store **simple metadata alongside
  the tags — e.g. the expected character/byte length** of each memory unit. On read, compare actual
  vs expected length: a **mismatch flags a possible leak/corruption** cheaply (a size counter, not a
  cryptographic hash). Decide: is this per-unit metadata, and does a mismatch DENY (fail-closed) or
  just ALERT (feed the police/whistle-blower #2/#3)? Recommend: ALERT + log; DENY only if the unit's
  integrity is part of the access contract.

### The big design question — ACL/RBAC tag scoping
- [ ] **8. Carefully scope what a tag attaches to (the unit of governance).** Today a tag attaches
  to a whole `MemoryItem`. We must decide the **granularity** deliberately, because the wrong choice
  is "too easy to escape" (via injection or plain user error). Is the governed unit a line? a
  paragraph? a RAG chunk? a vector? a whole file? **Guidance / recommended direction:**
  - **Govern at the *chunk/record* level** (the unit that is independently stored AND independently
    retrieved). The tag must travel with the *exact* unit that retrieval can return — never broader.
  - **One tag per unit, set at WRITE time by Scribe, immutable thereafter** (read-time never
    re-tags — that's the absolute rule). Mixed-content units must be SPLIT before tagging, never
    tagged with the more-permissive label.
  - **A unit with no tag = DENY** (fail-closed). Untagged content is never retrievable.
  - **The tag must live in trusted metadata, NOT inside the user-controllable text** — otherwise
    injection ("...\n[category: public]") could forge a tag. Tag is structural, content is data;
    never parse the tag out of the body.
  - For **vectors/RAG**: the tag is metadata on the vector record, and the permission filter is
    applied to the candidate set BEFORE results are returned (pre-filter, not post-filter), so a
    forbidden chunk is never even a candidate.
  - Pairs with #7: the size metadata helps detect a unit that was tampered to smuggle extra content
    across a boundary.
  - **Action:** write a short design note fixing the unit = chunk/record, the write-time-immutable
    rule, fail-closed-on-untagged, and tag-in-metadata-not-body — then enforce it in the store (M7).
  - **Red-team finding (2026-06-30) — the CONTENT-CHANNEL leak this item must close.** The read gate
    decides on the TAG only and NEVER inspects the unit's TEXT (by design: no LLM at read time, rule 2).
    So a unit correctly tagged with an *allowed* category whose BODY carries *forbidden*-category
    content is served verbatim to an unauthorized reader. The gate cannot and should not catch this —
    the defense MUST live at WRITE time. Concrete failures this item must prevent:
    - **Mixed-content unit:** a `schedules` item whose text also contains
      "`… [FINANCIALS] Q3 revenue 4.2M, margin 18%  [LEGAL] penalty clause £50k`" — `bob` (no
      financials/legal) receives all of it, because the carrier tag `schedules` is allowed.
    - **Mis-tagged / poisoned unit:** content written under a more-permissive tag than its true
      sensitivity (author error, or an injection that plants content under a benign tag).
    - **Required rules (defense is all write-time):**
      1. **Split mixed-content units BEFORE tagging** — never tag a mixed unit with the more-permissive
         label; each governed unit must be single-sensitivity.
      2. **Tag = the MOST-RESTRICTIVE category present** in the unit, never the most permissive.
      3. The write-time classifier (**#6 "Scribe"**) classifies on the ACTUAL content, not the author's
         claimed tag; a unit whose content out-ranks its tag is re-tagged up or split.
      4. Governed unit small enough (chunk/record) that "one unit = one sensitivity" actually holds.
    - Pairs with **#6** (Scribe classifies content), **#7** (size tripwire flags a unit that grew after
      tagging), and the metadata-not-body rule above (so injection can't forge the carrier tag).

---

## Suggested ordering (not fixed)
Robustness/stress generator (#4) and tag-scoping decision (#8) unblock the most — do them early.
Scribe rename (#6) is cheap, do anytime. Crypto-chain (#1), police (#2), whistle-blower (#3) build
on the audit core. GUI (#5) and size-tripwire (#7) layer on once the pipeline is stable.
