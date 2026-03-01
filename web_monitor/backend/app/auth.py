"""
Auth module - User login and JWT token management.
"""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# Use bcrypt directly to avoid passlib compatibility issues with bcrypt 5.0.0

# JWT config - must set JWT_SECRET_KEY env var in production
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# HTTP Bearer authentication
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password."""
    try:
        # Ensure password is bytes type
        password_bytes = plain_password.encode('utf-8')
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """Verify JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current user (dependency injection)."""
    token = credentials.credentials
    payload = verify_token(token)
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"username": username}


# Simple in-memory user storage (use database in production)
# Default dev account: admin / admin (change or configure via env vars in production)
_USERS_DB_INITIALIZED = False
USERS_DB = {}


def _init_default_users():
    """Initialize default users (lazy execution)."""
    global _USERS_DB_INITIALIZED, USERS_DB
    if _USERS_DB_INITIALIZED:
        return

    # Default password controlled by ADMIN_PASSWORD env var, "admin" when unset (dev only)
    default_pwd = os.getenv("ADMIN_PASSWORD", "admin")
    USERS_DB["admin"] = {
        "username": "admin",
        "hashed_password": get_password_hash(default_pwd),
        "role": "admin",
    }
    _USERS_DB_INITIALIZED = True


# Initialize default users
_init_default_users()


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate user."""
    user = USERS_DB.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_user(username: str, password: str, role: str = "user") -> dict:
    """Create new user."""
    if username in USERS_DB:
        raise ValueError("User already exists")
    USERS_DB[username] = {
        "username": username,
        "hashed_password": get_password_hash(password),
        "role": role,
    }
    return USERS_DB[username]
