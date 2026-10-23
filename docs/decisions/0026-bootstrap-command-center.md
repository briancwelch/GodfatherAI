# Bootstrap Command Center components

Accepted by the owner, 2026-10-22, as a website presentation milestone.

Use the stable Bootstrap 5.3.8 package, pinned in npm, for the existing Next.js
React/TSX Command Center. Python/FastAPI, worker protocols and permissions retain
their existing responsibilities. The Bootstrap package supplies local CSS; no CDN
or Bootstrap JavaScript plugins are loaded. React remains the sole owner of
interactive state, progress values, tabs, dismissals, forms and confirmations.

Existing screen content and authenticated workflows use Bootstrap cards, buttons,
forms, tables, navigation and alerts. Notifications use Bootstrap toast markup,
and all task/download/contribution progress uses one accessible React component
with Bootstrap progress markup. Unknown progress has no aria-valuenow; a measured
zero is represented as zero. Existing persistent error/active-work notifications
remain persistent. Reduced-motion settings disable progress animations.

A small theme stylesheet maps Bootstrap variables to the existing Godfather
navy/cyan light and neutral dark palettes. Existing Tailwind utilities remain for
compatible local layout use. The shared Button wrapper now emits Bootstrap
classes. Font Awesome continues to supply the shared icons.

The existing PostgreSQL-backed appearance JSON stores validated, additive
component options. Missing fields receive defaults; existing colors and layout
values are preserved. No schema migration is needed. Administrators alone may
write these shared settings, with the existing permission, origin and audit checks.
Settings accept bounded numbers, enumerations, booleans and hex colors, never
arbitrary CSS, markup, scripts or URLs. Semantic badge foreground colors are
chosen for contrast against their configured backgrounds.

The new direct dependency is justified by the requested site-wide Bootstrap
presentation. Its Popper peer dependency is installed by npm but no Bootstrap or
Popper runtime code is imported. Packaging, deployment and native worker builds
are outside this milestone. A coordinator update requires the matching API and
dashboard so new appearance fields are understood together.
