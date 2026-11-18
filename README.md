# Mailmind — Gmail assistant over MCP

Mailmind is a small Gmail client with an AI assistant built in. You sign in
with Google, read and reply to mail in a Gmail-style inbox, ask Gemini to
draft replies, and use a chat bar for requests like *"show unread from Stripe"*
or *"email sam@example.com that I'll be late"*.

All Gmail access goes through a **Model Context Protocol (MCP) server**, so the
same Gmail tools the UI uses are the ones the model calls.

## How it works

```
 Browser (Next.js)                 FastAPI backend                    Node MCP server
┌────────────────┐  cookie +   ┌──────────────────────┐   stdio    ┌──────────────────┐
│ /inbox UI      │ ─────────▶ │ /emails  /ai  /chat  │ ─────────▶ │ gmail_list_...   │ ──▶ Gmail API
│ chat bar       │  JSON       │ Gemini tool loop     │  per user  │ gmail_read_...   │
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

Sending email from chat always takes two steps. When Gemini calls
`gmail_send_message`, the backend doesn't send. It returns the draft as a
`pendingAction`, and the email goes out only after the user clicks
**Confirm & send** (`POST /chat/confirm`).

## Running locally

Prerequisites: Python 3.12+, Node 20+, a Gemini API key, and a Google Cloud
OAuth **Web** client with the Gmail API enabled and
`http://localhost:8001/auth/callback` as an authorized redirect URI.

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
| GET    | `/auth/me`          | Connected account, or 401                   |
| POST   | `/auth/logout`      | Forget the stored token, clear cookie       |
| GET    | `/emails?query=`    | List messages for a Gmail search query      |
| GET    | `/emails/{id}`      | Full message                                |
| POST   | `/emails/send`      | Send; `inReplyTo` keeps the reply threaded  |
| POST   | `/ai/suggest-reply` | Gemini reply draft for a message            |
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

## Security notes

- Refresh tokens are encrypted at rest. Rotating `TOKEN_ENCRYPTION_KEY`
  disconnects everyone, and rotating `SESSION_JWT_SECRET` logs everyone out.
- The OAuth `state` is checked on the callback to prevent login CSRF.
- `API_KEY` / `NEXT_PUBLIC_API_KEY` is shipped to the browser. It keeps out
  casual probes but isn't real authentication; the session cookie is.
