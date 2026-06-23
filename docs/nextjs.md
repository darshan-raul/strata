# Next.js (in Strata)

> **Stub for Phase 0.** Full doc lands in Phase 2 (web signup/login)
> and Phase 5 (read-only dashboard).

[Next.js 15](https://nextjs.org/) with the App Router is the
framework for Strata's web dashboard. Strict TypeScript,
`pnpm` as the package manager.

The web dashboard is **read-only** plus signup/login. It is the
account system of record for the backend and the place where
users register their existing clusters.

Pages planned:

- `/signup` — create an account
- `/login` — sign in
- `/device` — OIDC device-code display, polled by the TUI
- `/dashboard` — list of user's clusters + health summary
- `/clusters/[id]` — per-cluster detail (read-only)
- `/clusters/[id]/resources` — resource browser
- `/clusters/[id]/history` — recent actions

The web talks to the backend's orchestrator over HTTPS with the
user's session cookie. Server actions in Next.js are the
preferred way to call the orchestrator from form submits.

Planned outline:

1. App Router vs Pages Router (App Router only)
2. Server Components vs Client Components
3. Auth in Next.js (cookies + server actions)
4. Talking to the orchestrator (server-only `fetch` with the
   session cookie)
5. Streaming (Phase 5+ — for tool call progress)
6. Styling (Tailwind + shadcn/ui — TBD)
7. Form handling with server actions
8. Testing
9. What to read next