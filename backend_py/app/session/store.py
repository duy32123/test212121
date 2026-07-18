"""
app/session/store.py — SessionStore interface + MemorySessionStore + SQLiteSessionStore.

Tách _sessions khỏi server.py để session có thể bền vững hơn qua restart.

Nguyên tắc:
- MemorySessionStore: dùng dict (giống hành vi cũ), tốt cho test và dev.
- SQLiteSessionStore: lưu state JSON, có TTL, không cần thư viện ngoài.
- SessionStore giao tiếp với ConversationState (frozen dataclass), convert
  sang/từ dict khi cần lưu/đọc.
- Validate state gửi từ frontend trước khi restore: chỉ chấp nhận các field
  đã biết trong ConversationState, không tin field lạ.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from app.conversation.state import ConversationState, create_conversation_state

logger = logging.getLogger("ai_product_advisor.session")

# Tập field hợp lệ trong ConversationState — dùng để validate state từ frontend
_VALID_STATE_FIELDS = frozenset(f.name for f in fields(ConversationState))

# TTL mặc định 7 ngày (giây)
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def validate_client_state(raw_state: dict | None) -> dict | None:
    """Kiểm tra state gửi từ frontend:
    - Loại bỏ field lạ (chỉ giữ field trong _VALID_STATE_FIELDS)
    - Kiểm tra kiểu dữ liệu cơ bản để không inject giá trị sai
    - Trả về None nếu state không dùng được
    """
    if not isinstance(raw_state, dict):
        return None

    cleaned: dict[str, Any] = {}
    for key, value in raw_state.items():
        if key not in _VALID_STATE_FIELDS:
            logger.debug("validate_client_state: bỏ field lạ '%s'", key)
            continue
        # Type guards đơn giản — không tin giá trị phức tạp
        if key == "session_id" and not isinstance(value, str):
            continue
        if key == "category" and value is not None and not isinstance(value, str):
            continue
        if key == "slots" and not isinstance(value, dict):
            continue
        if key == "asked_slots" and not isinstance(value, list):
            continue
        if key == "rejected_fields" and not isinstance(value, list):
            continue
        if key == "turn_count" and not isinstance(value, int):
            continue
        cleaned[key] = value

    return cleaned if cleaned else None


def state_to_dict(state: ConversationState) -> dict[str, Any]:
    return asdict(state)


def dict_to_state(data: dict[str, Any], session_id: str) -> ConversationState:
    """Khôi phục ConversationState từ dict đã lưu/gửi lên.
    session_id luôn được override bằng giá trị từ request.
    """
    data = {k: v for k, v in data.items() if k in _VALID_STATE_FIELDS}
    data["session_id"] = session_id
    try:
        return ConversationState(**data)
    except Exception:
        return create_conversation_state(session_id)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class SessionStore:
    """Interface chung cho mọi backend lưu session."""

    def get(self, session_id: str) -> ConversationState | None:
        raise NotImplementedError

    def save(self, session_id: str, state: ConversationState) -> None:
        raise NotImplementedError

    def reset(self, session_id: str) -> ConversationState:
        state = create_conversation_state(session_id)
        self.save(session_id, state)
        return state

    def get_or_create(self, session_id: str, client_state: dict | None = None) -> ConversationState:
        """Lấy session từ store; nếu không có thì thử khôi phục từ client_state
        (frontend gửi lên sau khi backend restart). Validate client_state trước.
        """
        existing = self.get(session_id)
        if existing is not None:
            return existing

        # Backend vừa restart — thử restore từ state hợp lệ mà frontend gửi
        if client_state:
            cleaned = validate_client_state(client_state)
            if cleaned and cleaned.get("session_id") == session_id:
                restored = dict_to_state(cleaned, session_id)
                self.save(session_id, restored)
                logger.info("session_restored_from_client session_id=%s turn=%s", session_id, restored.turn_count)
                return restored

        # Tạo mới hoàn toàn
        new_state = create_conversation_state(session_id)
        self.save(session_id, new_state)
        return new_state


# ---------------------------------------------------------------------------
# Memory store (cho test và dev không cần persistence)
# ---------------------------------------------------------------------------

class MemorySessionStore(SessionStore):
    """Lưu session trong dict RAM — nhanh, không bền vững qua restart."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def save(self, session_id: str, state: ConversationState) -> None:
        self._sessions[session_id] = state

    def reset(self, session_id: str) -> ConversationState:
        state = create_conversation_state(session_id)
        self._sessions[session_id] = state
        return state


# ---------------------------------------------------------------------------
# SQLite store (mặc định cho local — bền vững qua restart, không cần deps ngoài)
# ---------------------------------------------------------------------------

class SQLiteSessionStore(SessionStore):
    """Lưu session trong SQLite (stdlib sqlite3). State lưu dạng JSON text.
    TTL: session quá cũ sẽ bị coi như không tồn tại (không xoá ngay).
    """

    def __init__(self, db_path: str | Path, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._db_path = str(db_path)
        self._ttl = ttl_seconds
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get(self, session_id: str) -> ConversationState | None:
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT state_json, updated_at FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if row is None:
                return None
            state_json, updated_at = row
            if time.time() - updated_at > self._ttl:
                logger.debug("session_expired session_id=%s", session_id)
                return None
            data = json.loads(state_json)
            return dict_to_state(data, session_id)
        except Exception as exc:
            logger.warning("sqlite_session_get_error session_id=%s error=%s", session_id, exc)
            return None

    def save(self, session_id: str, state: ConversationState) -> None:
        try:
            state_json = json.dumps(state_to_dict(state), ensure_ascii=False)
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO sessions (session_id, state_json, updated_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(session_id) DO UPDATE SET
                         state_json = excluded.state_json,
                         updated_at = excluded.updated_at""",
                    (session_id, state_json, int(time.time())),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("sqlite_session_save_error session_id=%s error=%s", session_id, exc)

    def reset(self, session_id: str) -> ConversationState:
        state = create_conversation_state(session_id)
        self.save(session_id, state)
        return state
