# 0006. A React explorer alongside the static dashboard

**Status:** Accepted

## Context

The static dashboard from ADR 0005 answers fixed questions and works anywhere, which
is what a CI artifact needs. It cannot answer the next question a reader asks: which
hour is busiest on which day, how a single week compares with the month, how the
figures change for a chosen date range. Answering those means filtering and linking
views, which a page without scripts cannot do.

## Decision

Keep the static dashboard unchanged and add a separate interactive explorer in `web/`,
built with Vite, React and TypeScript, with three.js through React Three Fiber for the
weekday by hour view. The explorer reads one JSON file written by
`nyc-lake explore --json`: the analytics report plus its provenance note. The page
validates that file with zod before drawing anything and names the field when it does
not match. A Zustand store links the 3D view and the 2D panels. GitHub Actions builds
the app and publishes it to GitHub Pages.

## Consequences

- Two front ends read the same report, so a figure has one source. The explorer adds
  no query of its own; anything it shows is a sum or a selection of report rows.
- The explorer depends on JavaScript and WebGL. Without WebGL it shows the same data
  as a table, and the static dashboard remains the fallback that needs neither.
- The hosted page uses the committed `web/public/data/report.json`, which is built
  from synthetic months because the TLC files were not reachable from the build
  machine. The page labels it as synthetic; replacing the file with a real export is
  one command.
- The repository now has a Node toolchain to maintain. It is isolated in `web/`, has
  its own lockfile and CI job, and does not affect the Python package.
