# WDM Visual Component Library — Style Guide

## 1. Overview

The WDM component library provides shared UI primitives for WDM visualization views: wavelength editors, channel planners, and service path traces. It is **not** a full design system — it covers the specific patterns that appear across WDM canvases and panels.

**Files:**
- CSS: `netbox_wdm/static/netbox_wdm/css/wdm-components.css` (when created)
- TypeScript: `netbox_wdm/static/netbox_wdm/src/`
- Built output: `netbox_wdm/static/netbox_wdm/dist/` (via `npm run build`)

---

## 2. Getting Started

Add the `wdm-component` class to any wrapper element. This activates all CSS custom properties.

```html
<div class="wdm-component">
  <!-- toolbar, canvas, panel, stats bar go here -->
</div>
```

Load the stylesheet in your template:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'netbox_wdm/css/wdm-components.css' %}">
```

The component root reads `data-bs-theme` from a parent element to switch between dark and light palettes automatically — no extra JS needed.

---

## 3. Color Palette

All colors are defined as CSS custom properties on `.wdm-component`. Never use hex values directly — always reference these variables.

| Variable | Purpose |
|---|---|
| `--wdm-bg` | Canvas / panel background |
| `--wdm-bg-card` | Card / input surface (slightly lighter than bg) |
| `--wdm-border` | Borders, dividers, separator lines |
| `--wdm-text` | Primary body text |
| `--wdm-text-muted` | Secondary / hint text |
| `--wdm-text-label` | Row label text (left side of detail rows) |
| `--wdm-link` | Interactive links and active pill highlight |
| `--wdm-live` | Live / active status (green) |
| `--wdm-planned` | Planned status (amber) |
| `--wdm-pending` | Pending / in-progress status (orange) |
| `--wdm-danger` | Error / protected / destructive (red) |
| `--wdm-muted` | Disabled / draft state (grey) |

Light mode overrides are applied via `[data-bs-theme="light"] .wdm-component`.

---

## 4. Badge (`.wdm-badge`)

Use badges to show status inline with text. They are small (9px, uppercase) and meant for tight spaces.

**Available variants:**

| Class | Color | When to use |
|---|---|---|
| `.wdm-badge--lit` | Green | Channel is carrying traffic |
| `.wdm-badge--active` | Green | Service is active (alias for lit) |
| `.wdm-badge--planned` | Amber | Service planned but not provisioned |
| `.wdm-badge--reserved` | Orange | Channel reserved for future use |
| `.wdm-badge--available` | Grey | Channel available for assignment |
| `.wdm-badge--protected` | Red | Channel or service is protected; do not touch |

```html
<span class="wdm-badge wdm-badge--lit">Lit</span>
<span class="wdm-badge wdm-badge--reserved">Reserved</span>
<span class="wdm-badge wdm-badge--protected">Protected</span>
```

Do not use badges for counts or non-status information — use plain text for those.

---

## 5. Legend (`.wdm-legend`)

The legend is an absolutely-positioned overlay anchored to the **bottom-left** of the canvas container. It collapses **downward** — the bottom edge stays fixed and the content shrinks into a small pill-shaped bar at the bottom corner.

**Rules:**
- Only include items that are currently visible on the canvas. If a filter hides all reserved channels, remove the "Reserved" entry from the legend. Rebuild on every render.
- Group related items under `wdm-legend__section` with a section title.
- Section ordering convention: **status items first** (lit, reserved, available), then **structural items** (grid positions, wavelength bands), then **interaction hints** (selected, hover).

```html
<div class="wdm-component">
  <div class="wdm-legend" id="my-legend">
    <div class="wdm-legend__header">
      <span class="wdm-legend__title">Legend</span>
      <button class="wdm-legend__toggle" aria-label="Toggle legend">▼</button>
    </div>
    <div class="wdm-legend__body">
      <div class="wdm-legend__section">
        <div class="wdm-legend__section-title">Status</div>
        <div class="wdm-legend__item">
          <span class="wdm-legend__dot" style="background:#00cc66"></span>
          Lit
        </div>
        <div class="wdm-legend__item">
          <span class="wdm-legend__dot" style="background:#ffaa00"></span>
          Reserved
        </div>
      </div>
    </div>
  </div>
