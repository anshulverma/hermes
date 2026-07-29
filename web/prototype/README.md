# Hermes control plane — design prototype

Imported from Claude Design project **"Hermes control plane UI brief"**
(`claude.ai/design/p/1af79cea-b4a0-43e9-8183-4d323a4e37ea`), built from
[`web/UI_BRIEF.md`](../UI_BRIEF.md).

**This is a design reference, not production code.** Everything here is a
browser-only React + Babel prototype of look and behavior — hand-loaded via
`<script type="text/babel">`, no build step, mock data in `app/data.js`. The
production target is a React + Vite + TypeScript SPA under `web/` over the
engine's JSON API. Recreate these screens there using the repo's own patterns;
**do not ship this HTML**.

## Run it

Static files with CDN dependencies (React 18, Babel standalone, Lucide) — serve
over HTTP (opening `file://` will not run the Babel scripts):

```sh
cd web/prototype
python3 -m http.server 8000
# open http://localhost:8000/Hermes%20Control%20Plane.html
```

Requires network access for the unpkg CDN scripts and the Inter webfont.

## Layout

| Path | Contents |
| --- | --- |
| `Hermes Control Plane.html` | Entry point — token stylesheets, DS bundle, script order |
| `app/HermesApp.jsx` | Routing, drawers, stop-run dialog, playbook dialog |
| `app/Shell.jsx` | TopBar, RunContext, SectionHead, LiveDot |
| `app/RunOverview.jsx` | Banners, KPIs, progress, phase timeline, crew strip |
| `app/MetricsView.jsx` | KPI tiles, chart primitives, hover model, phase table |
| `app/ResourcesSection.jsx` | cpu/gpu/mem timelines, host filter, per-host meters |
| `app/AgentUsageSection.jsx` | Token throughput, spend, spend split |
| `app/TicketBoard.jsx` | Lanes + list, filters |
| `app/CrewPanel.jsx` | Crew rows, health, errors, add-host modal |
| `app/Findings.jsx`, `app/ActivityFeed.jsx`, `app/TicketDrawer.jsx` | Findings, events + leases, drawers |
| `app/data.js` | Mock records |
| `_ds/mono-dark-dash-design-system-…/` | Bound design system: `_ds_bundle.js` (components), `styles.css`, `tokens/*.css` |

The design-system components (`StatTile`, `StatusPill`, `Card`, `Table`,
`Dialog`, `Drawer`, `CrewRow`, `HealthBadge`, `EventRow`, `AttentionBanner`,
`TicketCard`, `KanbanColumn`, …) live in `_ds_bundle.js` and are exposed on
`window.DSNS`. Keep these component names in the SPA.

## Design system (token table is the source of truth)

Dark-only, near-monochrome operator UI. **Structure is expressed in white alpha;
hue is reserved for machine state.**

- **Surfaces:** page `rgb(0,0,0)`, card `rgb(22,22,22)`, floating chrome
  `oklab(0 0 0 / 0.85)` + `backdrop-filter: blur(12px)`. **No shadows anywhere.**
- **Text:** primary `#fff`, secondary `rgba(255,255,255,.7)`, muted
  `rgba(255,255,255,.5)`. No fourth level.
- **Borders:** hairline `rgba(255,255,255,.1)`; controls `rgba(255,255,255,.5)`
  resting → `#fff` hover. Washes: hover `.06`, active `.1`, selected `.08`.
- **Status ramp (the only color):** live `oklch(0.74 0.11 230)`, ok
  `oklch(0.74 0.11 150)`, attention `oklch(0.80 0.11 85)`, danger
  `oklch(0.68 0.15 25)`; each with a `-tint` (14%) for pill grounds and an
  `-edge` (38%) for borders.
- **Type:** `Inter, ui-sans-serif, system-ui, …`; body 14/20, metadata 12/16,
  h3 20/26, h1 48/48 at weight 400. Mono (`ui-monospace, SFMono-Regular, Menlo,
  Consolas`) for ids, counts, timestamps, code. Tracking never adjusted.
- **Radii:** 0.75rem controls, 1rem cards, 1.25rem dialogs, `9999px` for
  dots/track fills only.
- **Motion:** 120ms color/border, 160ms washes/overlays, `ease-out`. Fades and
  ≤2px moves only — no scale, spring, or slide.
- **Accessibility:** color is never the only signal. Every status carries hue
  **+ marker shape** (hollow dot queued, half in-transition, dashed parked,
  pulsing solid live, ✓ / × / ! terminal) **+ the literal state word**.

## Screens

Run overview · Metrics (playbook burn/progress/error rate, system resources,
agent usage) · Tickets (four lifecycle lanes + dense list) · Crew (rows, health
probes, add-host probe checklist) · Findings (deduped root causes) · Activity
(streaming events + leases) · ticket & host drawers · playbook dialog.

## Note on the page backdrop

`CrewBackdrop` (theme `graph`) references
`_ds/…/assets/backdrops/graph.png` as a low-alpha (~0.09) CSS background. Only
`graph.png` (the theme the app uses) ships under `_ds/…/assets/backdrops/`; the
DS defines seven other themes (`construction`, `robots`, `farm`, `depot`,
`pipeline`, `tree`, `neural`) whose textures are not included. A missing file
renders no background (it's a CSS `background-image`, so no broken-image icon).
