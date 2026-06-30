# GOVhence MEM-Ø — Product Requirements Document
### Next phase: the live memory-governance pipeline

**Status:** Draft · **Version:** 0.1 · **Owner:** team-one
**Scope:** the end-to-end runtime pipeline (intake → analysis → retrieval → response → memory-write)
built on the existing deterministic access-control + audit core.

> **Preservation note.** §4 (Data) and §5 (Process) reproduce the author's specification **verbatim**,
> with only harmless fixes (typos, spacing, punctuation, grammar). Every other section is added PRD
> scaffolding and is marked as such. Component names are unchanged.

---

## 1. Overview / Purpose
GOVhence is a permission-aware governance layer over **one** corporate shared memory (**CocoShaMem**)
used by many AI agents and users. This PRD defines the next phase: a **live message pipeline** that, for
every user message, (a) retrieves the CocoShaMem memories the user is *permitted* to see and feeds them
to a Responder, and (b) — in parallel — judges whether the message contributes information worth
memorising and, if so, quality-gates and stores it. Access is decided by **deterministic code, never an
LLM**; every decision is **RBAC/ACL-scoped, fail-closed, and audited**; all models are **open-weight**.

## 2. Glossary *(added)*
| Term | Meaning |
|---|---|
| **GOVhence (MEM-Ø)** | This project. Orchestrates the pipeline, enforces access, writes the audit trail. |
| **CocoShaMem** (CorpSharedMemory) | The corporate-wide shared memory of tagged content — reusable across the org, but every read is scoped per RBAC/ACL. |
| **Intake agent** | The front-end agent the user messages (TBD — candidate: Hermes). |
| **Judge LLM** | Assesses a message's *relevance* to CocoShaMem and its *corporate-wide usefulness* (write-candidacy). |
| **Classifier LLM** | Tags/labels the message (content tags + role/department tags), reusing existing tags. |
| **DeterminExtractor** | Strictly **script-based, NO-LLM** matcher: looks up message tags against CocoShaMem content tags to select relevant memories. |
| **Memoriser** | Write-time **quality gate**: refines a memory candidate (from the original message, no LLM expansion) and its tags before storing. |
| **Responder LLM** | Produces the final answer to the user, given the original message + the MemoryLane preamble. |
| **MemoryLane** | The preamble GOVhence prepends to the Responder's input, carrying the retrieved CocoShaMem memories. |
| **RBAC / ACL** | Role/attribute-based access scoping — each user only ever sees permitted content. |

## 3. Pipeline at a glance *(added)*
```
   user ─▶ (1) Intake agent ─▶ (2) GOVhence captures ─▶ (3) verify user + profile
                                                              │
   ── analysis ───────────────────────────────────────────────┤
     (4–5) Judge: relevance + org usefulness   (7–8) Classifier: tags (content + role/dept)
   ────────────────────────────────────────────────────────────┘
                                                              │
   READ PATH  (first stage — the answer waits for this):      │
     (10) DeterminExtractor: tag match (NO LLM) ─▶ RBAC/ACL filter ─▶ retrieve permitted memories
                                                              │
     (13) Responder LLM ◀─ original message + MemoryLane (retrieved memories)
     (14–15) GOVhence ◀─ Responder ─▶ user gets the answer
                                                              │
   WRITE PATH (parallel side-track — never blocks the user):  │
     (9) Judge: write-candidate? ─▶ (11) Memoriser quality-gate ─▶ (12) tag reuse ─▶ write CocoShaMem
```

## 4. Data

### 4.1 User information source *(verbatim)*
- name
- profile (role, department)

### 4.2 Datasource *(verbatim)*
- **simulated** (for the hackathon)
- **intended (prod):** email, SharePoint, Teams, NFS, etc.

These have strict access control already in place (simulated, for the hackathon, with a simpler
implementation — no real Domain Controller, etc.).

