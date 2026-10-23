"""密码和会话相关的安全工具。

密码只保存不可逆的 scrypt 哈希；会话令牌本身不包含角色等权限信息，
权限每次从 SQLite 查询，因此管理员权限变更会立即生效。
"""

import base64
import hashlib
import hmac
import secrets


_SCHEME = "scrypt"
_N = 2**14
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    """生成带随机盐的 scrypt 密码哈希。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_N,
        r=_R,
        p=_P,
        dklen=_KEY_BYTES,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"{_SCHEME}${_N}${_R}${_P}${encode(salt)}${encode(derived)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """校验密码；格式异常时按校验失败处理，不把内部错误暴露给用户。"""
    try:
        scheme, n, r, p, encoded_salt, encoded_key = stored_hash.split("$", 5)
        if scheme != _SCHEME or (int(n), int(r), int(p)) != (_N, _R, _P):
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        if len(salt) != _SALT_BYTES or len(expected) != _KEY_BYTES:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_N,
            r=_R,
            p=_P,
            dklen=_KEY_BYTES,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return False


def create_session_token() -> str:
    """生成不携带业务信息的随机会话令牌。"""
    return secrets.token_urlsafe(32)
