"""标准时间获取：禁止信任本地系统时间，从 Cloudflare 网关取服务端时间"""
import http.client
import ssl
from email.utils import parsedate_to_datetime

_TRACE_HOSTS = ["1.1.1.1", "1.0.0.1", "cloudflare.com"]


def _from_trace_header() -> float | None:
    ctx = ssl.create_default_context()
    for host in _TRACE_HOSTS:
        try:
            conn = http.client.HTTPSConnection(host, timeout=4, context=ctx)
            conn.request("GET", "/cdn-cgi/trace")
            resp = conn.getresponse()
            resp.read()
            conn.close()
            date_h = resp.getheader("Date")
            age_h = resp.getheader("Age")
            if not date_h:
                continue
            server_now = parsedate_to_datetime(date_h).timestamp()
            age = float(age_h) if age_h else 0.0
            return server_now + age / 2
        except Exception:
            continue
    return None


def _from_ntp() -> float | None:
    """RFC 868 简单时间协议，作为 Cloudflare 失败后的兜底"""
    import socket
    import struct

    for server in ("time.apple.com", "ntp.aliyun.com", "pool.ntp.org"):
        try:
            s = socket.create_connection((server, 123), timeout=3)
            pkt = b"\x1b" + b"\x00" * 47
            s.send(pkt)
            data = s.recv(48)
            s.close()
            secs, frac = struct.unpack("!II", data[40:48])
            epoch = secs - 2208988800
            return epoch + frac / 2 ** 32
        except Exception:
            continue
    return None


def get_server_time() -> float | None:
    """返回服务端 UNIX 时间戳；全部失败返回 None（上层应拒绝启动校验）"""
    t = _from_trace_header()
    if t:
        return t
    return _from_ntp()
