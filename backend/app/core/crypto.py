"""数据源密码加密。

主密钥来自 EI_SECRET_KEY（32 字节 base64）。用 HKDF 派生两把互不复用的子密钥：
一把用于 AES-GCM 加密，一把用于签名。密文格式：nonce(12) + ciphertext + tag。
"""

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

_NONCE_LEN = 12


class SecretKeyMissing(RuntimeError):
    pass


def _master_key() -> bytes:
    raw = get_settings().secret_key
    if not raw:
        raise SecretKeyMissing("EI_SECRET_KEY 未配置，拒绝启动")
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise SecretKeyMissing("EI_SECRET_KEY 不是合法的 base64") from exc
    if len(key) != 32:
        raise SecretKeyMissing("EI_SECRET_KEY 必须是 32 字节的 base64")
    return key


def ensure_keys() -> None:
    """启动时调用：主密钥缺失或长度不对时直接失败，而不是等到首次加解密才报错。"""
    _master_key()


def derive_key(info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=info
    ).derive(_master_key())


def encrypt(plaintext: str) -> str:
    key = derive_key(b"easyimporter-datasource-encryption")
    nonce = os.urandom(_NONCE_LEN)
    token = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + token).decode()


def decrypt(ciphertext: str) -> str:
    key = derive_key(b"easyimporter-datasource-encryption")
    raw = base64.b64decode(ciphertext)
    nonce, token = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, token, None).decode()


def signing_key() -> bytes:
    return derive_key(b"easyimporter-signing")
