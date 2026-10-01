# HELIX MASTER TODO & AGENT HANDOFF LEDGER

> Canonical project roadmap. Every agent must read and update this file when changing Helix.

## Current mission
Build Helix into a reliable AI-assisted xLights auto-sequencer while preserving deterministic sequencing, verified artifacts, and cumulative behavior.

**Current priority:** finish drummer/band logic and prove it with real-song XSQ + MP4 artifacts.

## Drummer / band current state
- [x] Canonical nine-component drummer contract documented.
- [x] Runtime drummer state model changed to nine integrated hit components.
- [x] Structure catalog changed to nine drummer sequencing components.
- [x] XML exporter no longer emits the legacy `line0="1-4"` placeholder for drummer components.
- [x] Pose geometry spec now defines nine component composites with embedded contacting-stick geometry.
- [~] xLights model exporter still needs to be taught to emit the new component composites as the nine canonical sequencing submodels.
- [ ] Generate real-song XSQ.
- [ ] Render full-song MP4 with audio.
- [ ] Human visual review of rendered drummer timing.

## Canonical drummer components
1. `HX_SNOWMAN_DRUMMER_KICK` = KICK + KICK_RIM
2. `HX_SNOWMAN_DRUMMER_SNARE` = SNARE + SNARE_RIM + SNARE_CONTACT_STICK
3. `HX_SNOWMAN_DRUMMER_TOM_1` = TOM_1 + TOM_1_CONTACT_STICK
4. `HX_SNOWMAN_DRUMMER_TOM_2` = TOM_2 + TOM_2_CONTACT_STICK
5. `HX_SNOWMAN_DRUMMER_TOM_3` = TOM_3 + TOM_3_CONTACT_STICK
6. `HX_SNOWMAN_DRUMMER_TOM_4` = TOM_4 + TOM_4_CONTACT_STICK
7. `HX_SNOWMAN_DRUMMER_HI_HAT` = HI_HAT + HIHAT_CONTACT_STICK
8. `HX_SNOWMAN_DRUMMER_CYMBAL_LEFT` = CYMBAL_LEFT + CYMBAL_LEFT_CONTACT_STICK
9. `HX_SNOWMAN_DRUMMER_CYMBAL_RIGHT` = CYMBAL_RIGHT + CYMBAL_RIGHT_CONTACT_STICK

**Physical rule:** the contacting stick is part of the corresponding hit component. There are no independent stick sequencing channels. Kick has no stick.

## Verification gate
**audio → detected events → mapped components → XSQ → full-song MP4 with real audio → visual review**

Do not mark complete from unit tests alone.

## Change Ledger

### 2026-09-30 — Nine-component drummer geometry spec
**Agent:** ChatGPT/GitHub
**Branch:** `feature/restructure-core`
**Commit:** `a6ee1e22c66fd1d9e4020b1c92538102262b23e7`

**Changed:**
- `fixtures/band_geometry/drummer_v3_pose_spec.json` — replaced the obsolete two-tom/independent-stick component structure with four distinct tom zones and nine canonical hit composites.
- Each snare/tom/hi-hat/cymbal composite contains its contacting-stick geometry.
- Kick remains its own component without a stick.

**Preserved intentionally:**
- Snowman body/head/hat/scarf/torso/platform geometry.
- Left/right cymbal distinction.
- Real custom-model grid geometry and asset-first xmodel generation path.

**Known limitation:** the xmodel builder currently exports every authored zone and composite, so the generated xmodel still contains more than the nine sequencing submodels. The next slice must make the nine composites the canonical sequencing targets while retaining physical/support geometry as non-sequenced submodels where appropriate.

**Next actions:**
1. Update xmodel/export integration so the nine `DRUMMER_*` composites are the sequenced components.
2. Add validation that each canonical component has non-empty, non-overlapping required geometry except intentional physical overlaps at contact points.
3. Generate the repository's real-song XSQ.
4. Render the complete song to MP4 with audio.
5. Inspect the result frame-by-frame against the XSQ and audible drum events.
