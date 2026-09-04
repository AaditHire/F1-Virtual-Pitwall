# Dashboard Design Specification

Reference: `pitwall-dashboard-concept.png` (1536 × 1024).

## Visual system

- Background: `#0b0f12`; panels: `#11171b`; raised rows: `#1b2227`.
- Primary text: `#f4f6f7`; muted text: `#96a0a7`; border: `#2a3237`.
- Interaction accent: `#ef3e42`; data accent: `#35bdd0`; caution: `#f2c94c`.
- Geometry: square/4px controls, 1px separators, no gradients or decorative glows.
- Typography: Geist Sans for UI and Geist Mono for timing; compact tabular numerals.

## Layout and components

The desktop shell uses a 208px sidebar, a 52px top bar, a lap timeline, then a two-column
workspace. The left column is a dense position table and lap chart; the 480px right rail is
the strategy advisor and comparison. Mobile collapses navigation into a top strip and
stacks analysis below the timeline and table.

Component families are navigation rows, square icon buttons, select controls, timeline
markers, table rows, evidence rows, metric pairs, line charts, and comparison columns.
Controls use consistent thin outline icons. Selected state is indicated by a red edge and
dark-red surface, never by glow.

## Allowed first-viewport copy

`F1 Virtual Pit Wall`, `Race Replay`, `Strategy`, `Tyres`, `Traffic`, `Radio`,
`Evaluations`, `2024 Bahrain GP`, `Lando Norris`, `Lap {n} / 57`, `Strategy Advisor`,
`Recommendation`, `Confidence`, `Evidence`, `Predicted rejoin`, `Traffic risk`,
`Lap Time Trend`, `Strategy Comparison`, `PIT NEXT LAP`, and `STAY OUT ONE LAP`.

## Interaction contract

Previous, next, play/pause, and lap selection must update real dashboard state. Selecting a
driver updates the strategy target. Backend failures show an explicit operational error;
they do not silently replace real data with fabricated values.

