import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # scrypt: memory-hard password hash in the standard library

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(actual, bytes.fromhex(digest_hex))  # constant-time compare


def create_access_token(user_id: int) -> str:
    # Real wall-clock time, not app.clock: PyJWT checks "exp" against the real time too.
    payload = {"sub": str(user_id), "exp": datetime.now(UTC) + TOKEN_TTL}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    error = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Could not validate credentials", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        user_id = int(jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error from None
    user = db.get(User, user_id)
    if user is None:
        raise error
    return user


def get_editor(user: User = Depends(get_current_user)) -> User:
    """Like get_current_user, but for routes that change data. The public demo login can only look."""
    if user.is_demo:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The demo account is read-only. Create your own business to try editing."
        )
    return user
