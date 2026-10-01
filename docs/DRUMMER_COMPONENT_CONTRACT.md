# Canonical Snowman Drummer Component Contract

## Purpose

This is the canonical sequencing contract for the Helix snowman drummer. It supersedes the old assumption that left/right arms or left/right sticks are independent lighting channels.

## Nine sequenced components

The drummer uses exactly nine sequenced components:

1. `HX_SNOWMAN_DRUMMER_KICK`
2. `HX_SNOWMAN_DRUMMER_SNARE`
3. `HX_SNOWMAN_DRUMMER_HI_HAT`
4. `HX_SNOWMAN_DRUMMER_TOM_1`
5. `HX_SNOWMAN_DRUMMER_TOM_2`
6. `HX_SNOWMAN_DRUMMER_TOM_3`
7. `HX_SNOWMAN_DRUMMER_TOM_4`
8. `HX_SNOWMAN_DRUMMER_CYMBAL_LEFT`
9. `HX_SNOWMAN_DRUMMER_CYMBAL_RIGHT`

## Non-negotiable behavior

- There are **no separate stick channels**.
- There are **no separate left-stick or right-stick sequencing targets**.
- A snare hit lights the snare and its contacting stick geometry as one component/event, using one color and one timing event.
- A tom hit lights that tom and the contacting stick geometry as one component/event.
- A hi-hat hit lights the hi-hat and its contacting stick geometry as one component/event.
- A cymbal hit lights the selected cymbal and its contacting stick geometry as one component/event.
- A kick hit lights only the kick component. It has no stick target.
- Left and right cymbals are separate components and alternate during ordinary fills/crashes unless the musical event explicitly represents a simultaneous crash.
- Multiple components may be active at the same timestamp; mapping must never collapse simultaneous kick/snare/cymbal/tom events into one replacement event.
- The four tom components are distinct targets. Generic tom detections are distributed across the four toms deterministically until richer tom classification is available.

## Visual versus sequenced submodels

The snowman may still contain visual/geometry submodels for arms, sticks, stands, rims, etc. Those are implementation geometry, not independent sequencing channels. Sequencing targets must resolve to the nine components above.

## Acceptance criteria

A drummer mapping is correct only if:

- the emitted sequenced component IDs are a subset of the nine canonical IDs;
- no emitted target contains `LEFT_STICK`, `RIGHT_STICK`, `LEFT_ARM`, or `RIGHT_ARM` as a sequencing component;
- kick events target only kick;
- snare, hi-hat, tom, and cymbal events target the appropriate combined component;
- cymbal alternation is deterministic;
- simultaneous events remain simultaneous;
- a full-song real-audio render is used for final visual validation.

This contract is intentionally narrower than the visual asset specification. Geometry may be richer than the sequencing interface.
