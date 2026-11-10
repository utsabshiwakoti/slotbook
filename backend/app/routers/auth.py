from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Business, User
from ..security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.Me, status_code=201)
def register(payload: schemas.Register, db: Session = Depends(get_db)):
    """Sign up a business owner and create their business in one step."""
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")
    if db.scalar(select(Business.id).where(Business.slug == payload.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That booking URL is taken; try another")
    business = Business(name=payload.business_name.strip(), slug=payload.slug, timezone=payload.timezone)
    user = User(email=email, name=payload.name.strip(), password_hash=hash_password(payload.password), business=business)
    db.add(user)
    db.commit()
    return user


@router.post("/token", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow (form fields `username` = email, `password`), so /docs' Authorize button works."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    # One message for both cases, so the API doesn't reveal which emails have accounts.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    return schemas.Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=schemas.Me)
def me(user: User = Depends(get_current_user)):
    return user
