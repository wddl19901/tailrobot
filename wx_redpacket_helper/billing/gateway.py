"""USDT 自动收银台网关
Base: https://sweet-moon-43e4.wddl19901.workers.dev
流程: 传金额下单 -> 用户付精准USDT(TRC20) -> 轮询 check-order 到 SUCCESS -> 客户端本地解锁
订单有效期15分钟; 网关不做鉴权, 授权状态由客户端本地保管
"""
import json

import requests

GATEWAY = "https://sweet-moon-43e4.wddl19901.workers.dev"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

PACKAGES = [
    ("1天", 20, 1),
    ("7天", 120, 7),
    ("15天", 240, 15),
    ("1月", 360, 30),
    ("1年", 2888, 365),
]

_timeout = 15


def _post(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False)
    headers = {"Content-Type": "application/json", "User-Agent": _UA}
    resp = requests.post(f"{GATEWAY}{path}", data=body, headers=headers, timeout=_timeout)
    data = _safe_json(resp)
    _check(resp, data)
    return data.get("data", {}) or {}


def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{GATEWAY}{path}", params=params, headers={"User-Agent": _UA}, timeout=_timeout)
    data = _safe_json(resp)
    _check(resp, data)
    return data


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"code": resp.status_code, "msg": f"非JSON响应: {resp.text[:200]}"}


def _check(resp, data: dict):
    code = data.get("code", resp.status_code)
    if code != 200 and resp.status_code >= 400:
        raise RuntimeError(f"网关错误 {resp.status_code}: {data.get('msg', data)[:200]}")


def create_order(usdt: float, order_id: str) -> dict:
    return _post("/api/create-order", {"amount": usdt, "orderId": order_id})


def check_order(pay_id: str) -> dict:
    return _get("/api/check-order", {"payId": pay_id})
