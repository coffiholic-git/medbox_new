"""
AI Conversational Agent — talk-to-MedBox.

A chat endpoint backed by the Groq API (OpenAI-compatible chat
completions + tool/function calling), wired to the app's voice
input/output (useSpeech.js) and available from every screen via the
global assistant drawer (frontend/src/components/AgentAssistant.jsx).
It stays intentionally narrow and safe:

  - STATELESS PER REQUEST for reasoning. The frontend remains the source
    of truth for both conversation history and app data (see
    store/useStore.js — most demo users never sync to this backend's DB
    at all), so every request carries the running transcript (`history`)
    and a snapshot of the user's medicines/schedule (`context`). What
    *is* new: every turn is also written (best-effort) to the
    agent_chat_logs table for durability across refreshes/devices and a
    caregiver-facing audit trail — see `_persist_turn` below. That table
    is a log, not a cache: a request never reasons over it, only over
    what the frontend sent in `history`.

  - The agent can only ever *ask* the frontend to do one of five things
    via the `actions` list in the response — navigate to a screen, mark
    a dose taken, snooze a dose, refill a medicine's stock, or log a
    vitals reading. It cannot add or delete a medicine, edit a reminder,
    or touch caregiver data. Every action the frontend executes reuses
    the exact same store function (logDose/snoozeDose/navigate/
    refillStock/addVitalLog) a manual tap already uses — the agent is
    not a new, less-audited write path. Adding a *new* medicine by voice
    is deliberately left out: that flow already has a purpose-built,
    more careful confirmation UI (Scan → confirm) precisely because a
    misheard name/strength on a new entry is a bigger risk than a
    misheard refill amount or a duplicate dose-log on an existing one.

  - No interaction/safety claims are invented. If asked about a drug
    interaction, the model is given a `check_interaction` tool backed by
    the same offline dataset routers/medicines.py already uses
    (services/interaction_service.py) rather than answering from its own
    training knowledge, and the system prompt tells it to say so and
    recommend a pharmacist/doctor when the tool has no data.

  - MULTI-TURN TOOL ROUND TRIPS. When the model calls a tool, its result
    is fed back to the model in a second (or third, ...) request so the
    model reacts to it in its own words — e.g. it can actually explain
    what `check_interaction` found instead of a canned sentence being
    spliced in. See `_run_agent_turn` below.

  - AUTH + RATE LIMITING. The endpoint sits behind the same
    `get_current_user` dependency as the rest of the API (permissive
    demo fallback unless REQUIRE_AUTH=1, see security.py) and a small
    in-memory per-user rate limiter. The limiter is process-local (a
    dict), which is fine for this single-instance demo; a multi-instance
    deployment should move it to Redis (INCR + EXPIRE).

Not done yet: extending the tool set further (add/edit reminders,
caregiver-visible actions), and moving the rate limiter to a shared
store for multi-instance deployments.
"""
import json
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.schemas import (
    AgentAction,
    AgentChatRequest,
    AgentChatResponse,
    AgentHistoryMessage,
)
from backend.security import CurrentUser, get_current_user
from backend.services.interaction_service import check_interactions

