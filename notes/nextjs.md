# Next.js 15

The web frontend for Strata. Strata uses **Next.js 15 with the App
Router** because:

1. **Server components by default** — less JavaScript shipped to
   the browser, easier to reason about.
2. **Server actions for mutations** — the UI calls the orchestrator
   from the server, no separate BFF tier.
3. **Native streaming (RSC + Suspense)** — the chat rail can stream
   tokens from the agent-service through Next.js to the browser.
4. **Single language (TypeScript) end-to-end** — same types in
   server and client, validated at build time.

The web UI is **for demos**, not the day-to-day interface (the
Typer CLI is). It lands in **Phase 5**. This doc is the design
you need to understand before that phase.

---

## 1. Mental model

Next.js 15 App Router splits rendering into two flavors:

| Component type | Where it runs | What it can do | What it can't do |
|---|---|---|---|
| **Server Component** (default) | Server only | Fetch data, query DB, call APIs | Use `useState`, `useEffect`, click handlers |
| **Client Component** (`"use client"`) | Browser (after hydration) | Interactive state, event handlers, browser APIs | Directly query DBs; needs an API route or server action |

The default is server. You opt into client only when you need
interactivity. Strata's web UI will be ~70% server, ~30% client
(the chat rail and form widgets are client; the dashboards and
lists are server).

### Routes

The App Router uses **file-based routing** under `app/`:

```
app/
  layout.tsx          # root layout, wraps everything
  page.tsx            # /, dashboard
  clusters/
    page.tsx          # /clusters, list
    [id]/
      page.tsx        # /clusters/cl-001, detail
  chat/
    page.tsx          # /chat, full-page chat
  api/                # route handlers (rarely needed; use server actions instead)
    chat/
      route.ts        # POST /api/chat — only if you need raw HTTP
```

Folders = URL segments. Square-bracket folders = dynamic segments.
Special files:

- `page.tsx` — the route's UI.
- `layout.tsx` — wraps `page.tsx` and any children. Persists
  across navigation (the chat rail lives here).
- `loading.tsx` — Suspense fallback.
- `error.tsx` — error boundary.
- `not-found.tsx` — 404.

### Server actions

A server action is a server-side function you call from a client
component or form. The function runs on the server (full Node.js
access: env vars, DB, internal APIs), the client just calls it.

```tsx
// app/clusters/page.tsx
import { listClusters } from "@/lib/orchestrator";

export default async function Page() {
  const clusters = await listClusters();   // server-side fetch
  return <ClusterList clusters={clusters} />;
}
```

```tsx
// app/clusters/new/actions.ts
"use server";

export async function createCluster(formData: FormData) {
  const name = formData.get("name");
  await fetch("http://orchestrator:8080/clusters", { method: "POST", body: ... });
  revalidatePath("/clusters");
}
```

```tsx
// app/clusters/new/page.tsx
import { createCluster } from "./actions";

export default function Page() {
  return <form action={createCluster}>...</form>;
}
```

Server actions replace most BFF/API-route code. Use them for any
mutation that originates in the UI.

---

## 2. Strata's web pages (Phase 5)

Three pages. Each is a server component with a small client
island for interactivity.

### `/` — cluster list

```tsx
// app/page.tsx
import { listClusters } from "@/lib/orchestrator";

export default async function Page() {
  const clusters = await listClusters();
  return (
    <div>
      <h1>Your clusters</h1>
      <ClusterTable clusters={clusters} />
    </div>
  );
}
```

`listClusters` calls the orchestrator's `GET /clusters` (server-to-server,
no CORS, internal DNS). Server-rendered HTML. Fast first paint.

### `/clusters/$id` — cluster detail

```tsx
// app/clusters/[id]/page.tsx
import { getCluster } from "@/lib/orchestrator";
import { notFound } from "next/navigation";

export default async function Page({ params }: { params: { id: string } }) {
  const cluster = await getCluster(params.id);
  if (!cluster) notFound();
  return <ClusterDetail cluster={cluster} />;
}
```

A "logs" tab is a client component that polls or subscribes for
log updates (Phase 5+).

### `/chat` — full-page chat (or right-rail on `/` and `/clusters/$id`)

The interesting page. The chat rail needs:

- Streaming tokens from `POST /agent/chat`.
- Local state for the message history.
- Display of tool calls (`<ToolCallCard />` for confirmation UX,
  Phase 6+).
- Markdown rendering of the assistant's responses.

This is the only place Strata uses significant client-side state.

```tsx
// app/chat/page.tsx
import { Chat } from "./chat-client";

export default function Page() {
  return <Chat />;
}
```

