# GOVhence MEM-Ø — Roadmap

> Deferred / future work, kept out of the authoritative spec ([PRD-2026-07-01.md](PRD-2026-07-01.md))
> so the spec stays lean. Items here are intended, not yet committed to a milestone.

## Write path

- **Memoriser — second run of verifications.** An extra precision/security pass by the Memoriser LLM
  before a memory candidate is committed to CocoShaMem. The first pass (per the authoritative spec) takes
  the Judge's memory candidate + tags, reuses existing tags to avoid duplication, and writes. This
  roadmap item adds a follow-up verification run (e.g. re-check tag accuracy, sensitivity/access
  category, and quality) as a second gate before the write is finalised. Deferred from
  [PRD-2026-07-01.md](PRD-2026-07-01.md) (§ Roadmap pointer).
