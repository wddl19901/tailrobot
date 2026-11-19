"""AES-256 加解密：密钥由机器码+盐值经 PBKDF2 派生，授权文件跨机不可用"""
import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .machine_id import get_machine_id

# 硬编码盐值（商用时建议混淆注入，避免明文字面量被直接搜索到）
_SALT = b"TailRobot-2026-USDT-Gate-V1"


def derive_key() -> bytes:
    material = get_machine_id().encode("ascii") + _SALT
    return hashlib.pbkdf2_hmac("sha256", material, _SALT, 65536)


def encrypt_json(obj: dict) -> bytes:
    import json

    key = derive_key()
    iv = hashlib.sha256(key + b"iv-seed").digest()[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = pad(json.dumps(obj, ensure_ascii=False).encode("utf-8"), AES.block_size)
    return base64.b64encode(iv + cipher.encrypt(pt))


def decrypt_json(data: bytes) -> dict:
    import json

    key = derive_key()
    raw = base64.b64decode(data)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return json.loads(unpad(cipher.decrypt(ct), AES.block_size).decode("utf-8"))