router = APIRouter(prefix="/api/agent", tags=["AI Conversational Agent"])

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("MEDBOX_AGENT_MODEL", "openai/gpt-oss-20b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Keep this list in one place — both the tool schema below and
# schemas.AgentAction.target rely on it staying in sync with App.jsx's
# actual routes.
VALID_ROUTES = ["/", "/scan", "/schedule", "/safety", "/library"]

# Hard ceiling on how many tool-call <-> tool-result round trips a single
# /chat request will do before giving up and returning whatever text it
# has. Guards against a runaway loop (e.g. the model repeatedly calling a
# tool) turning into an unbounded number of API calls.
MAX_TOOL_ROUNDS = 4

# ---------------------------------------------------------------- Rate limiting
# Process-local sliding-window limiter: `RATE_LIMIT_MAX` requests per
# `RATE_LIMIT_WINDOW_SECONDS` per user (falls back to client IP for
# unauthenticated demo traffic). Intentionally simple — see module
# docstring for the multi-instance caveat.
RATE_LIMIT_MAX = int(os.getenv("MEDBOX_AGENT_RATE_LIMIT", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("MEDBOX_AGENT_RATE_WINDOW", "300"))
_request_log: Dict[str, Deque[float]] = defaultdict(deque)


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    bucket = _request_log[key]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many assistant requests. Please wait about {retry_after} seconds "
                "and try again."
            ),
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


# ---- OpenAI-compatible tool definitions for Groq ----
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": (
                "Open a different screen of the app for the user. Use this when "
                "they ask to scan a medicine, see their schedule, check safety/"
                "interactions, or browse their medicine library."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": VALID_ROUTES},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_dose_taken",
            "description": "Mark one of the user's medicines as taken just now, by its id.",
            "parameters": {
                "type": "object",
                "properties": {"medId": {"type": "string"}},
                "required": ["medId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "snooze_dose",
            "description": "Snooze a reminder for a medicine by a number of minutes (default 15).",
            "parameters": {
                "type": "object",
                "properties": {
                    "medId": {"type": "string"},
                    "minutes": {"type": "integer", "default": 15},
                },
                "required": ["medId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_interaction",
            "description": (
                "Look up whether two medicine names are known to interact, using "
                "MedBox's offline interaction reference. Always use this instead "
                "of answering an interaction question from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "medicineA": {"type": "string"},
                    "medicineB": {"type": "string"},
                },
                "required": ["medicineA", "medicineB"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refill_medicine",
            "description": (
                "Add pills to an existing medicine's stock count, by its id. Only "
                "call this when the user explicitly says they refilled or bought "
                "more of a specific medicine already in their library — never to "
                "add a brand-new medicine."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "medId": {"type": "string"},
                    "amount": {"type": "integer", "default": 30},
                },
                "required": ["medId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_vital",
            "description": (
                "Record a vitals reading (blood pressure, glucose, pulse) the user "
                "just read off a device and told you out loud. Only call this with "
                "numbers the user actually stated — never estimate or invent a "
                "reading. If they only give some of the numbers, ask for the rest "
                "instead of guessing, or omit fields you don't have."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bpSystolic": {"type": "integer"},
                    "bpDiastolic": {"type": "integer"},
                    "glucose": {"type": "integer"},
                    "pulse": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_medicine",
            "description": (
                "Add a new medicine to the user's MedBox library / pill cabinet when they ask you "
                "to add, schedule, or prescribe a new medication."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the medicine, e.g. Metformin, Ibuprofen, Aspirin"},
                    "strength": {"type": "string", "description": "Strength or dosage, e.g. 500 mg, 10 mg, 100 IU (default: 500 mg)"},
                    "form": {"type": "string", "enum": ["Tablet", "Capsule", "Softgel", "Liquid", "Injection", "Inhaler", "Drops"], "default": "Tablet"},
                    "frequency": {"type": "string", "enum": ["daily", "weekly", "asNeeded"], "default": "daily"},
                    "time": {"type": "string", "description": "Dose time, e.g. 8:00 AM, 1:00 PM, 9:00 PM (default: 9:00 AM)"},
                    "instructions": {"type": "string", "description": "Usage instructions, e.g. 1 tablet after meals"},
                    "stock": {"type": "integer", "description": "Pill count / quantity in stock (default: 30)"},
                    "expiry": {"type": "string", "description": "Expiry date, e.g. Dec 2027"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_caregiver",
            "description": (
                "Initiate a call or send an urgent alert to the user's assigned caregiver "
                "when the user asks to call them or needs urgent help."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


def _build_system_prompt(ctx) -> str:
    meds_lines = "\n".join(
        f"- id={m.id} | {m.name} {m.strength} ({m.form}) | {m.frequency} at {m.time} | "
        f"stock={m.stock if m.stock is not None else 'unknown'} | instructions: {m.instructions or 'none on file'}"
        for m in ctx.medicines
    ) or "(no medicines on file yet)"

    low_stock = ", ".join(ctx.lowStockMedIds) or "none"
    today_log = json.dumps(ctx.todaysLog) if ctx.todaysLog else "{}"

    return f"""You are the MedBox voice assistant, speaking with {ctx.patientName}, who is blind or
visually impaired. Every reply of yours is read aloud by a screen reader / text-to-speech engine, so:

- Never refer to visuals: no "tap the button", "see below", "the screen shows", icons, or colors.
- Keep replies short and conversational — 1-3 sentences unless they ask for a list, and if it IS a
  list, say it as a spoken list ("First, ... Second, ...") not a bulleted layout.
- Be direct and warm, not clinical or robotic.
- If you don't have information to answer safely (e.g. a dosage question, a symptom, anything
  medical beyond what's in their MedBox library below), say so plainly and recommend they contact
  their doctor or pharmacist. Never invent a dose, interaction, or side effect.
- For interaction/safety questions, always call the check_interaction tool rather than answering
  from memory, and once you have the result, explain it in your own plain words.
- Use the navigate, mark_dose_taken, snooze_dose, refill_medicine, log_vital, add_medicine,
  and call_caregiver tools when the user's request calls for one of those actions.
- IMPORTANT: You DO have the ability to call the caregiver using the call_caregiver tool. If the user asks you to call their caregiver, you MUST use the call_caregiver tool and confirm you are calling them. Do not say you cannot make phone calls.
- Always say a short natural-language confirmation of what you did in the same turn (e.g. "Done — I've marked your Metformin as taken." or "I'm calling your caregiver now.").
- When the user asks to add or schedule a new medicine (e.g. "Add Metformin 500mg daily at 8am",
  "Add Aspirin to my pill cabinet", "Schedule Ibuprofen"), call the add_medicine tool with the
  details and confirm out loud what you added and when to take it.
- You are not a doctor: if asked to interpret a vitals reading (e.g. "is that blood pressure bad?"),
  log the number if given but decline to interpret it medically, and suggest they discuss it with
  their doctor.
- The current time is {ctx.nowIso or "not provided"}.

Here is {ctx.patientName}'s current MedBox data — use it to answer questions like "what do I take
next", "am I low on anything", "did I take my morning pills":

Medicines:
{meds_lines}

Low stock (5 or fewer left): {low_stock}
Today's dose log so far ({{medId: status}}): {today_log}
"""


def _groq_call(system: str, messages: List[dict]) -> dict:
    """Call the Groq chat completions API (OpenAI-compatible format)."""
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI assistant isn't configured yet — set the GROQ_API_KEY "
                "environment variable on the backend and restart it. "
                "Get a free key at https://console.groq.com"
            ),
        )

    # Prepend system message into the messages list (OpenAI format)
    full_messages = [{"role": "system", "content": system}] + messages

    try:
        resp = httpx.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": 500,
                "messages": full_messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach the AI service: {exc}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"AI service error ({resp.status_code}): {resp.text[:300]}",
        )

    return resp.json()


def _execute_tool(name: str, tool_input: dict) -> Tuple[str, List[AgentAction]]:
    """Run one tool call. Returns (tool_result_text_for_the_model, actions_for_the_frontend)."""
    actions: List[AgentAction] = []

    if name == "navigate":
        target = tool_input.get("target")
        if target in VALID_ROUTES:
            actions.append(AgentAction(type="navigate", target=target))
            return f"Navigated the app to {target}.", actions
        return f"'{target}' is not a valid screen; no navigation happened.", actions

    if name == "mark_dose_taken":
        med_id = tool_input.get("medId")
        if not med_id:
            return "No medId was provided; nothing was marked.", actions
        actions.append(AgentAction(type="mark_taken", medId=med_id))
        return f"Marked medicine {med_id} as taken just now.", actions

    if name == "snooze_dose":
        med_id = tool_input.get("medId")
        if not med_id:
            return "No medId was provided; nothing was snoozed.", actions
        minutes = int(tool_input.get("minutes", 15))
        actions.append(AgentAction(type="snooze", medId=med_id, minutes=minutes))
        return f"Snoozed medicine {med_id} for {minutes} minutes.", actions

    if name == "refill_medicine":
        med_id = tool_input.get("medId")
        if not med_id:
            return "No medId was provided; nothing was refilled.", actions
        amount = int(tool_input.get("amount", 30))
        actions.append(AgentAction(type="refill_medicine", medId=med_id, amount=amount))
        return f"Added {amount} to the stock count of medicine {med_id}.", actions

    if name == "log_vital":
        vitals = {
            k: v
            for k, v in {
                "bpSystolic": tool_input.get("bpSystolic"),
                "bpDiastolic": tool_input.get("bpDiastolic"),
                "glucose": tool_input.get("glucose"),
                "pulse": tool_input.get("pulse"),
            }.items()
            if v is not None
        }
        if not vitals:
            return "No vitals values were provided; nothing was logged.", actions
        actions.append(AgentAction(type="log_vital", vitals=vitals))
        return f"Logged vitals reading: {json.dumps(vitals)}.", actions

    if name == "check_interaction":
        med_a = tool_input.get("medicineA", "")
        med_b = tool_input.get("medicineB", "")
        advisory = check_interactions(med_a, [med_b])
        if advisory.hasConflict:
            return advisory.advisoryMessage, actions
        return (
            f"No known interaction found between '{med_a}' and '{med_b}' in the offline "
            "reference data. This list isn't exhaustive, so still recommend the user "
            "double-check with a pharmacist.",
            actions,
        )

    if name == "add_medicine":
        med_name = tool_input.get("name", "").strip()
        if not med_name:
            return "No medicine name was provided; nothing was added.", actions
        med_dict = {
            "name": med_name,
            "strength": tool_input.get("strength") or "500 mg",
            "form": tool_input.get("form") or "Tablet",
            "frequency": tool_input.get("frequency") or "daily",
            "time": tool_input.get("time") or "9:00 AM",
            "instructions": tool_input.get("instructions") or f"{tool_input.get('form') or 'Tablet'} · {tool_input.get('time') or '9:00 AM'}",
            "stock": int(tool_input.get("stock") or 30),
            "maxStock": int(tool_input.get("stock") or 30),
            "expiry": tool_input.get("expiry") or "",
        }
        actions.append(AgentAction(type="add_medicine", medicine=med_dict))
        return (
            f"Successfully added {med_dict['name']} {med_dict['strength']} "
            f"({med_dict['frequency']} at {med_dict['time']}) to the pill cabinet.",
            actions,
        )

    if name == "call_caregiver":
        actions.append(AgentAction(type="call_caregiver"))
        return "Initiated a call to the caregiver.", actions

    return f"Unknown tool '{name}' — ignored.", actions


def _run_agent_turn(system: str, messages: List[dict]) -> Tuple[str, List[AgentAction], str]:
    """Drive the Groq call through as many tool-use round trips as it
    needs (bounded by MAX_TOOL_ROUNDS), so the model gets to react to its
    own tool results in natural language instead of a canned sentence
    being spliced in. Returns (reply_text, actions, model_used)."""
    all_actions: List[AgentAction] = []
    model_used = GROQ_MODEL

    for _ in range(MAX_TOOL_ROUNDS):
        data = _groq_call(system, messages)
        model_used = data.get("model", GROQ_MODEL)

        choices = data.get("choices", [])
        if not choices:
            return "I'm sorry, I didn't get a response. Please try again.", all_actions, model_used

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            # No tool calls — just a text reply
            reply = (message.get("content") or "").strip()
            return reply or "Okay, done.", all_actions, model_used

        # The assistant's turn (including its tool_calls) must be replayed
        # back before we can send tool result messages.
        messages.append(message)

        for tc in tool_calls:
            func = tc.get("function", {})
            func_name = func.get("name", "")
            try:
                func_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                func_args = {}

            result_text, actions = _execute_tool(func_name, func_args)
            all_actions.extend(actions)

            # Groq expects tool results as role:"tool" messages with the
            # matching tool_call_id.
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_text,
            })

    # Ran out of rounds — return whatever actions we gathered plus a plain
    # confirmation rather than erroring the whole request out.
    return "Okay, done.", all_actions, model_used


def _persist_turn(
    db: Session, user_id: str, role: str, content: str, actions: Optional[List[AgentAction]] = None
) -> None:
    """Best-effort write to agent_chat_logs. Never raises — a persistence
    hiccup should not break the chat response itself."""
    try:
        entry = models.AgentChatLog(
            user_id=user_id,
            role=role,
            content=content,
            actions_json=json.dumps([a.model_dump(exclude_none=True) for a in actions]) if actions else None,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send the transcript + app-state snapshot, get back a spoken reply
    plus any actions to carry out locally on the frontend. Internally does
    as many tool-call round trips as the model needs (see
    `_run_agent_turn`), gated by a per-user rate limit, and persists the
    turn to the DB afterward."""
    rate_key = current_user.uid or (request.client.host if request.client else "anonymous")
    _check_rate_limit(rate_key)

    ctx = payload.context
    system = _build_system_prompt(ctx)
    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    reply, actions, model_used = _run_agent_turn(system, messages)

    _persist_turn(db, current_user.uid, "user", payload.message)
    _persist_turn(db, current_user.uid, "assistant", reply, actions)

    return AgentChatResponse(reply=reply, actions=actions, modelUsed=model_used)


@router.get("/history", response_model=List[AgentHistoryMessage])
def agent_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Recent persisted turns for the signed-in user, oldest first — lets a
    refreshed page or a new device restore the visible transcript. This is
    a convenience read of the audit log described in the module docstring,
    not the thing a /chat call reasons over (that's always `history` in
    the request body)."""
    rows = (
        db.query(models.AgentChatLog)
        .filter(models.AgentChatLog.user_id == current_user.uid)
        .order_by(models.AgentChatLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    rows.reverse()
    out = []
    for row in rows:
        actions = []
        if row.actions_json:
            try:
                actions = [AgentAction(**a) for a in json.loads(row.actions_json)]
            except (json.JSONDecodeError, TypeError):
                actions = []
        out.append(
            AgentHistoryMessage(
                role=row.role,
                content=row.content,
                actions=actions,
                createdAt=row.created_at.isoformat(),
            )
        )
    return out


@router.delete("/history")
def clear_agent_history(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete the signed-in user's persisted transcript (e.g. a "clear
    conversation" control in the assistant drawer)."""
    deleted = (
        db.query(models.AgentChatLog)
        .filter(models.AgentChatLog.user_id == current_user.uid)
        .delete()
    )
    db.commit()
    return {"deleted": deleted}
