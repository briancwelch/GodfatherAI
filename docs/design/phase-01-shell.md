# Phase 01 shell design

## Purpose and hierarchy

Establish an accessible local Command Center frame. The sole page is Overview: brand/navigation, development label, purpose, explicit disconnected state, then Phase 01 scope. The only actions navigate within the page. Future sections are labeled unavailable and have no management controls or API dependencies.

## Components and states

- Responsive sidebar/header, page heading, static phase label, empty connection panel, scope cards, footer.
- Minimal shadcn/ui Button with shared class utilities. No icon dependency is needed; future icons follow Font Awesome 7 Free.
- Dark/light semantic tokens follow system preference; configurable layouts/themes belong to later phases.
- Empty/disconnected is the only operational state. No requests means no fabricated loading, success, permission, offline telemetry, or error state. Future backend-dependent components must define those states before implementation.

## Accessibility and responsive behavior

Semantic landmarks and heading levels, a skip link, visible keyboard focus, text-based status, and readable muted text. Planned navigation entries are noninteractive and explain their unavailable state to assistive technology. The sidebar becomes a compact top section with native collapsible navigation on smaller screens; cards stack. No motion or externally loaded fonts are required.

## Acceptance checklist

- Local page identifies itself as Phase 01 with no backend or user session.
- No invented metrics, login behavior, or privileged controls.
- Overview and phase anchor work with keyboard navigation.
- Content fits desktop and narrow screens without horizontal overflow.
- Light and dark system preferences are supported.
- Browser reports no hydration errors; production build and strict type checks pass.

Check results belong in `docs/operations/phase-01.md`; this checklist is not evidence of execution.
