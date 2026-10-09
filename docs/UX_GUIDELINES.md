# CreatorIQX UX Guidelines

> **Status: stub.** Tokens and principles arrive with P0-080 and P0-090 (wireframes). Screens are designed and approved before they are built.

## Purpose

Design principles, design tokens (color, spacing on an 8 px grid, type scale, motion), accessibility rules (WCAG 2.2 AA), copy style, empty, loading and error states, and the rule that CreatorIQX should feel like a polished creator operating system, not a generic admin dashboard (spec §11, docs/AGENT_KICKOFF.md).

## Visual direction (owner-supplied, 2026-10-10)

The owner supplied a high-fidelity reference mockup, saved at
`docs/design/visual-direction-v1.png`, covering: Dashboard, Planner
(kanban), Video Workspace (Script/SEO/Thumbnail/Chapters/QA/Publish tabs),
Analytics, Comments, Publish & Sync, Research & Inspiration, Channel Audit,
and Settings/YouTube Sync. This is the visual-style target for the product
("you can use this as a design for the site") — dark theme, indigo/purple
brand accent with a gradient on primary CTAs, card-based layout on an 8px
grid, data visualized with sparklines/progress rings/kanban columns rather
than bare tables.

**How this applies, concretely:**

- It **sets the look-and-feel**, not the screen-by-screen content or
  structure — those still come from each screen's own approved wireframe
  (P0-090 for login/shell/dashboard) and acceptance criteria (spec §4).
  Spec §11's rule stands: a low-fidelity wireframe is produced and approved
  before a *new* screen's structure is built; this mockup supplies the
  *styling* layer on top of that, not a replacement for it.
- It already lines up with the dark-mode tokens built in P0-080
  (`apps/web/src/app/globals.css`): `--brand: #818cf8` (indigo) in dark
  mode is close to this mockup's accent purple. Applying it is expected to
  mean extending the existing token set (e.g. a brand gradient token for
  primary CTAs, a positive-trend accent) rather than replacing it.
- It shows screens across every feature tier (Core: Dashboard, Planner,
  Video Workspace tabs, Settings, YouTube Sync; Should: Comments, Research
  & Inspiration). Spec §4's tier order still governs *when* each screen
  gets built — Should-tier screens shown here (Comments, Research) are
  styled for later, not built ahead of their tier.
- First applied to P0-091 (login screen) and P0-092 (app shell and empty
  dashboard), the next UI tickets after P0-090's wireframes; extended to
  each further screen as its owning feature reaches Core/Should tier.
