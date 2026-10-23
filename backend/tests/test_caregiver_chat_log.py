"""Tests for GET /api/caregiver/chat-log (backend/routers/caregiver.py),
the caregiver-facing read of the agent_chat_logs table that
routers/agent.py's /chat endpoint writes to."""
import json

from backend import models
from backend.database import get_db


def _seed_turn(client, role, content, actions=None, user_id="demo-primary"):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    entry = models.AgentChatLog(
        user_id=user_id,
        role=role,
        content=content,
        actions_json=json.dumps(actions) if actions else None,
    )
    db.add(entry)
    db.commit()
    db.close()


def test_chat_log_empty_by_default(client):
    resp = client.get("/api/caregiver/chat-log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_chat_log_returns_persisted_turns_oldest_first(client):
    _seed_turn(client, "user", "What do I take next?")
    _seed_turn(
        client,
        "assistant",
        "Your next dose is Metformin at 9am.",
        actions=[{"type": "navigate", "target": "/schedule"}],
    )

    resp = client.get("/api/caregiver/chat-log")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "What do I take next?"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["actions"][0]["type"] == "navigate"
    assert rows[1]["actions"][0]["target"] == "/schedule"


def test_chat_log_ignores_other_users(client):
    _seed_turn(client, "user", "hello from someone else", user_id="some-other-user")
    resp = client.get("/api/caregiver/chat-log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_chat_log_respects_limit(client):
    for i in range(5):
        _seed_turn(client, "user", f"message {i}")
    resp = client.get("/api/caregiver/chat-log?limit=2")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # Most recent two, still oldest-first within that page.
    assert rows[0]["content"] == "message 3"
    assert rows[1]["content"] == "message 4"