</div>
```

The `data-collapsed` attribute is managed by JS. When collapsed, the legend shrinks to a 24px pill showing "Legend ▲". When expanded, content grows upward from the bottom edge, toggle shows "▼".

---

## 6. Detail Panel (`.wdm-detail-panel`)

A slide-in panel anchored to the right edge of the canvas container. On mobile it becomes a bottom sheet.

**Structure:**

```html
<div class="wdm-detail-panel" id="detail-panel" role="complementary" aria-label="Details">
  <div class="wdm-detail-panel__header">
    <span class="wdm-detail-panel__title">Channel C32</span>
    <button class="wdm-detail-panel__close" aria-label="Close panel">&times;</button>
  </div>
  <div class="wdm-detail-panel__body">

    <!-- Card with rows -->
    <div class="wdm-detail-card">
      <div class="wdm-detail-card__heading">Wavelength</div>

      <!-- Text row -->
      <div class="wdm-detail-card__row">
        <span class="wdm-detail-card__label">Grid position</span>
        <span class="wdm-detail-card__value">32</span>
      </div>

      <!-- Link row -->
      <div class="wdm-detail-card__row">
        <span class="wdm-detail-card__label">Service</span>
        <a class="wdm-link wdm-detail-card__value" href="/services/12/">SVC-0012</a>
      </div>

      <!-- Badge row -->
      <div class="wdm-detail-card__row">
        <span class="wdm-detail-card__label">Status</span>
        <span class="wdm-badge wdm-badge--lit">Lit</span>
      </div>
    </div>

  </div>
</div>
```

**Escape key** and close button should be wired by the constructor.

---

## 7. Toolbar (`.wdm-toolbar`)

The toolbar sits above the canvas, below any page heading. It wraps at narrow widths.

**Structure rules:**
1. Start with pill groups (exclusive mode selectors).
2. Add a separator between groups of unrelated controls.
3. Place `wdm-toolbar__spacer` to push right-side controls to the far right.
4. Search input goes last on the right.

```html
<div class="wdm-toolbar wdm-component">

  <!-- Exclusive mode group (only one active at a time) -->
  <div class="wdm-pill-group" role="group" aria-label="View mode">
    <button class="wdm-pill wdm-pill--active" aria-pressed="true">Grid</button>
    <button class="wdm-pill" aria-pressed="false">Spectrum</button>
  </div>

  <!-- Separator -->
  <div class="wdm-separator" role="separator"></div>

  <!-- Independent filter toggles (any combination allowed) -->
  <div class="wdm-pill-filter" role="group" aria-label="Filters">
    <button class="wdm-pill wdm-pill--on" style="--pill-color:#00cc66" aria-pressed="true">Lit</button>
    <button class="wdm-pill wdm-pill--off" style="--pill-color:#ffaa00" aria-pressed="false">Reserved</button>
  </div>

  <!-- Spacer pushes the following to the right -->
  <div class="wdm-toolbar__spacer"></div>

  <!-- Search -->
  <input class="wdm-search" type="search" placeholder="Search…" aria-label="Search channels">

</div>
```

**Pill group (exclusive):** Only one pill has `wdm-pill--active`. Clicking another deactivates the current one. Use `aria-pressed` to reflect state.

**Pill filter (independent):** Each pill toggles on/off independently. Use `wdm-pill--on` / `wdm-pill--off` modifier and set `--pill-color` to the associated status color. Use `aria-pressed` on each button.

---

## 8. Stats Bar (`.wdm-stats-bar`)

A slim (28px) bar pinned to the bottom of the canvas. Surfaces aggregate counts.

**Stat ordering:** Essential counts left (total channels, lit count), secondary/contextual counts right.

Mark the most important stats with `wdm-stat--essential` — these remain visible on mobile when non-essential stats are hidden.

```html
<div class="wdm-stats-bar wdm-component">
  <div class="wdm-stats-bar__left">
    <span class="wdm-stat wdm-stat--essential">
      <span class="wdm-stat__label">Channels:</span> 44
    </span>
    <span class="wdm-stats-bar__dot" aria-hidden="true">·</span>
    <span class="wdm-stat wdm-stat--lit">
      <span class="wdm-stat__label">Lit:</span> 28
    </span>
    <span class="wdm-stats-bar__dot" aria-hidden="true">·</span>
    <span class="wdm-stat wdm-stat--reserved">
      <span class="wdm-stat__label">Reserved:</span> 4
    </span>
  </div>
  <div class="wdm-stats-bar__right">
    <span id="status-msg"></span>
  </div>
