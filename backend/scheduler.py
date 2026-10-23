"""
Layer 3 (Async Processing) — reminder scheduling, per Section 9:
"Celery Beat (or APScheduler) runs on a schedule, checks for due
reminders, and pushes a notification to the client over a WebSocket
connection the instant it's due — not by the client polling the
server." This uses APScheduler (the doc's explicitly-named
lighter-weight alternative) so the whole backend runs as one process
for the demo, with Celery+Redis documented in docker-compose.yml as
the production upgrade path.

Also implements 6.4's missed-dose follow-up: if a fired reminder
isn't acknowledged within a window, it repeats once and flags the
caregiver dashboard (via a CaregiverAlert row + a CAREGIVER_ALERT push).
"""
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend import models
from backend.database import SessionLocal
from backend.services.notifications import ws_manager

CHECK_INTERVAL_SECONDS = 30
MISSED_FOLLOW_UP_MINUTES = 15


def _time_label(dt: datetime) -> str:
    """Cross-platform '8:00 PM' formatting, matching how the frontend
    stores reminder times (strftime's no-leading-zero flag isn't
    portable across platforms, so this strips it manually)."""
    return dt.strftime("%I:%M %p").lstrip("0")


async def _check_due_reminders():
    db = SessionLocal()
    try:
        now = datetime.now()
        now_label = _time_label(now)

        reminders = db.query(models.Reminder).filter(models.Reminder.is_active == True).all()  # noqa: E712
        for rem in reminders:
            if rem.time != now_label:
                continue

            already_fired_this_minute = (
                rem.last_fired_at is not None and (now - rem.last_fired_at) < timedelta(minutes=1)
            )
            if already_fired_this_minute:
                continue

            rem.last_fired_at = now
            rem.acknowledged = False
            rem.missed_follow_up_sent = False
            db.commit()

            await ws_manager.broadcast(
                {
                    "type": "REMINDER_DUE",
                    "reminderId": rem.id,
                    "medId": rem.med_id,
                    "medName": rem.med_name,
                    "dosage": rem.dosage,
                    "quantity": rem.quantity,
                    "spokenResponse": (
                        f"Reminder: It is time to take your {rem.med_name} {rem.dosage}. "
                        f"Your scheduled dose is {rem.quantity}."
                    ),
                }
            )

        # 6.4 — follow-up + caregiver flag for anything unacknowledged past the window.
        pending = db.query(models.Reminder).filter(
            models.Reminder.last_fired_at.isnot(None),
            models.Reminder.acknowledged == False,  # noqa: E712
            models.Reminder.missed_follow_up_sent == False,  # noqa: E712
        ).all()
        for rem in pending:
            if now - rem.last_fired_at < timedelta(minutes=MISSED_FOLLOW_UP_MINUTES):
                continue

            rem.missed_follow_up_sent = True
            db.add(
                models.DoseLog(date_key=now.strftime("%Y-%m-%d"), med_id=rem.med_id, status="missed")
            )
            db.add(
                models.CaregiverAlert(
                    patient_name="Maya Lin",
                    med_id=rem.med_id,
                    message=f"Missed dose: {rem.med_name} scheduled for {rem.time} was not acknowledged.",
                    kind="missed_dose",
                )
            )
            db.commit()

            await ws_manager.broadcast(
                {
                    "type": "REMINDER_FOLLOW_UP",
                    "reminderId": rem.id,
                    "medName": rem.med_name,
                    "spokenResponse": f"Reminder: you still haven't taken your {rem.med_name}. Please take it now if you can.",
                }
            )
            await ws_manager.broadcast(
                {"type": "CAREGIVER_ALERT", "message": f"Missed dose: {rem.med_name} at {rem.time}.", "patientName": "Maya Lin"}
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
#
# AsyncIOScheduler binds itself to whatever asyncio event loop is running
# the first time start() is called, and caches that loop internally — it
# does not re-read the running loop on later start() calls. In production
# that's fine: start_scheduler()/shutdown_scheduler() each run exactly once
# for the life of the process (see main.py's lifespan).
#
# Under pytest, though, every `with TestClient(app) as client:` block (see
# tests/conftest.py's `client` fixture, which is function-scoped — a fresh
# TestClient per test) drives FastAPI's lifespan on its own event loop and
# closes that loop when the block exits. A single module-level
# AsyncIOScheduler instance reused across many TestClient instances keeps
# the *first* test's now-closed event loop cached, so the next test's
# scheduler.start() tries to schedule its wakeup callback on a dead loop —
# raising "RuntimeError: Event loop is closed".
#
# Fix: don't keep one global scheduler alive across restarts. Build a new
# AsyncIOScheduler every time start_scheduler() runs, so it always binds to
# whichever event loop is actually running right now, and drop the
# reference entirely on shutdown so nothing keeps pointing at a dead loop.
# ---------------------------------------------------------------------------
_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        # Defensive: guards against start_scheduler() being called twice
        # for the same lifespan without an intervening shutdown.
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _check_due_reminders,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id="reminder_check",
        replace_existing=True,
    )
    _scheduler.start()


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
