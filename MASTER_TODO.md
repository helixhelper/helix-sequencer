# HELIX MASTER TODO & AGENT HANDOFF LEDGER

> **Canonical project roadmap.** Every human, Codex, GitHub, or other coding agent MUST read this file before changing Helix. Every agent that changes code, configuration, tests, workflows, documentation, sequencing logic, mappings, GUI behavior, rendering, or generated-artifact logic MUST update this file in the same change set.

## Operating rule

The master ledger exists to prevent logic from being silently lost between agents.

An agent MUST NOT:
- assume an undocumented subsystem is disposable;
- replace working logic without recording what it did;
- mark a feature complete merely because tests pass;
- claim a behavior is implemented without evidence;
- remove or supersede an existing implementation without documenting the replacement and migration path.

When an agent discovers undocumented behavior, preserve it first, then document it here.

## 1. Current mission

Build Helix into a reliable AI-assisted xLights auto-sequencer that can accept audio and xLights layout/template inputs, analyze musical structure, map musical roles onto real display props/channels, generate an importable xLights sequence, produce useful previews, provide an accessible GUI, preserve deterministic rule-based behavior beneath AI-assisted features, and eventually provide enough quality and automation to justify a commercial product.

**Current priority:** stabilize and finish the drummer/band logic, preserve all existing sequencing logic, establish artifact-based verification, and eliminate agent-to-agent loss of intent.

## 2. Status legend

- [ ] Not started
- [~] In progress / partially implemented
- [x] Implemented and verified
- [?] Implemented but insufficiently verified
- [!] Known regression/blocker
- [-] Intentionally deferred
- [ARCHIVED] Superseded but retained for reference

A checkbox may only become [x] when the ledger records evidence.

## 3. Non-negotiable agent workflow

Before changing anything:
- [ ] Read MASTER_TODO.md.
- [ ] Read AGENTS.md.
- [ ] Inspect the relevant current implementation rather than relying on an old handoff.
- [ ] Identify existing behavior that must be preserved.
- [ ] State the smallest useful implementation slice.
- [ ] Work on a feature branch.

After changing anything:
- [ ] Update this file in the same PR/commit series.
- [ ] Record files/modules changed.
- [ ] Record behavior added/changed.
- [ ] Record behavior intentionally preserved.
- [ ] Record tests/CI/manual evidence.
- [ ] Record unresolved issues and deferred work.
- [ ] Record assumptions made.
- [ ] Record logic that could not be verified.
- [ ] If a previous task was superseded, explicitly say why.
- [ ] Never silently delete a roadmap item.

**If an agent cannot update this ledger, it must not claim the implementation is complete.**

## 4. Current architecture / areas that must not be lost

### Sequencing core
- [~] Core sequencing pipeline / engine profiles
- [~] Effect generation and effect-engine behavior
- [~] AC-safe effects: On / Ramp / Shimmer / Level
- [~] Timing generation and audio-derived timing tracks
- [~] xLights XSQ generation/import compatibility

### Audio intelligence
- [~] Beat/bar/onset detection
- [~] Spectral/audio feature extraction
- [~] Bass / melody / high-frequency role detection
- [~] Pitch/melodic analysis
- [ ] More robust musical-role separation
- [ ] Evaluate/improve advanced audio analysis without destabilizing baseline
- [ ] Preserve deterministic fallback behavior when advanced analysis fails

### Display mapping
- [~] xLights layout parsing
- [~] Group/channel mapping
- [~] 256-channel AC-oriented display support
- [~] Candy cane mappings
- [~] Arch mappings
- [~] Snowflake/star mappings
- [~] Mega-tree mappings
- [ ] Comprehensive mapping validation
- [ ] No-output/duplicate-output diagnostics
- [ ] Better automatic semantic prop discovery

### Drummer / band
- [~] Drummer subsystem exists
- [~] Drummer test/preview infrastructure exists
- [?] Kick/bass synchronization
- [?] Snare hit behavior
- [?] Hi-hat behavior
- [?] Cymbal behavior
- [?] Stick/light motion behavior
- [?] 8-channel drummer mapping
- [?] Visual choreography quality
- [ ] Full musical drummer phrase logic
- [ ] Band-member coordination
- [ ] Guitar/string note response
- [ ] Singing-face/phoneme integration
- [ ] Validate against actual rendered MP4, not only unit tests

### Rendering / artifacts
- [~] Preview/render infrastructure
- [?] HTML/visualizer artifacts
- [?] MP4 generation
- [ ] Consistent MP4 + audio artifact generation
- [ ] Artifact links in CI
- [ ] Automated artifact sanity checks
- [ ] Human visual review gate

### GUI
- [~] GUI exists
- [~] Launcher exists
- [ ] Stable beta workflow
- [ ] Audio/layout/template/output selectors
- [ ] Dry validation
- [ ] Friendly errors
- [ ] Run manifest
- [ ] Progress/log display
- [ ] Donation/instructions/help surfaces where appropriate
- [ ] Package/desktop launch validation

## 5. Beta / reliability roadmap

### Repository safety
- [ ] Single documented supported branch/release baseline
- [ ] No-overwrite guarantees
- [ ] Run manifests
- [ ] Reproducible environment
- [ ] Clean-room sample inputs
- [ ] Clear input/output boundaries

### CI
- [ ] Compile gate
- [ ] Unit tests
- [ ] Integration tests
- [ ] Deterministic smoke sequence
- [ ] XSQ artifact generation
- [ ] MP4 preview artifact
- [ ] Artifact sanity validation
- [ ] Regression detection

