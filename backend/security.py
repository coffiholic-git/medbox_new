"""
FR14 — Authentication & role separation.

JWT via python-jose-style PyJWT, bcrypt password hashing via passlib.
`get_current_user` / `require_role` are FastAPI dependencies the other
routers use to gate primary-user vs. caregiver actions.

Kept permissive by design for two reasons:
1. The shipped frontend (src/config/firebase.js) authenticates end users
   with Firebase directly and never calls /api/auth — these endpoints
   exist to satisfy FR14 / the caregiver dashboard / Postman-level API
   contract described in Section 15, not to gate the current UI.
2. Endpoints that DO enforce auth (caregiver-only routes) fall back to
   an "unauthenticated demo caregiver" identity rather than a hard 401,
   so `/docs` and the dashboard keep working without a login step —
   flip REQUIRE_AUTH=1 to make the 401 real for a production deploy.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("SECRET_KEY", "MEDBOX_SECRET_KEY_JWT_AUTHENTICATION_ACCESSIBLE_APP")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "0") == "1"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    # bcrypt's input limit is part of its security model. Reject rather than
    # silently truncating, which could make two passwords authenticate alike.
    if len(password_bytes) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        return False
    try:
        # Standard bcrypt hashes made by passlib and bcrypt share this format.
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


class CurrentUser:
    def __init__(self, uid: str, email: str, role: str, display_name: str = ""):
        self.uid = uid
        self.email = email
        self.role = role
        self.display_name = display_name


DEMO_USER = CurrentUser(uid="demo-primary", email="demo@medbox.health", role="primary_user", display_name="Demo User")
DEMO_CAREGIVER = CurrentUser(uid="demo-caregiver", email="demo.caregiver@medbox.health", role="caregiver", display_name="Demo Caregiver")


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> CurrentUser:
    if not token:
        if REQUIRE_AUTH:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
        return DEMO_USER

    payload = decode_token(token)
    if not payload:
        if REQUIRE_AUTH:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
        return DEMO_USER

    return CurrentUser(
        uid=payload.get("sub", "unknown"),
        email=payload.get("email", ""),
        role=payload.get("role", "primary_user"),
        display_name=payload.get("displayName", ""),
    )


def require_role(*roles: str):
    """Dependency factory: `Depends(require_role("caregiver"))`."""

    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            if REQUIRE_AUTH:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This action requires one of roles {roles}, not '{user.role}'.",
                )
            # Demo mode: coerce so the dashboard is browsable without a login flow.
            return DEMO_CAREGIVER if "caregiver" in roles else DEMO_USER
        return user

    return _checker
