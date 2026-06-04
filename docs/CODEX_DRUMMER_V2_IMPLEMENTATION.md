# Codex Drummer V2 Implementation Checklist

## Purpose

Upgrade the snowman drummer from a mostly-functional reactive performer into a richer xLights-ready performer model that satisfies `docs/HELIXVILLE4_DRUMMER_TARGET.md`.

The current logic is strong: `models/working_drummer.py`, `animation/drummer_motion.py`, `mapping/drum_mapper.py`, and `effects/drum_effects.py` already support reactive kick/snare/hat/cymbal cues, stick motion, humanization, timing targets, and drum-specific visual effects.

The main missing piece is the physical xModel/submodel representation.

## Current implementation gap

`models/snowman_geometry.py` currently gives the drummer these primary drum regions:

- `kick`
- `snare`
- `tom`
- `cymbal`
- `hi_hat`
- `left_stick`
- `right_stick`

That is enough for logic smoke tests, but not enough for a vendor-quality animated drummer. The target doc requires a full readable kit with distinct zones, no placeholder ranges, and at least 16 real exported submodels.

## Required V2 submodels

Add or preserve the following submodels. Keep old aliases where needed so existing logic does not break.

### Snowman/body/costume

- `head`
- `face`
- `hat`
- `hat_band`
- `scarf`
- `torso`
- `buttons`
- `left_arm`
- `right_arm`
- `left_stick`
- `right_stick`

### Drum kit

- `kick`
- `kick_rim`
- `snare`
- `snare_rim`
- `tom_left`
- `tom_right`
- `tom` composite alias containing `tom_left` + `tom_right`
- `hi_hat`
- `cymbal_left`
- `cymbal_right`
- `cymbal` composite alias containing `cymbal_left` + `cymbal_right`
- `stands`
- `platform`
- `drumkit_all`

### Pose/action composites

These should be composite submodels or export metadata targets, not necessarily separate geometry:

- `pose_idle`
- `pose_kick`
- `pose_snare`
- `pose_hihat`
- `pose_tom_fill`
- `pose_crash_left`
- `pose_crash_right`
- `pose_both_up`
- `pose_downbeat_impact`

## Geometry changes

Implement this first in `models/snowman_geometry.py` inside the `role == "drummer"` block.

Recommended coordinates should remain proportional using `_scale(..., s)` so 32/48/64 canvases still work.

Suggested V2 layout:

- Kick centered low: `circle(cx, _scale(49, s), max(5, _scale(7, s)))`
- Kick rim: larger ring approximation around kick using a larger circle minus inner kick, or a thin ellipse/line perimeter if ring subtraction is inconvenient.
- Snare left-front: `ellipse(cx - _scale(11, s), _scale(39, s), ...)`
- Snare rim: slightly wider/flatter ellipse around snare.
- Tom left: near center-left/top of kick.
- Tom right: near center-right/top of kick.
- Hi-hat: far left, high enough to read separately from snare.
- Cymbal left: above/left of head-arm zone, not collapsed into hi-hat.
- Cymbal right: above/right of kit, current cymbal can become right crash.
- Stands: thin lines from cymbals/hi-hat/snare down to platform.
- Platform: wide rectangle or line at the base.
- Face: include eyes/nose region if simple geometry exists; otherwise use `mouth_area` + small eye/nose dots.
- Hat/hat_band/scarf/buttons: simple costume regions so the model reads as a snowman and not a stick figure.

## Submodel generation changes

Update `generate_submodels()` role-specific drummer list from:

```python
"drummer": ["kick", "snare", "tom", "cymbal", "hi_hat", "left_stick", "right_stick"]
```

to a richer list similar to:

```python
"drummer": [
    "face",
    "hat",
    "hat_band",
    "scarf",
    "buttons",
    "kick",
    "kick_rim",
    "snare",
    "snare_rim",
    "tom_left",
    "tom_right",
    "tom",
    "hi_hat",
    "cymbal_left",
    "cymbal_right",
    "cymbal",
    "stands",
    "platform",
    "left_stick",
    "right_stick",
]
```

Keep `tom` and `cymbal` as aliases/composites so current `drum_mapper.py` and `effects/drum_effects.py` continue to work.

Update `instrument_regions` / `drumkit_all` so `drumkit_all` excludes costume/body but includes:

- kick
- kick_rim
- snare
- snare_rim
- tom_left
- tom_right
- hi_hat
- cymbal_left
- cymbal_right
- stands
- platform

## Working drummer changes

Update `_required_drummer_submodels()` in `models/working_drummer.py` to require the V2 set.

Keep old required names only where they are compatibility aliases:

- `tom`
- `cymbal`
- `drumkit_all`

Add validation fields:

- `has_v2_drummer_submodels`
- `v2_missing_submodels`
- `drumkit_zone_count`
- `has_split_cymbals`
- `has_split_toms`
- `has_rims`
- `has_stage_platform`

## Mapping/effects changes

Leave the existing stable mapping alone for compatibility:

- kick → `kick`
- snare → `snare`
- tom → `tom`
- hihat → `hi_hat`
- cymbal → `cymbal`

Then add richer composite targets:

- tom hit should include `tom_left` and `tom_right` when doing fills.
- cymbal hit should choose `cymbal_left` or `cymbal_right` based on alternating hits or stereo/spatial info if available.
- snare should include `snare_rim` for sharper attack.
- kick should include `kick_rim` for impact ring.

Do not remove the old submodel names until all exporters and tests are updated.

## Tests to add

Create or update tests so CI fails if the drummer regresses.

Recommended tests:

1. `build_working_drummer()` has at least 22 submodels.
2. Required V2 names are present.
3. `tom_left` and `tom_right` exist and have nonzero node counts.
4. `cymbal_left` and `cymbal_right` exist and have nonzero node counts.
5. `kick_rim` and `snare_rim` exist and have nonzero node counts.
6. `stands` and `platform` exist and have nonzero node counts.
7. `drumkit_all` includes real drum geometry and is not collapsed to the same tiny range as placeholders.
8. Reactive cues from `build_reactive_drummer_member()` still target existing submodels.
9. Legacy aliases `tom` and `cymbal` remain valid.
10. The target doc rule is met: fewer than 16 drummer submodels should fail.

## Acceptance criteria

The implementation is accepted when:

- `build_working_drummer()` reports no missing required submodels.
- The drummer has split cymbal, split tom, rim, stand, platform, costume, stick, and body regions.
- Existing reactive logic still works without breaking old `tom` and `cymbal` targets.
- xLights export metadata still identifies this as `custom_model_with_submodels`.
- The result satisfies the visual direction in `docs/HELIXVILLE4_DRUMMER_TARGET.md`.

## How Ryan can help

Ryan should approve or sketch the canonical poses:

1. Idle/ready
2. Kick hit
3. Snare hit
4. Hi-hat tick
5. Tom fill
6. Left cymbal crash
7. Right cymbal crash
8. Both arms up
9. Downbeat impact

Best help: provide or approve a simple front-view reference with where the left/right cymbals, toms, snare, kick, and sticks should sit. The code can generate geometry, but the final performer quality depends on those pose choices.