### xLights compatibility
- [ ] Generated XSQ opens successfully in xLights
- [ ] Channel counts remain correct
- [ ] Timing remains aligned with media
- [ ] No unintended persistent lights
- [ ] No accidental channel collisions
- [ ] AC-safe output validation

## 6. Quality gates

A feature is not complete merely because code exists.

For sequencing features, prefer:
**code → unit test → integration test → XSQ → xLights import → rendered preview → human review**

For drummer/band features:
**audio → detected events → mapped channels → XSQ → MP4 with audio → visual review**

A failed or missing artifact must remain visible in this ledger.

## 7. Known problem: agent communication loss

Multiple agents have historically worked from separate handoff reports, chat context, branches, and partial assumptions. This can cause duplicated implementations, abandoned logic, hidden regressions, reintroduced bugs, tests passing while visual behavior deteriorates, and features being declared complete without rendered evidence.

**Countermeasure:** this file is the persistent handoff layer. Every agent must append/update the Change Ledger below.

## 8. Change Ledger

Newest entries go first.

### 2026-09-27 — Master ledger established
**Agent:** ChatGPT/GitHub MCP  
**Change:** Established MASTER_TODO.md as the canonical cross-agent roadmap and handoff ledger.  
**Preserved:** Existing ROADMAP_BETA_TODO.md, TASKS.md, and AGENTS.md; no existing sequencing logic removed.  
**Purpose:** Prevent undocumented logic loss between agents.  
**Verification:** Repository inspection confirmed existing roadmap/task documents and active feature/restructure-core baseline.  
**Next:** Enforce this protocol in AGENTS.md and TASKS.md.

### 2026-09-29 — Current-state artifact render requested
**Agent:** ChatGPT/GitHub MCP  
**Branch/PR:** feature/restructure-core  
**Goal:** Generate fresh current-state drummer and regular XSQ/MP4 artifacts from the present branch baseline.  

**Changed:**
- MASTER_TODO.md — recorded the artifact-validation run request so the push-triggered render workflows are traceable.

**Preserved intentionally:**
- No sequencing, mapping, drummer, layout, or renderer implementation was changed.
- Existing feature/restructure-core code is the render subject.

**New behavior:**
- Trigger the branch's existing drummer and full-band render workflows from this documented baseline.

**Tests/evidence:**
- Fresh CI artifacts pending.
- Historical full-Lights-Out drummer run was not reused because it failed before rendering on an older branch state.

**Known limitations:**
- xLights import/manual visual review remains separate from automated CI rendering.

### 2026-09-29 — Drummer render failure diagnosed and corrected
**Agent:** ChatGPT/GitHub MCP  
**Branch/PR:** feature/restructure-core / PR #22  
**Goal:** Correct the failed drummer/full-render validation reported after the current-state artifact run.

**Changed:**
- audio/drum_classification.py — added harmonic/percussive separation and spectral-flatness/percussive-ratio gates so harmonic guitar attacks are not freely classified as cymbals/hats.
- audio/drum_detection.py — records harmonic-vs-percussive and spectral-flatness features.
- mapping/drum_mapper.py — maps drummer events to the real HX_SNOWMAN_DRUMMER performer and its actual drum/stick submodels.
- tools/integrate_drummer_v3_into_xsq.py — injects effects into real drummer submodels rather than synthetic 257–264 elements.
- tools/render_drummer_v3_preview.py — renders explicit kick/snare/hi-hat/tom/cymbal/stick targets.
- .github/workflows/helix-full-current.yml — builds a render layout containing the real drummer geometry.
- tests/test_drummer_v3_xsq_integration.py — updated mapping expectations.

**Preserved intentionally:**
- 256-channel AC sequencing remains intact.
- The drummer remains virtual/performer-based rather than consuming the 256 AC channels.
- Existing sequence generation and audio input remain unchanged apart from the drummer detection path.

**Tests/evidence:**
- Previous run exposed 840 detected cymbals versus 37 snares and 9 toms and had no real drummer geometry in the full-render layout.
- Corrective code is now committed; fresh render artifact is the required next validation.

**Known limitations:**
- Corrected MP4 has not yet received visual review.

## 9. Agent change-entry template

### YYYY-MM-DD — Short change name
**Agent:** <agent/tool/name>  
**Branch/PR:** <branch or PR>  
**Goal:** <what this change was intended to accomplish>

**Changed:**
- <file/module> — <what changed>

**Preserved intentionally:**
- <existing behavior that must remain>

**New behavior:**
- <new behavior>

**Tests/evidence:**
- <test command/result>
- <CI run>
- <artifact path/link>
- <manual review>

**Known limitations:**
- <what remains uncertain>

**Deferred work:**
- <what the next agent must not forget>

**Risks/regressions to watch:**
- <specific risks>

## 10. Current next actions

1. [ ] Enforce master-ledger requirement in AGENTS.md.
2. [ ] Make TASKS.md point to MASTER_TODO.md as the first source of truth.
3. [ ] Audit current drummer/band implementation against this ledger.
4. [ ] Identify every drummer behavior that exists in code but lacks verification.
5. [ ] Generate a real XSQ + MP4 validation artifact for the current drummer baseline.
6. [ ] Fix the highest-impact drummer quality gaps one slice at a time.
7. [ ] After each slice, update this ledger before starting the next slice.
8. [ ] Reconcile ROADMAP_BETA_TODO.md with this master ledger rather than allowing two competing roadmaps.
9. [ ] Establish a formal release/baseline tag once the current drummer/band baseline is proven.

## 11. Important principle

**Do not optimize for the appearance of progress. Optimize for retained behavior, verified artifacts, and cumulative capability.**

If an agent says "done," the next agent should be able to determine what changed, why, what existed before, what exists now, what was tested, what was not tested, and what remains.