## 5. Process — end-to-end pipeline *(verbatim spec, grouped into phases for hierarchy)*

### Phase A — Intake & identity
1. User sends a message to **[intake agent — TBD: Hermes agent?]**.
2. GOVhence (our project) captures the message.
3. GOVhence verifies user and profile.

### Phase B — Analysis & candidacy
4. GOVhence asks a **Judge LLM** (e.g. GSM-5.2) to analyse the message for possible relevance to the
   CorpSharedMemory (CocoShaMem).
5. GOVhence's Judge LLM analyses what it is about, and whether it contains information useful to the
   organisation. It could be a candidate for storing information in CocoShaMem.
6. Whether or not the **Classifier LLM** identifies the user message as a query/question rather than a
   statement, in all cases the message is a candidate for receiving CocoShaMem enhancements — additional
   context and memory retrieval.
7. The Classifier LLM classifies the user message with tags/labels that summarise its content, context,
   or relation, and also assigns user-based tags such as role and department. Where possible — since
   CocoShaMem aims at corporate-wide reusability — the stored content should not be unique to a single
   user but aimed at general usefulness (albeit scoped per RBAC/ACL).
8. This classification is used to match relevance. For example, the message "where can I find the best
   sandwich" relates to food, location, etc.
9. The Judge LLM assesses usefulness. In the sandwich example, since it is a query without additional
   context, the corporate-wide usefulness is limited — so it is **not** a candidate for adding content to
   memory. In another example, if the user message is "No, no sandwiches in Tokyo, we are in London!",
   then: first, it indicates the user is sharing useful information; second, it can be relevant to the
   organisation that future queries carry the context `location: London`. So it is a **double candidate**:
   (a) an implicit desire from the user to be memorised; and (b) useful shared information to add into
   CocoShaMem.

### Phase C — Deterministic retrieval
10. The **DeterminExtractor** is script-based code (strictly **NO LLM**) that looks up the message tags
    and matches them against CocoShaMem content tags.

### Phase D — Memory quality gate (write candidate)
11. If the Judge LLM deems the user message of possible interest — based on the Classifier's summary —
    for content addition to expand CocoShaMem, the candidate memory is inspected by the **Memoriser**. It
    reviews the original user message **not** for quick assessment, but for quality memory content that
    would be useful to other members of the organisation, whether in the same department or not. This is a
    quality gate for the memory candidate. The memory can be improved at this stage — not from LLM
    expansion/inference, but based on the original user message, for authenticity and accuracy. The tags
    are also revisited for accuracy and relevance.
12. The Classifier and the Memoriser should reuse existing tags when possible and suitable (with security
    in mind). For example, "location" and "Location" should not be duplicated; likewise "Weekend" or
    "week-end". Tags should be single-word, or hyphenated if they must be multi-word. Both must do due
    diligence in attempting to reuse existing tags without unnecessary proliferation.

### Phase E — Response
13. Whether or not memory assistance was used from CocoShaMem (with some memory extraction, or none),
    the message is passed to the **Responder LLM**, which receives both the original user message and a
    **"MemoryLane"** preamble that GOVhence appends with the CocoShaMem memories.
14. GOVhence receives the Responder's message.
15. GOVhence sends the Responder's response to the user.

### Phase F — Asynchronous memory-write
16. Writing new memories (Memoriser activities) can happen **in parallel** with the user receiving their
    answer from the Responder; the user should not need to wait for memories to be added first.
    Memorising new memories is a side track. But accessing existing memories (tag-based) is a first-stage
    step **before** GOVhence passes the user message + memories to the Responder LLM.