```tsx
// app/chat/chat-client.tsx
"use client";

import { useState } from "react";

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  async function send() {
    const res = await fetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: input }),
    });
    const reader = res.body!.getReader();
    // ... read NDJSON / SSE chunks, append to messages
  }

  return (
    <div>
      <MessageList messages={messages} />
      <Input value={input} onChange={setInput} onSubmit={send} />
    </div>
  );
}
```

The fetch goes to `/api/chat` (a Next.js route handler) which
proxies to `http://agent-service:8080/chat` and streams the
response back. Why a route handler instead of calling the
agent-service directly from the browser? The agent-service is
internal ClusterIP; the browser can't reach it. Plus auth.

```tsx
// app/api/chat/route.ts
export async function POST(req: Request) {
  const body = await req.json();
  const upstream = await fetch("http://agent-service:8080/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return new Response(upstream.body, {
    headers: { "Content-Type": "application/x-ndjson" },
  });
}
```

The route handler passes the upstream response body straight
through. Backpressure and chunked transfer work without any
extra code.

### Layout and the right-rail chat

The chat rail is a client component that lives in the root layout:

```tsx
// app/layout.tsx
import { CopilotRail } from "./copilot-rail";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        <div className="grid lg:grid-cols-[1fr_400px]">
          <main>{children}</main>
          <CopilotRail />
        </div>
      </body>
    </html>
  );
}
```

On `lg:` screens, the rail is a 400px column. On smaller screens,
it's full-page at `/chat`. The rail is a client component
(`"use client"`) that owns its own message state.

---

## 3. Streaming tokens to the browser

Three options, in order of complexity:

1. **NDJSON via fetch + ReadableStream** (what the Python side does
   in Phase 2). Easy to debug. The browser reads line-by-line
   and parses.
2. **Server-Sent Events (SSE)** via `EventSource` or
   `fetch` + `ReadableStream` with `text/event-stream`. Standard,
   auto-reconnect, but harder to debug.
3. **WebSocket** via `ws`. Two-way, but overkill for one-way
   streaming.

Strata's web UI uses **NDJSON** in Phase 5 (the agent-service can
be updated to emit SSE in Phase 5+ without changing the wire
format on the browser side, by wrapping the body). Phase 6+ can
move to SSE without changing the agent's API.

### Reading NDJSON in the browser

```tsx
const res = await fetch("/api/chat", { method: "POST", body: JSON.stringify(body) });
const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop()!;     // last partial line stays in buffer
  for (const line of lines) {
    if (!line) continue;
    const event = JSON.parse(line);
    handleEvent(event);
  }
}
```

`handleEvent` is the dispatch:

```tsx
function handleEvent(event: { type: string; [k: string]: any }) {
  switch (event.type) {
    case "token":
      appendToLastAssistantMessage(event.text);
      break;
    case "tool_call":
      addToolCallCard(event.name, event.args);
      break;
    case "tool_result":
      completeToolCallCard(event.name, event.result);
      break;
    case "done":
      markStreamComplete();
      break;
  }
}
```

### React 19's `use()` hook for streaming

React 19 (which ships with Next.js 15) has a `use()` hook that
can unwrap a Promise. The pattern for streaming from a server
component is:

```tsx
import { use } from "react";

async function* streamAgent(message: string) {
  const res = await fetch("http://agent-service:8080/chat", { ... });
  const reader = res.body!.getReader();
  // ... yield parsed events
}

function ChatStream({ message }: { message: string }) {
  const events = use(streamAgent(message));   // suspends until stream starts
  return <MessageList events={events} />;
}
```

This is the "RSC streaming" pattern. You can use it without a
client component for read-only streams. For two-way chat (user
input → stream), you need a client component with a fetch.

---

## 4. Auth (Phase 6+)

For Phase 5 single-user, there's no auth on the web UI (the
orchestrator trusts the user's header). Phase 6 introduces
Zitadel.

The flow:

1. Browser hits a protected page.
2. Next.js middleware (`middleware.ts`) checks for a session
   cookie.