</div>
```

**Messages:** Use `setMessage()` for status updates — they appear on the right side and auto-clear. The left side (counts) is never replaced. Do not use alerts or toasts for minor status updates from canvas actions.

---

## 9. Theme Integration

The library automatically responds to Bootstrap's `data-bs-theme` attribute. No extra work is needed if your page already sets this.

**Rules:**
- Always use `--wdm-*` variables for colors inside `.wdm-component`.
- Never hardcode hex values for backgrounds, text, or borders.
- For SVG `fill` and `stroke`, use Bootstrap variables (`var(--bs-body-color)`, `var(--bs-primary)`) since SVG elements live inside the canvas, not inside `.wdm-component`.

```css
/* Correct */
.my-element {
  color: var(--wdm-text);
  border-color: var(--wdm-border);
}

/* Wrong */
.my-element {
  color: #ccc;
  border-color: #444;
}
```

---

## 10. Responsive Design

### Breakpoints

| Breakpoint | Width | Behavior |
|---|---|---|
| Desktop | > 991px | Full layout, panel slides in from right |
| Tablet | ≤ 991px | Panel overlays canvas (absolute, full height, shadow) |
| Mobile | ≤ 767px | Panel becomes bottom sheet (50vh max), toolbar compacts, legend hidden, non-essential stats hidden |

### Component behavior at each breakpoint

**Detail panel:**
- Desktop: side-by-side with canvas, no shadow.
- Tablet: overlays canvas, `box-shadow: -4px 0 16px rgba(0,0,0,0.3)`.
- Mobile: fixed bottom sheet, slides up from bottom, swipe-down to dismiss.

**Toolbar:**
- Desktop: single row, full labels.
- Mobile: smaller padding and font (10px), search wraps to its own row (`order: 99`).

**Stats bar:**
- Mobile: only `wdm-stat--essential` stats are visible. Mark secondary stats without this class.

**Legend:**
- Mobile: hidden entirely (`display: none`). Canvas space is too limited.

---

## 11. Touch & Accessibility

### Touch targets

All interactive elements must have a minimum tap target of **44×44px**, even if the visual element is smaller. Use padding to expand the hit area without changing the visual size.

```css
.wdm-detail-panel__close {
  padding: 12px;
  margin: -8px;
}
```

### Swipe-to-dismiss (mobile bottom sheet)

Wire `touchstart` / `touchmove` / `touchend` on the panel header. If the user drags down more than 60px, close the panel.

### Focus states

Every interactive element must have a visible focus ring. The library provides `:focus-visible` styles on `.wdm-pill`, `.wdm-link`, `.wdm-legend__toggle`, and `.wdm-detail-panel__close`. Do not override these with `outline: none`.

### ARIA labels

| Element | Required attribute |
|---|---|
| `.wdm-detail-panel` | `role="complementary"`, `aria-label="Details"` |
| `.wdm-detail-panel__close` | `aria-label="Close panel"` |
| `.wdm-legend__toggle` | `aria-label="Toggle legend"` |
| Pill group | `role="group"`, `aria-label="<group name>"` |
| Each pill | `aria-pressed="true\|false"` |
| `.wdm-separator` | `role="separator"` |
| Dot separators in stats bar | `aria-hidden="true"` |

### Keyboard navigation

- **Escape** — close the open detail panel.
- **Tab** — move through toolbar controls, close button, and panel rows in DOM order.
- Pill groups should support **Left/Right arrow** keys to move between pills in the group (implement with a `keydown` handler; the CSS does not do this automatically).

---

## 12. TypeScript Component Structure

All components live in `netbox_wdm/static/netbox_wdm/src/`:

| File | Export | Purpose |
|---|---|---|
| `wavelength-editor-types.ts` | `ChannelData`, `PortData`, `EditorConfig` | Type definitions for the wavelength editor |
| `wavelength-editor.ts` | `WavelengthEditor` class | ROADM channel assignment editor |

Future components follow the same pattern — one file per component, types in a separate `-types.ts` file.

Import via the entry point or barrel:
```typescript
import type { ChannelData, EditorConfig } from './wavelength-editor-types';
```

---

## 13. Debug Mode

When Django runs with `DEBUG=True`, templates should pass `debug: true` in the editor config. All editor JavaScript should use a `dbg()` helper that logs to `console.log` with a `[WDM]` prefix only when debug is enabled.

```typescript
function dbg(...args: unknown[]): void {
  if ((window as any).WAVELENGTH_EDITOR_CONFIG?.debug) {
    console.log('[WDM]', ...args);
  }
}

dbg('loadData() response:', { channels: response.channels.length });
// Outputs: [WDM] loadData() response: {channels: 44}
```

Debug logging covers: config load, DOM element discovery, API fetch/response, state after load, and errors. In production (`DEBUG=False`), no console output is produced.