## 6. Mapping to the current build *(added — what exists vs. what's next)*
| PRD component | Today (in repo) | Next / roadmap |
|---|---|---|
| **DeterminExtractor** (no-LLM tag match) | `bouncer.py` → `check_item()` / `retrieve()` (deterministic, fail-closed) — **done** | extend matching to tag-set retrieval over the store |
| **CocoShaMem** (store + tags) | `memory_store.json` + `memory.py` tag resolution — **done (stub)** | **M7** real semantic store + open-weight embeddings (bouncer still filters) |
| **RBAC/ACL + fail-closed + audit** | `memory.py` (`allowed_categories_for_user`), `audit.py` (chain + checkpoint/anchor) — **done** | — |
| **Classifier LLM** + **Memoriser** | not built | **#6 "Scribe"** (write-time tagging) + **#8** tag-scoping discipline |
| **Judge LLM** (read-time relevance/usefulness) | not built | **net-new** (legal only if it reads permitted content + never makes the access decision) |
| **Responder LLM** + **MemoryLane** | not built | **net-new** (M7/M8 outline the pipeline but don't name these) |
| Write-time tagging | not built | **M8** — label only, never decide |

## 7. Non-functional requirements *(added)*
- **Open-weight models only** (Llama/Qwen/Mistral via BasedAPIs) — no closed models anywhere in the loop.
- **No LLM in the access decision / extraction.** The DeterminExtractor is pure script code; enforcement
  is deterministic and lives at the retrieval layer. LLMs may classify/judge/respond, never *gate*.
- **RBAC/ACL, fail-closed.** Untagged content = DENY; every read scoped to the user's permitted set.
- **Audit.** Every retrieval decision (ALLOW + DENY) logged; append-only, tamper-evident, complete.
- **Async memory-write.** The read/retrieval path is first-stage and may block the answer; the write path
  (Judge→Memoriser→store) runs in parallel and must **not** block the user.
- **Tag hygiene.** Reuse existing tags; single-word or hyphenated; no near-duplicate proliferation
  (`location` vs `Location`, `weekend` vs `week-end`).
- **Latency.** Target sub-200ms P99 for permission checks.
- **Portability.** Runs identically on Windows + macOS (enforced by `.gitattributes` + the CI matrix).

## 8. Absolute rules this pipeline must honour *(added — see SKILL.md / HANDOFF.md)*
1. **Strict exact-match enforcement, FAIL-CLOSED** at read time — never normalize/interpret/LLM-guess.
2. **No LLM in the access decision** — a model may classify/label at **write time only**.
3. **The audit log is a legal record** — complete, append-only, tamper-evident, fail-closed on log error.
4. **Enforcement + logging live at the retrieval layer** (inside the gate), not an app layer above it.

## 9. Blocking dependencies *(added — must close before the live pipeline ships)*
- **R1 — concurrent audit writes not serialized** (seq-race forks the hash chain). *Fix: serialize
  writers (queue / SQLite WAL) or sharded chains + Merkle root.*
- **R2 — audit write not total on two adversarial values** (oversized CSV field; unpaired surrogate →
  raw crash, bricks the log). *Fix: cap field length + wrap any failure as `AuditError` (fail closed).*
- **R3 — derived memory doesn't inherit its source's access constraints.** *Fix: at write time the
  Memoriser/Scribe tags a derived unit with the **most-restrictive** parent tag (ties to #8).*

## 10. Open questions / TBD *(added)*
- **Intake agent** (step 1): Hermes, or another front-end? Define the interface to GOVhence.
- **Judge model** (step 4): "GSM-5.2" is a placeholder — choose a concrete **open-weight** model.
- **Judge at read time:** confirm the Judge only *influences relevance/retrieval*, and the
  **DeterminExtractor remains the sole access gate** (rule 2). The Judge must read only permitted content.
- **Governed unit granularity** (ties to #8): chunk/record-level tagging for store + retrieval.
- **Memorisation consent:** is the "implicit desire to be memorised" sufficient, or is explicit
  user/operator consent required before writing to a corporate-wide store?
- **Datasource integration:** simulated now; define the real connectors (email/SharePoint/Teams/NFS) and
  how their existing ACLs sync into CocoShaMem scoping.
