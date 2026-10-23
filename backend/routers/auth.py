"""FR14 — Authentication & security. Register/login with JWT, role separation."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import secrets

from backend import models
from backend.database import get_db
from backend.schemas import GoogleAuthRequest, LoginRequest, RegisterRequest, TokenResponse, UserProfileResponse
from backend.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication & Security (FR14)"])


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")
    if payload.role not in ("primary_user", "caregiver"):
        raise HTTPException(status_code=400, detail="role must be 'primary_user' or 'caregiver'.")

    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = models.User(
        email=payload.email,
        password_hash=password_hash,
        display_name=payload.name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role, "displayName": user.display_name})
    return TokenResponse(access_token=token, uid=user.id, displayName=user.display_name, email=user.email, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role, "displayName": user.display_name})
    return TokenResponse(access_token=token, uid=user.id, displayName=user.display_name, email=user.email, role=user.role)


@router.post("/google", response_model=TokenResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Exchange a completed Firebase Google sign-in for a MedBox JWT.

    The frontend calls Firebase's signInWithPopup directly (that's what
    verifies the Google identity), then sends us the resulting profile.
    We find-or-create the matching local user by email and issue our own
    JWT so the session behaves exactly like an email/password login —
    without this bridge, App.jsx has no token to persist and immediately
    signs the user back out after a Google login.
    """
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user:
        # No password was ever set for a Google-only account; store a
        # random, never-shared hash so the column stays non-null and the
        # account simply can't log in via the email/password form.
        user = models.User(
            email=payload.email,
            password_hash=hash_password(secrets.token_urlsafe(32)[:64]),
            display_name=payload.name or payload.email.split("@")[0],
            role="primary_user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role, "displayName": user.display_name})
    return TokenResponse(access_token=token, uid=user.id, displayName=user.display_name, email=user.email, role=user.role)


@router.get("/me", response_model=UserProfileResponse)
def me(current_user=Depends(get_current_user)):
    return UserProfileResponse(
        uid=current_user.uid, email=current_user.email, displayName=current_user.display_name, role=current_user.role
    )
