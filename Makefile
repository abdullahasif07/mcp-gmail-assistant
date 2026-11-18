# Mailmind - local development
#
#   make setup   one-time: install everything, create backend/.env
#   make run     start backend (:8001) + frontend (:3000); Ctrl+C stops both
#
# Run `make help` for the full list.

VENV    := backend/.venv
PY      := $(VENV)/bin/python
ENVFILE := backend/.env

.DEFAULT_GOAL := help
.PHONY: help setup run backend frontend test lint

help:
	@echo "make setup     Install backend, frontend and MCP server deps; create backend/.env"
	@echo "make run       Start backend + frontend together (Ctrl+C stops both)"
	@echo "make backend   Start only the backend   (http://localhost:8001)"
	@echo "make frontend  Start only the frontend  (http://localhost:3000)"
	@echo "make test      Run backend tests"
	@echo "make lint      Lint backend (ruff) and frontend (eslint + tsc)"

# ── Setup ─────────────────────────────────────────────────────────────────

setup: $(PY) $(ENVFILE)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements.txt -r backend/requirements-dev.txt
	cd mcp-server && npm install
	cd frontend && npm install
	@echo ""
	@echo "Setup done. Next:"
	@echo "  1. Put your OPENAI_API_KEY in backend/.env"
	@echo "  2. make run, then open http://localhost:3000"

$(PY):
	python3 -m venv $(VENV)

# Copy the example and fill in freshly generated secrets. Never overwrites
# an existing backend/.env.
$(ENVFILE): | $(PY)
	$(PY) -m pip install -q cryptography
	@$(PY) -c "import re, secrets; from cryptography.fernet import Fernet; \
	s = open('backend/.env.example').read(); \
	s = re.sub(r'(?m)^SESSION_JWT_SECRET=.*$$', 'SESSION_JWT_SECRET=' + secrets.token_urlsafe(48), s); \
	s = re.sub(r'(?m)^TOKEN_ENCRYPTION_KEY=.*$$', 'TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode(), s); \
	open('$(ENVFILE)', 'w').write(s)"
	@echo "Created $(ENVFILE) with generated secrets."

# ── Run ───────────────────────────────────────────────────────────────────

# Both servers run as children of one shell; Ctrl+C (or either crashing and
# you hitting Ctrl+C) stops the whole group.
run: _check
	@echo "Backend  -> http://localhost:8001  (API docs: /docs)"
	@echo "Frontend -> http://localhost:3000"
	@trap 'kill 0' INT TERM; \
	(cd backend && .venv/bin/python -m uvicorn main:app --reload --port 8001) & \
	(cd frontend && npm run dev -- --port 3000) & \
	wait

backend: _check
	cd backend && .venv/bin/python -m uvicorn main:app --reload --port 8001

frontend:
	cd frontend && npm run dev -- --port 3000

# Friendly errors instead of stack traces when setup hasn't been done.
_check:
	@test -x $(PY) || { echo "No Python venv found. Run: make setup"; exit 1; }
	@test -f $(ENVFILE) || { echo "No backend/.env found. Run: make setup"; exit 1; }
	@test -d mcp-server/node_modules || { echo "MCP server deps missing. Run: make setup"; exit 1; }
	@test -d frontend/node_modules || { echo "Frontend deps missing. Run: make setup"; exit 1; }

# ── Quality ───────────────────────────────────────────────────────────────

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint && npx tsc --noEmit
