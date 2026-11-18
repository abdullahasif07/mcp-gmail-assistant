# Mailmind frontend

Next.js (App Router) UI for Mailmind. See the [root README](../README.md) for
the full setup, including the backend and MCP server.

```bash
cp .env.example .env.local   # point NEXT_PUBLIC_BACKEND_URL at the backend
npm install
npm run dev                  # http://localhost:3000
```

| Path       | What it is                                              |
| ---------- | ------------------------------------------------------- |
| `app/`     | Routes: `/` landing page, `/inbox` the mail client      |
| `components/` | Sidebar, email view, reply panel, AI chat bar        |
| `lib/api.ts`  | Typed client for the FastAPI backend                 |
| `lib/format.ts` | Helpers for rendering `From` headers               |
