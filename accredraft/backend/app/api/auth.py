"""Authentication endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    get_password_hash, verify_password, create_access_token, get_current_user
)
from app.models.models import User, Organization, AuditLog
from app.schemas.schemas import UserCreate, UserLogin, Token, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(data: UserCreate, db: Session = Depends(get_db)):
    # Check if email exists
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Get or create organization
    org = None
    if data.org_name:
        org = db.query(Organization).filter(Organization.name == data.org_name).first()
        if not org:
            org = Organization(name=data.org_name)
            db.add(org)
            db.flush()
    
    # Create user
    user = User(
        email=data.email,
        name=data.name,
        password_hash=get_password_hash(data.password),
        role="editor",
        org_id=org.id if org else None,
    )
    db.add(user)
    db.flush()
    
    # Create audit log
    audit = AuditLog(
        user_id=user.id,
        action="user.register",
        after={"email": user.email, "role": user.role},
    )
    db.add(audit)
    db.commit()
    db.refresh(user)
    
    return user


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is deactivated"
        )
    
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user