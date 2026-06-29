# govMEMnence — TODO / Roadmap

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

---

## Suggested ordering (not fixed)
Robustness/stress generator (#4) and tag-scoping decision (#8) unblock the most — do them early.
Scribe rename (#6) is cheap, do anytime. Crypto-chain (#1), police (#2), whistle-blower (#3) build
on the audit core. GUI (#5) and size-tripwire (#7) layer on once the pipeline is stable.