3. If absent, redirect to Zitadel's login page.
4. Zitadel redirects back with a `code` query param.
5. Next.js exchanges `code` for tokens, sets a session cookie.
6. Subsequent requests carry the cookie. The orchestrator
   verifies the JWT (Zitadel's public keys) on each API call.

Zitadel discovery URL: `https://zitadel.example.com/.well-known/openid-configuration`.

For Phase 5 we use a `MOCK_USER` header (`X-Strata-User-Id: dev`)
that the orchestrator trusts. The Next.js dev server sets it
from a local config.

```tsx
// lib/orchestrator.ts
const USER_ID = process.env.STRATA_USER_ID ?? "dev";

export async function orchFetch(path: string, init?: RequestInit) {
  return fetch(`http://orchestrator:8080${path}`, {
    ...init,
    headers: {
      "X-Strata-User-Id": USER_ID,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
}
```

---

## 5. Forms and validation

Strata's cluster-create form is a server action that takes
`FormData`. Validation happens server-side:

```tsx
// app/clusters/new/actions.ts
"use server";

import { z } from "zod";
import { redirect } from "next/navigation";

const CreateCluster = z.object({
  name: z.string().min(1).max(64).regex(/^[a-z0-9-]+$/),
  region: z.enum(["us-west-2", "us-east-1", "eu-west-1"]),
  k8sVersion: z.string().regex(/^1\.\d+$/),
});

export async function createCluster(formData: FormData) {
  const parsed = CreateCluster.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return { error: parsed.error.flatten() };
  }
  const res = await fetch("http://orchestrator:8080/clusters", {
    method: "POST",
    body: JSON.stringify(parsed.data),
  });
  const cluster = await res.json();
  redirect(`/clusters/${cluster.id}`);
}
```

For client-side validation (instant feedback), use
`react-hook-form` + `@hookform/resolvers/zod`. For just server-side
validation (cleaner; client waits for the redirect), skip the
client lib.

Strata uses server-only validation in Phase 5. Adds the client
form lib in Phase 6+ if needed.

---

## 6. Styling

**Tailwind CSS** is the default for App Router. Strata uses
Tailwind because:

- No runtime cost (CSS is generated at build time).
- Pairs well with server components.
- The user can read it.

```bash
pnpm add -D tailwindcss postcss autoprefixer
pnpm tailwindcss init -p
```

`tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

`app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

For component primitives, Strata uses **shadcn/ui** (the
"copy-paste a component, not install a library" approach) for
the chat rail, dialogs, and form widgets. shadcn/ui requires
Tailwind. Components land in `components/ui/`.

For the data tables in `/clusters`, use **TanStack Table** if
filtering/sorting matters. For a simple read-only table, plain
HTML + Tailwind.

---

## 7. Package manager and tooling

Strata uses **pnpm**:

- Fast install (hard links, content-addressable store).
- Strict (no hoisting surprises).
- Native workspaces.

```bash
pnpm install
pnpm dev          # next dev
pnpm build        # next build
pnpm start        # next start
pnpm lint         # next lint (or eslint directly)
pnpm test         # vitest or jest
```

For the chat client, **Vitest** for unit tests, **Playwright**
for E2E. Phase 5+ decides which is worth setting up.

---

## 8. Common pitfalls

1. **Forgetting `"use client"`** — if your component uses
   `useState` without the directive, you get a build error. Easy
   to fix; easy to forget.
2. **Using `next/router` instead of `next/navigation`** — App
   Router uses the new `useRouter` from `next/navigation`. The
   old one is for the Pages Router and breaks in App Router.
3. **Server components can't pass functions to client components.**
   Pass data, not callbacks. For mutations, use server actions
   via `<form action={...}>`.
4. **Env vars are server-side by default.** `process.env.X` in a
   server component is the value at request time. In a client
   component, you must use `NEXT_PUBLIC_X` (or pass it as a prop
   from a server component).
5. **Streaming requires a `Suspense` boundary** if you want
   progressive rendering. Without `<Suspense>`, the whole
   response is buffered.
6. **`revalidatePath` and `revalidateTag`** are how you invalidate
   the server-side cache. Use them after mutations so the next
   render fetches fresh data.
7. **Don't use `getServerSideProps` / `getStaticProps`** — those
   are Pages Router. App Router fetches in the server component
   itself.

---

## 9. Local dev

```bash
cd web/
pnpm install
pnpm dev            # http://localhost:3000
```

`pnpm dev` reads `.env.local` (gitignored). The orchestrator and
agent-service are accessed via `http://localhost:8080` and
`http://localhost:8080` respectively (port-forwarded from the
Kind cluster) or via in-cluster DNS if Next.js is also in the
cluster.

For the "Next.js in the cluster" deployment (Phase 5+), the
web deployment is one container in the `strata` namespace,
served by Node.js, behind a Kong route. The dev loop is
`pnpm dev` against a port-forwarded backend; the production
image is built by CI, pushed to ECR, and deployed via ArgoCD.

---

## 10. What to read next

- `docs/strata/agent-architecture.md` — how the chat rail fits
  into the system.
- `AGENTS.md §7 Phase 5` — the Phase 5 deliverable for `web/`.
- Next.js docs: <https://nextjs.org/docs>
- App Router migration guide: <https://nextjs.org/docs/app/building-your-application/upgrading/app-router-migration>
- React 19 `use()` hook: <https://react.dev/reference/react/use>
- shadcn/ui: <https://ui.shadcn.com/>
