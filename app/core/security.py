from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
import bcrypt
from app.core.config import settings

ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(
    subject: Union[str, Any],
    session_id: str,
    client_type: str,
    roles: list,
    allowed_apps: list,
    expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "session_id": session_id,
        "client_type": client_type,
        "roles": roles,
        "allowed_apps": allowed_apps
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(
    subject: Union[str, Any],
    session_id: str,
    expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Default refresh token expiry is 7 days
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "session_id": session_id,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_qris_ktp(qr_string: str) -> str:
    """
    Decodes the secure symmetric XOR obfuscated QRIS string to retrieve the raw NIK.
    """
    prefix = "SUBSIDIA-QRIS:KTP:"
    if not qr_string.startswith(prefix):
        raise ValueError("Invalid QRIS code format or prefix mismatch")
        
    import base64
    base64_data = qr_string[len(prefix):]
    encrypted_bytes = base64.b64decode(base64_data)
    
    key_bytes = settings.QRIS_SECRET_KEY.encode('utf-8')
    decrypted_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted_bytes)])
    return decrypted_bytes.decode('utf-8')
