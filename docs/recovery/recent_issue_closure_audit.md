# Recent Issue Closure Audit

This recovery audit separates merged deterministic code slices from acceptance criteria that still require CI, generated artifacts, xLights import evidence, visual review, or controller/runtime proof. Closed issues should be treated as implemented or partially implemented only where evidence supports that status.

## Audit rules

- PR #75 merged a guarded, default-off Issue #2 Birdsong adapter slice. Runtime wiring, fixture integration, phrase persistence, spatial/adjoining target logic, and scoring/report fields remain follow-up work.
- PR #74 added the high-quality preview wrapper and preset validation path, but runtime MP4 rendering was not executed and it does not prove true xLights/OpenGL preview parity.
- PR #73 and PR #66 were still open and unmerged when this recovery gate was written.
- Issue #72 documents the gap between targeted beta CI and the broader full-suite pytest job.
- Manual claims require artifacts. xLights import, render, channel safety, controller safety, and visual review stay unproven until evidence is stored.

## Recovery checklist

- [ ] Record current CI status for the recovery PR.
- [ ] Record targeted and full pytest status separately.
- [ ] Store representative generated XSQ artifacts where review can inspect them.
- [ ] Store representative MP4 artifacts when rendering is actually executed.
- [ ] Capture xLights import evidence for validation-heavy issues.
- [ ] Capture manual visual review evidence where acceptance requires it.
- [ ] Capture controller/channel safety evidence before production claims.
- [ ] Keep roadmap/umbrella issues open or explicitly supersede them instead of marking them complete by implication.
- [ ] Keep the remaining Issue #2 runtime integration work tracked in bounded follow-ups.

## Issue status audit

| Issue | Evidence-supported status | Still not proven |
| --- | --- | --- |
| #2 Birdsong Engine | Feature state plus guarded/default-off adapter slice. | Runtime hook, fixture integration, phrase persistence, spatial targeting, scoring/reporting. |
| #20 Helixia validation | Tracker documents known parser/local facts. | xLights import, channel/controller safety, visual review. |
| #23 Showcase parity | Roadmap/umbrella only. | Benchmark improvement, reports, renderer stability. |
| #24 Showcase bias caps | Bounded deterministic scoring slice may be implemented. | Current broad CI evidence. |
| #28 Quality escalation | Roadmap/umbrella only. | Phased quality metrics and runtime proof. |
| #29 GUI state audit | Investigation request. | Screenshot walkthrough, parity matrix, friction notes, recommendation. |
| #35 Lyric phoneme timing | Bounded v1 mapping/allocation appears implemented. | Real audio alignment beyond stated v1. |
| #37 Multi-line lyric scheduling | Bounded deterministic scheduler appears implemented. | Real song-section artifact validation. |
| #39 Section energy scaling | Bounded deterministic scaler appears implemented. | Downstream visual impact proof. |
| #41 / #42 Beat-grid alignment | Appears duplicate; count one implementation. | Maintainer-selected canonical issue and export proof. |
| #44 XSQ emitter | Deterministic emitter slice. | xLights import/render acceptance. |
| #46 Real xLights import workflow | Validator/docs exist. | Manual xLights import and render timing. |
| #48 XSQ validation fixtures | Automated fixture coverage. | Manual xLights proof, intentionally separate. |
| #50 Generated XSQ export command | Export command/tests exist. | Generated artifact attached to review and import outcome. |
| #52 Band geometry gate | Manifest/status validation metadata. | Physical geometry parity and real xLights assets. |
| #54 Band geometry seed | Bounded metadata slice. | Physical render/controller proof. |
| #56 Draft band xmodel generation | Draft asset slice only. | xLights acceptance, preview, controller output. |
| #60 Legacy runtime consolidation | Cleanup plan/inventory requirement. | Runtime parity and canonical path proof. |
| #61 Promote band xmodels | Import evidence must be verified. | All assets, preview animation, controller validation. |
| #72 Full-suite CI triage | Real triage remains open. | Restored full-suite CI or documented expected failures. |

## Validation flags

Roadmap or umbrella closures needing an explicit supersession decision: #2, #23, #28, and #60.

Validation-heavy closures needing xLights/manual/visual/controller/artifact evidence before complete claims: #20, #29, #44, #46, #50, #52, #56, #61, and #72.

Duplicate hygiene: #41 and #42 describe the same deterministic beat-grid alignment work. Count one implementation and record the canonical issue before marking the duplicate complete.

## Preview truthfulness

`tools/preview_hq.py --validate-quality-presets` proves preset definitions import and print; it does not render an MP4. It also does not prove xLights/OpenGL preview parity, layout correctness, node binding, or controller safety.

Real preview evidence should be generated from repo-safe copied inputs and stored outside private source input folders, then referenced from the review record:

- XSQ artifacts: CI upload or `artifacts/recovery/xsq/`.
- MP4 artifacts: CI upload or `artifacts/recovery/mp4/`.
- Manual xLights notes/screenshots/import metadata: CI upload, `artifacts/recovery/xlights/`, or a documented external evidence link when binaries should not enter git.

Do not claim rendering is fixed from preset validation alone.
