# Strata web

> **Stub for Phase 0.** The web dashboard lands in Phase 2
> (signup/login) and Phase 5 (read-only dashboard).

Next.js 15 with the App Router. TypeScript, `pnpm`.

The web dashboard is **read-only** plus signup/login. It is the
account system of record for the backend and the place where
users register their existing clusters.

## Planned pages

- `/signup` — create an account
- `/login` — sign in
- `/device` — OIDC device-code display, polled by the TUI
- `/dashboard` — list of user's clusters + health summary
- `/clusters/[id]` — per-cluster detail (read-only)
- `/clusters/[id]/resources` — resource browser
- `/clusters/[id]/history` — recent actions

## See also

- `../docs/nextjs.md`
- `../docs/strata/backend-architecture.md`