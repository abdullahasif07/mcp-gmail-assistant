# Mailmind — Gmail assistant over MCP

Mailmind is a small Gmail client with an AI assistant built in. You read and
reply to mail in a Gmail-style inbox, ask the AI (OpenAI) to draft replies, and use a
chat bar for requests like *"show unread from Marcus"* or *"email
sam@example.com that I'll be late"*.

The landing page offers two ways in:

- **Demo inbox (for recruiters).** A sandboxed dummy account with fictional
  emails. No Google sign-in needed. Every feature works, and "sent" mail only
  lands in that visitor's own Sent folder. It can be gated with an access code.
- **Your own Gmail.** Real access through Google OAuth. Shown only when Google
  credentials are configured (and `GMAIL_ENABLED` isn't `false`), so a
  demo-only deployment needs no Google setup at all.

All Gmail access goes through a **Model Context Protocol (MCP) server**, so the
same Gmail tools the UI uses are the ones the model calls.

## How it works

```
 Browser (Next.js)                 FastAPI backend                    Node MCP server
┌────────────────┐  cookie +   ┌──────────────────────┐   stdio    ┌──────────────────┐
│ /inbox UI      │ ─────────▶ │ /emails  /ai  /chat  │ ─────────▶ │ gmail_list_...   │ ──▶ Gmail API
│ chat bar       │  JSON       │ OpenAI tool loop     │  per user  │ gmail_read_...   │
└────────────────┘             │ SQLite (encrypted    │            │ gmail_send_...   │
                               │ refresh tokens)      │            │ gmail_get_thread │
                               └──────────────────────┘            └──────────────────┘
```

- **`frontend/`**: Next.js 16 + Tailwind. Landing page, inbox, reply panel,
  AI chat bar.
- **`backend/`**: FastAPI.
  - Handles Google OAuth and stores each user's refresh token in SQLite,
    encrypted with Fernet.
  - Issues an HttpOnly JWT session cookie.
  - For each request, starts the MCP server with **that user's** token.
- **`mcp-server/`**: a stdio MCP server exposing four Gmail tools (list,
  read, send, get thread). It works on its own with any MCP client too.

In demo mode the backend swaps the MCP server for `DemoMailbox`
(`backend/services/demo_mailbox.py`). It implements the same four tools with
identical output, including Gmail-style search (`from:`, `is:unread`,
`label:`, `newer_than:7d`, quoted phrases, `-negation`), on a per-visitor
in-memory copy of the seed data. Routes and the AI tool loop don't know which
mode they're in.

Sending email from chat always takes two steps. When the model calls
`gmail_send_message`, the backend doesn't send. It returns the draft as a
`pendingAction`, and the email goes out only after the user clicks
**Confirm & send** (`POST /chat/confirm`).

## Running locally

Prerequisites: Python 3.12+, Node 20+ and an OpenAI API key. That's enough
for the demo inbox.

For "Use your own Gmail" you also need a Google Cloud OAuth **Web** client
with the Gmail API enabled and `http://localhost:8001/auth/callback` as an
authorized redirect URI. While the Google app is in testing mode, only
accounts listed as **test users** can sign in, and their access expires
after 7 days.

Quick start with `make`:

```bash
make setup    # once: venv + all deps, creates backend/.env with generated secrets
# put your OPENAI_API_KEY in backend/.env
make run      # backend :8001 + frontend :3000 together; Ctrl+C stops both
```

`make help` lists the other targets (`backend`, `frontend`, `test`, `lint`).

Or step by step:

```bash
# 1. MCP server deps (the backend spawns it)
cd mcp-server && npm install && cd ..

# 2. Backend
cd backend
cp .env.example .env          # fill in keys + generate the two secrets
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
cd ..

# 3. Frontend (new terminal)
cd frontend
cp .env.example .env.local
npm install && npm run dev    # http://localhost:3000
```

Open http://localhost:3000, click **Sign in with Google**, and you'll land in
the inbox.

### Docker

```bash
cp backend/.env.example backend/.env   # fill it in
docker compose up --build              # frontend :3000, backend :8001
```

The backend image bundles Node so it can spawn the MCP server. The SQLite DB
lives on the `mailmind-data` volume.

## API

| Method | Path                | Purpose                                     |
| ------ | ------------------- | ------------------------------------------- |
| GET    | `/auth/login`       | Redirect to Google consent                  |
| GET    | `/auth/callback`    | OAuth callback; sets session cookie         |
| GET    | `/auth/options`     | Which sign-in options are available         |
| POST   | `/auth/demo`        | Start a demo session (`{accessCode}`)       |
| GET    | `/auth/me`          | Current account and mode, or 401           |
| POST   | `/auth/logout`      | Forget the stored token, clear cookie       |
| GET    | `/emails?query=`    | List messages for a Gmail search query      |
| GET    | `/emails/{id}`      | Full message                                |
| POST   | `/emails/send`      | Send; `inReplyTo` keeps the reply threaded  |
| POST   | `/ai/suggest-reply` | AI reply draft for a message                |
| POST   | `/chat`             | Natural-language assistant over MCP tools   |
| POST   | `/chat/confirm`     | Execute a send the assistant prepared       |

Interactive docs: http://localhost:8001/docs

## Development

```bash
cd backend && pip install -r requirements-dev.txt
pytest            # unit tests
ruff check .      # lint

cd frontend && npm run lint && npx tsc --noEmit
cd mcp-server && node --check index.js
```

CI (`.github/workflows/`) runs all of the above on every push and pull
request, plus a secret scan. A weekly job runs dependency audits.

## Security notes and cost controls

- `DEMO_ACCESS_CODE` gates the demo, with 10 attempts per IP per 10 minutes.
- `AI_DAILY_LIMIT` caps AI requests app-wide per day, and
  `DEMO_SESSION_AI_LIMIT` caps each demo visitor. Over the limit, the API
  returns a friendly 429. Counters are in memory and reset on restart, so also
  set a monthly budget limit in the OpenAI dashboard.

- Refresh tokens are encrypted at rest. Rotating `TOKEN_ENCRYPTION_KEY`
  disconnects everyone, and rotating `SESSION_JWT_SECRET` logs everyone out.
- The OAuth `state` is checked on the callback to prevent login CSRF.
- `API_KEY` / `NEXT_PUBLIC_API_KEY` is shipped to the browser. It keeps out
  casual probes but isn't real authentication; the session cookie is.
