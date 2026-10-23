"""Seed data — mirrors the frontend's src/data/seed.js so a fresh
backend and a fresh frontend agree on what the demo library looks like."""
from datetime import datetime, timedelta

from backend import models
from backend.security import hash_password


def seed_if_empty(db):
    if db.query(models.User).count() == 0:
        db.add_all(
            [
                models.User(
                    id="u-maya-001",
                    email="maya.lin@medbox.health",
                    password_hash=hash_password("securePass123"),
                    display_name="Maya Lin",
                    role="primary_user",
                ),
                models.User(
                    id="u-caregiver-002",
                    email="dr.jenkins@medbox.health",
                    password_hash=hash_password("caregiverPass123"),
                    display_name="Dr. Sarah Jenkins",
                    role="caregiver",
                ),
            ]
        )
        db.commit()

    if db.query(models.Medicine).count() == 0:
        meds = [
            models.Medicine(
                id="m-paracetamol",
                name="Paracetamol",
                strength="500 mg",
                form="Tablet",
                frequency="daily",
                time="8:00 PM",
                instructions="1 tablet · after dinner",
                color="mint",
                expiry="Nov 2027",
                stock=4,
                max_stock=30,
                added_at="2026-06-02",
            ),
            models.Medicine(
                id="m-vitamind",
                name="Vitamin D3",
                strength="1000 IU",
                form="Softgel",
                frequency="weekly",
                time="9:00 AM",
                instructions="1 softgel · Sundays, with breakfast",
                color="lime",
                expiry="Jan 2028",
                stock=18,
                max_stock=60,
                added_at="2026-05-14",
            ),
            models.Medicine(
                id="m-amlodipine",
                name="Amlodipine",
                strength="5 mg",
                form="Tablet",
                frequency="daily",
                time="9:00 AM",
                instructions="1 tablet · every morning",
                color="coral",
                expiry="Mar 2027",
                stock=2,
                max_stock=30,
                added_at="2026-04-28",
            ),
        ]
        db.add_all(meds)
        db.commit()

        db.add_all(
            [
                models.Reminder(
                    id="rem-1",
                    med_id="m-paracetamol",
                    med_name="Paracetamol",
                    dosage="500 mg",
                    quantity="1 tablet",
                    time="8:00 PM",
                    frequency="daily",
                    is_active=True,
                ),
                models.Reminder(
                    id="rem-2",
                    med_id="m-amlodipine",
                    med_name="Amlodipine",
                    dosage="5 mg",
                    quantity="1 tablet",
                    time="9:00 AM",
                    frequency="daily",
                    is_active=True,
                ),
            ]
        )
        db.commit()

    if db.query(models.Vital).count() == 0:
        for i in range(6, -1, -1):
            d = datetime.now() - timedelta(days=i)
            db.add(
                models.Vital(
                    date=d.strftime("%a"),
                    bp_systolic=120 + (i % 5),
                    bp_diastolic=80 + (i % 3),
                    glucose=95 + (i % 7),
                    pulse=72 + (i % 4),
                )
            )
        db.commit()
