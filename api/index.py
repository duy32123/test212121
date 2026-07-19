"""
api/index.py — Vercel serverless entry point.

Import FastAPI app từ backend_py/app/server.py và expose là handler.
API key ĐỌC TỪ Environment Variables (Vercel dashboard), không đọc .env.
"""
import os
from pathlib import Path

os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("NLTK_DATA", "/tmp/nltk_data")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/.cache")

Path("/tmp/nltk_data").mkdir(parents=True, exist_ok=True)
Path("/tmp/.cache").mkdir(parents=True, exist_ok=True)

import sys
from pathlib import Path

# Thêm backend_py vào Python path để import app.server hoạt động
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend_py"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.server import app  # noqa: E402 — sau khi đặt sys.path

# Vercel dùng 'app' ASGI handler
handler = app
