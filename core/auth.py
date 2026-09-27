import jwt
import hmac
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from core.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from core.db import db

_scrypt_slots = threading.BoundedSemaphore(2)  # each call takes ~16 MB and ~60 ms CPU; cap it under a login flood

def _scrypt(password, salt):
    with _scrypt_slots:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()

def get_password_hash(password):
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt)}"

def verify_password(plain_password, hashed_password):
    if hashed_password.startswith("scrypt$"):
        _, salt, digest = hashed_password.split("$")
        return hmac.compare_digest(_scrypt(plain_password, bytes.fromhex(salt)), digest)
    # Legacy SHA-256 + static salt; admin_login upgrades these to scrypt on the next successful login
    return hmac.compare_digest(hashlib.sha256((plain_password + "ztools_salt_123").encode()).hexdigest(), hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])  # PyJWT verifies exp
    except jwt.PyJWTError:
        return None

async def get_current_user(request: Request):
    token = request.cookies.get("admin_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    with db as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE username = ?", (username,)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="User no longer exists")
            
    return username
