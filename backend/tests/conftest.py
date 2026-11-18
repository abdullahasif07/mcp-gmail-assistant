"""Test config: provide dummy settings before any app module is imported.

`config.settings` validates env vars at import time, so these must be set
before the first `import config` / `import main` happens.
"""

import os
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_ENV = {
    "ENV": "dev",
    "OPENAI_API_KEY": "test-openai-key",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "http://localhost:8001/auth/callback",
    "FRONTEND_BASE_URL": "http://localhost:3000",
    "SESSION_JWT_SECRET": "test-session-secret-0123456789abcdef",
    "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "DB_PATH": str(Path(tempfile.mkdtemp()) / "test.db"),
    "API_KEY": "",
}
for key, value in _TEST_ENV.items():
    os.environ[key] = value
