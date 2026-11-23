# SALTBOR Phase 1.16B — Studio Design System Specification

## 1. Visual Continuity & Token Inheritance

The Phase 1.16B Conversational Studio styles ([studio.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/studio.css)) strictly inherit CSS custom properties defined in [style.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/style.css) so Light Mode (`[data-theme="light"]`) and Dark Mode (`:root`) operate cohesively across the entire application with zero hardcoded theme conflicts.

| Token Category | CSS Variables (`style.css`) | Studio Usage |
| :--- | :--- | :--- |
| **Surfaces** | `--bg-base`, `--bg-surface`, `--bg-elevated`, `--bg-highlight` | Chat canvas, history drawer, welcome card, assistant cards, settings modal, optional map drawer |
| **Typography & Text** | `--font-sans`, `--font-mono`, `--text-primary`, `--text-secondary`, `--text-muted`, `--text-inverse` | Spanish conversational prose, KPI values, SQLite/seed provenance IDs, code/badges |
| **Borders & Focus** | `--border-subtle`, `--border-strong`, `--border-accent` | Composer focus ring, card separation, active history item border |
| **Semantic Accents** | `--accent-sky`, `--accent-emerald`, `--accent-amber`, `--accent-rose`, `--accent-purple` | Provenance badges, verdict pills, provider state pills, cancellation & warning emphasis |
| **Elevation & Radii** | `--radius-sm` (`4px`), `--radius-md` (`6px`), `--radius-lg` (`8px`), `--shadow-sm`, `--shadow-lg` | Prompt chips, autocomplete dropdown, KPI boxes, modal dialog |

---

## 2. Epistemic Color & Badge Encoding (Truth vs. Simulation vs. Opinion)

SALTBOR strictly prevents users from confusing verified geography with simulated outcomes or LLM commentary:

| Class | Meaning | Color Token | Where Used |
| :--- | :--- | :--- | :--- |
| `.studio-badge.real` | Verified national/OSM territorial context, accounting conservation OK, or `PROMISING` verdict | `--accent-emerald` | Stage A location pill, ledger conservation badge, verdict pill |
| `.studio-badge.synthetic` | Synthetic agent simulation outputs (`SYNTHETIC_SIMULATED`) | `--accent-purple` | Evidence card header, simulated indicator provenance |
| `.studio-badge.warn` | `CONDITIONALLY_PROMISING`, `INSUFFICIENT_EVIDENCE`, or missing/unavailable fields | `--accent-amber` | Verdict pill, data-gap disclosure |
| `.studio-badge.risk` | `HIGH_RISK` or `NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS` verdict | `--accent-rose` | Risk alerts, cancel CTA, error card border |
| `.studio-badge.info` | Preliminary Stage A assessment or configuration proposal | `--accent-sky` | Stage A summary header |

---

## 3. Provider Status Pill Encoding

Header `#studio-provider-pill` maps backend `status_code` dynamically via `data-status`:

- `CONNECTED` / `LOCAL_PROVIDER_ACTIVE` $\rightarrow$ `--accent-emerald` border & text
- `QUOTA_EXCEEDED` / `RATE_LIMITED` $\rightarrow$ `--accent-amber` border & text
- `OFFLINE_MODE` $\rightarrow$ `--accent-sky` border & text
- `NOT_CONFIGURED` / `UNAVAILABLE` $\rightarrow$ `--border-strong` & `--text-secondary`

---

## 4. Layout Geometry, Map Modes & Reuse Rules

`#studio-shell` implements a flexible 3-region workspace inside `#view-studio`:

1. **Left History Drawer (`aside#studio-history-drawer`)**: `260px` width; collapsible via `.studio-shell.history-collapsed`.
2. **Center Conversation Pane (`.studio-chat-pane`)**: `flex: 1` centered column (`max-width: 840px` for `.studio-thread` and `.studio-composer-box`) preserving comfortable reading measure (~60–75ch) and selectable message text (`user-select: text` overriding `body { user-select: none }`).
3. **Right Optional Map Drawer (`aside.studio-map-drawer`)**:
   - `.studio-shell.map-hidden` (default): `width: 0` — chat occupies full workspace without initializing WebGL.
   - `.studio-shell.map-side`: `width: 42%` (`min-width: 340px`).
   - `.studio-shell.map-expanded`: `width: 60%` (`min-width: 420px`).
   - `full` mode: restores single `#maplibre-viewport` to `#view-world` and switches active view to `world` with `#btn-return-to-studio` visible.

---

## 5. Accessibility & Responsive Breakpoints

- **Keyboard Focus**: `.studio-shell :focus-visible` renders a `2px solid var(--accent-sky)` outline; `Enter` submits in `#studio-chat-input` (`Shift+Enter` inserts newline); global `'H'` hotkey in [app.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/app.js) explicitly ignores `INPUT`, `SELECT`, and `TEXTAREA`.
- **Tablet (`@media (max-width: 1024px)`)**: `#studio-history-drawer` switches to overlay drawer (`position: absolute; z-index: 20`), side map uses `48%` (`min-width: 280px`).
- **Mobile (`@media (max-width: 768px)`)**:
  - Topbar reveals `#btn-mobile-nav` (`.mobile-only-btn`) to slide `#sidebar.mobile-open` into view.
  - Non-essential desktop telemetry widgets hide so chat header and composer stay uncluttered.
  - Side/expanded map stacks vertically below chat (`flex-direction: column`, drawer height `46vh`).
  - Interactive buttons apply `.studio-btn-touch` (`min-height: 40px`) for reliable touch ergonomics.
