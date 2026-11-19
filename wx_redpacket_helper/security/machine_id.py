import hashlib
import platform
import subprocess
import uuid


def get_machine_uuid() -> str:
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["wmic", "csproduct", "get", "uuid"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                line = line.strip()
                if line and line.upper() != "UUID" and not line.startswith("!"):
                    return line.upper()
        except Exception:
            pass
        return _fallback_id()

    if platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=")[-1].strip().strip('"').upper()
        except Exception:
            pass
        return _fallback_id()

    return _fallback_id()


def _fallback_id() -> str:
    try:
        mac = uuid.getnode()
    except Exception:
        mac = 0
    raw = f"{platform.node()}|{platform.machine()}|{platform.system()}|{mac}"
    return hashlib.sha256(raw.encode()).hexdigest().upper()


_machine_id = None


def get_machine_id() -> str:
    global _machine_id
    if _machine_id is None:
        _machine_id = get_machine_uuid()
    return _machine_id
