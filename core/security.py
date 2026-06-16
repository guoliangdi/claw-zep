"""
安全工具：密码哈希、JWT 签发/校验、API Key 生成与校验。
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import settings
from core.exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# API Key 明文前缀（用于展示与识别）
API_KEY_LIVE_PREFIX = "cz_live_"


# ---------------- 密码 ----------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------- JWT ----------------
def _create_token(
    subject: str,
    extra: dict[str, Any],
    expires_delta: timedelta,
    token_type: str,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        **extra,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(
    user_id: str, email: str, system_role: str, tenant_id: Optional[str]
) -> str:
    return _create_token(
        subject=user_id,
        extra={"email": email, "system_role": system_role, "tenant_id": tenant_id},
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        extra={},
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        token_type="refresh",
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise UnauthorizedError("无效或过期的令牌", detail=str(exc))


# ---------------- API Key ----------------
def generate_api_key() -> tuple[str, str, str]:
    """
    生成 API Key。
    返回 (明文 key, key_hash, key_prefix)。明文仅创建时返回一次。
    """
    raw = secrets.token_urlsafe(32)
    plain = f"{API_KEY_LIVE_PREFIX}{raw}"
    key_hash = hash_api_key(plain)
    key_prefix = plain[: len(API_KEY_LIVE_PREFIX) + 6]
    return plain, key_hash, key_prefix


def hash_api_key(plain: str) -> str:
    """API Key 使用 SHA-256 哈希（高熵随机串，无需慢哈希）。"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def verify_api_key(plain: str, key_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(plain), key_hash)
