"""HMAC-SHA256 签名：X-Sign = HMAC(body + timestamp, 机器码派生密钥)"""
import hashlib
import hmac
import time

from .crypto import derive_key


def make_sign(body: str, ts: int) -> str:
    key = derive_key()
    msg = f"{body}{ts}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def sign_headers(body: str, ts: int | None = None) -> dict:
    ts = ts or int(time.time())
    return {
        "X-Sign": make_sign(body, ts),
        "X-Timestamp": str(ts),
        "X-Device": hashlib.sha256(derive_key()).hexdigest()[:16],
    }


def verify_sign(body: str, ts: int, sign: str) -> bool:
    key = derive_key()
    expect = hmac.new(key, f"{body}{ts}".encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expect, sign)
