# Helix Agent Task Index

> **Start here:** MASTER_TODO.md is the canonical cross-agent roadmap and handoff ledger.

## First read

1. MASTER_TODO.md — canonical state, roadmap, decisions, unresolved work, and change ledger.
2. AGENTS.md — mandatory agent operating rules.
3. ROADMAP_BETA_TODO.md — existing beta roadmap; reconcile changes into the master ledger.
4. README.md / README_CURRENT.md — active entrypoints and current repo structure.

## Continuity rule

Every agent change must update MASTER_TODO.md in the same change set.

Before editing:
- Read the relevant master roadmap section.
- Inspect current implementation.
- Identify behavior that must be preserved.
- Choose one small implementation slice.

After editing:
- Update the Change Ledger.
- Record tests and artifacts.
- Record limitations and deferred work.
- Do not declare completion without appropriate evidence.

## Current next recommended task

1. Audit the current drummer/band implementation against MASTER_TODO.md.
2. Identify implemented-but-unverified drummer behavior.
3. Generate the current XSQ + MP4 baseline.
4. Fix the highest-impact drummer gap as one isolated slice.
5. Update MASTER_TODO.md before beginning another slice.

## Recovery / evidence

Do not treat a task as fully closed until the applicable evidence exists:
- [ ] CI status
- [ ] targeted/full tests
- [ ] generated XSQ
- [ ] generated MP4 when visual behavior is involved
- [ ] xLights import evidence
- [ ] manual visual validation
- [ ] remaining known gaps

## Non-goals for near-term agents

- Do not perform a major rewrite of core/effect_engine.py without a documented migration plan.
- Do not train on user/tester sequences or layouts.
- Do not add marketplace/model scraping.
- Do not claim production-quality unattended show deployment.
- Do not broaden legacy-profile support until the beta path is stable.
