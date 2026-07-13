# CertOps Dashboard — Design Strategy

## Reference & Guiding Principle

This is an **internal infrastructure tool**, not a consumer SaaS product. The design philosophy prioritizes:

- **Scanability**: Engineers check this like a monitoring dashboard—fast, glanceable, low cognitive friction
- **Clarity over charm**: No marketing fluff, no decorative elements, just clear information hierarchy
- **Distinction between concepts**: Secret Stores vs. Hosts are fundamentally different workflows; the UI must make this visible
- **Deliberate weight on critical actions**: The "Confirm reload" action for host-sourced certs should feel weighty and intentional, never casual

---

## Chosen Design Direction: "Ops-Grade Minimalism"

### Design Movement

**Brutalist infrastructure UI** — inspired by tools like Kubernetes dashboards, Datadog, and internal monitoring platforms. Clean, purposeful, no unnecessary decoration. Monospace accents for technical data. High contrast for scannability.

### Core Principles

1. **Distinction through structure, not decoration** — Secret Stores and Hosts are visually separated sections, not just list items. Each has its own visual language.
2. **Information density with breathing room** — Tables are compact but not cramped. Whitespace is used strategically to separate concerns.
3. **Color as semantic signal** — Status colors (green/yellow/red) are the primary visual language. Accent colors are minimal and purposeful.
4. **Typography hierarchy via weight and scale** — No decorative fonts; use weight shifts and sizing to establish hierarchy.

### Color Philosophy

- **Background**: Clean white (`oklch(1 0 0)`) for maximum contrast and clarity
- **Primary accent**: Deep slate blue (`oklch(0.35 0.08 260)`) — technical, trustworthy, not "SaaS blue"
- **Status colors**:
  - **Healthy**: Muted green (`oklch(0.65 0.12 142)`)
  - **Warning**: Amber (`oklch(0.72 0.15 70)`)
  - **Critical/Overdue**: Red (`oklch(0.55 0.20 25)`)
  - **Pending action**: Slate (`oklch(0.45 0.05 260)`)
- **Borders & dividers**: Subtle gray (`oklch(0.92 0.004 286)`)
- **Text**: Dark slate for body (`oklch(0.235 0.015 65)`), lighter slate for secondary (`oklch(0.55 0.02 260)`)

### Layout Paradigm

- **Sidebar navigation** (persistent, left-aligned) — standard for internal tools
- **Two-column structure for connectors** — Secret Stores (left) and Hosts (right), visually distinct sections
- **Tabular data with inline actions** — certificates displayed as scannable rows with status badges and quick-access buttons
- **Modal detail views** — clicking a cert row opens a detail panel without navigation away
- **Stepper component for host cert pipeline** — the one "design risk" mentioned in the brief; visually distinct from the rest of the UI to signal its importance

### Signature Elements

1. **Status badges** — small, color-coded pills with icons (✓ healthy, ⚠ warning, ✗ critical)
2. **Pipeline stepper** — visual 3-step flow (Renewed → Deployed, pending reload → Reload confirmed) for host-sourced certs
3. **Monospace technical data** — domain names, expiry dates, and technical identifiers use a monospace font for clarity

### Interaction Philosophy

- **Minimal motion** — only essential transitions (modals, toasts, hover states)
- **Confirmation on destructive actions** — "Confirm reload" is deliberately weighty, not a casual button
- **Inline feedback** — status updates, errors, and successes appear in context, not as separate notifications
- **Keyboard accessible** — all actions accessible via keyboard; focus states are clear

### Animation

- **Modal entrance**: 200ms ease-out scale-in from 0.95 opacity
- **Hover states**: 100ms ease-out for button/row highlights
- **Status transitions**: 300ms ease-in-out for color/state changes
- **No entrance animations on page load** — data tables load instantly, no stagger

### Typography System

- **Display/Headings**: System font stack (SF Pro, Segoe UI, Helvetica Neue) at 500–600 weight for hierarchy
- **Body text**: System font at 400 weight, 16px base, 1.5 line height
- **Technical data** (domains, dates, IDs): `SF Mono` or `Menlo` monospace at 13px
- **Labels & UI text**: 500 weight, 14px, uppercase letter-spacing for UI labels

### Brand Essence

**One-liner**: A no-nonsense certificate lifecycle manager built for infrastructure engineers who value clarity and control.

**Personality adjectives**: Reliable, precise, uncluttered.

### Brand Voice

- **Headlines**: Direct, action-oriented. "Reload nginx on prod-web-3" not "Trigger service invalidation event"
- **CTAs**: Clear and specific. "Confirm reload" not "Proceed"
- **Microcopy**: Error messages name the cert and connector. Empty states say what to do next.
- **Example lines**:
  - "3 certs due within 30 days"
  - "Reload pending on prod-api-2 — confirm to restart nginx"

### Wordmark & Logo

A bold, geometric symbol: a **shield with a checkmark** (representing security + verification), rendered in deep slate blue. No text, just the mark. Used in the header and as favicon.

### Signature Brand Color

**Deep slate blue**: `oklch(0.35 0.08 260)` — technical, trustworthy, distinct from typical SaaS blues. Used sparingly for primary actions and accents.

---

## Implementation Notes

- Use **shadcn/ui** components for consistency and accessibility
- **Sidebar layout** with persistent navigation (Connectors, Certificates, Activity, Groups)
- **Two-section connector page** (Secret Stores | Hosts) with distinct visual separation
- **Certificate table** with inline status badges, quick actions, and row-click detail modal
- **Pipeline stepper** for host certs — the visual focal point of the detail view
- **Activity log** grouped by day with clear failure messaging
- **Groups & notification policy** page (lighter touch, simplified UI)
- All mock data is realistic: mix of healthy/warning/critical statuses, multiple connector types, varied renewal histories

---

## Color Token Mapping (for index.css)

```
--primary: oklch(0.35 0.08 260)  // Deep slate blue
--accent: oklch(0.65 0.12 142)   // Muted green (healthy status)
--destructive: oklch(0.55 0.20 25) // Red (critical/overdue)
--warning: oklch(0.72 0.15 70)   // Amber (warning/due soon)
--muted: oklch(0.92 0.004 286)   // Subtle gray (borders, dividers)
```

---

## Status: CHOSEN & COMMITTED

This design direction is locked. All subsequent implementation will follow this ops-grade minimalist approach with strong distinction between connector types and deliberate weight on the host-cert reload action.
