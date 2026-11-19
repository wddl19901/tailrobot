"""USDT 收银台网关 API 客户端
根路径: https://workers.dev
套餐: 1天=20U | 7天=120U | 15天=240U | 1月=360U | 1年=2888U
"""
import json
import time

import requests

from ..security.signing import sign_headers
from ..security.signing import verify_sign

GATEWAY = "https://workers.dev"

PACKAGES = [
    ("1天", 20),
    ("7天", 120),
    ("15天", 240),
    ("1月", 360),
    ("1年", 2888),
]

_timeout = 15


def _post(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False)
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        **sign_headers(body, ts),
    }
    resp = requests.post(f"{GATEWAY}{path}", data=body, headers=headers, timeout=_timeout)
    _verify(resp, body, ts)
    return resp.json()


def _get(path: str, params: dict | None = None) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    body = qs or ""
    ts = int(time.time())
    headers = sign_headers(body, ts)
    resp = requests.get(f"{GATEWAY}{path}", params=params, headers=headers, timeout=_timeout)
    _verify(resp, body, ts)
    return resp.json()


def _verify(resp, body: str, ts: int):
    sig = resp.headers.get("X-Sign")
    if not sig:
        raise RuntimeError("响应缺少签名头，拒绝信任")
    resp_body = resp.text
    if not verify_sign(resp_body, int(resp.headers.get("X-Timestamp", ts)), sig):
        raise RuntimeError("响应签名校验失败，疑似中间人篡改")
    if resp.status_code >= 400:
        raise RuntimeError(f"网关错误 {resp.status_code}: {resp_body[:200]}")


def create_order(package_label: str) -> dict:
    """POST /api/create-order -> {payId, payUrl, amount}"""
    return _post("/api/create-order", {"package": package_label})


def check_order(pay_id: str) -> dict:
    """GET /api/check-order?payId=xxx -> {status: PENDING|SUCCESS, activationCode?}"""
    return _get("/api/check-order", {"payId": pay_id})


def activate(code: str) -> dict:
    """GET /api/activate?code=xxx -> 200 {data:{validUntil}}; 404/410 表示无效或过期"""
    resp = requests.get(
        f"{GATEWAY}/api/activate",
        params={"code": code},
        headers=sign_headers(json.dumps({"code": code}, ensure_ascii=False)),
        timeout=_timeout,
    )
    if resp.status_code in (404, 410):
        raise RuntimeError("激活码无效或已过期")
    _verify(resp, json.dumps({"code": code}, ensure_ascii=False), int(resp.headers.get("X-Timestamp", 0)))
    return resp.json()
