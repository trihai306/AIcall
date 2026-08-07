"""Talks to the physical calling device: connection checks and outbound dials.

The app does not speak GSM or SIP itself. It drives whatever bridge the user
already has - a phone-gateway app on an Android handset, a USB modem exposed
over HTTP, a PBX with a click-to-call URL - through one generic hook:

    dial_url = http://192.168.1.50:8080/call?number={number}

`{number}` is replaced with the number to dial and the URL is fetched with GET.
If the template carries no placeholder the number is POSTed as JSON instead
({"number": "0912345678"}), which is what most gateway apps accept.

Devices without a dial_url (a sound card, a handset dialled by hand) are managed
here - they just cannot be dialled programmatically, and the API says so
instead of pretending the call went out.
"""

import asyncio
import glob
import logging
import platform
import re
from urllib.parse import urlsplit

import httpx

from backend.services import adb_service

logger = logging.getLogger(__name__)

_TIMEOUT = 4.0
_HOST_PORT = re.compile(r"^(?P<host>[\w.\-]+):(?P<port>\d{1,5})$")


# --- connection check --------------------------------------------------------

async def check_device(device: dict) -> tuple[str, str]:
    """Probe a device. Returns (status, human readable detail in Vietnamese).

    status is one of: online | offline | error | unknown.
    """
    address = (device.get("address") or "").strip()
    dial_url = (device.get("dial_url") or "").strip()
    kind = device.get("kind", "")

    # Handsets are probed over ADB, not HTTP.
    if kind == "adb" and address:
        return await adb_service.check(address)

    target = address or dial_url

    if not target:
        return "unknown", "Chưa có địa chỉ để kiểm tra (thiết bị này chỉ quản lý thủ công)"

    if target.startswith(("http://", "https://")):
        return await _check_http(target)

    m = _HOST_PORT.match(target)
    if m:
        return await _check_tcp(m.group("host"), int(m.group("port")))

    # Serial port / MAC address / SIP uri: nothing to probe over the network,
    # so report what we know instead of guessing.
    return "unknown", f"Không kiểm tra tự động được địa chỉ '{target}' — kiểm tra thủ công"


async def _check_http(url: str) -> tuple[str, str]:
    # Probe the origin, not the dial endpoint: fetching the dial URL as a health
    # check would place a real call.
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            res = await client.get(origin)
        if res.status_code >= 500:
            return "error", f"Thiết bị trả về lỗi HTTP {res.status_code}"
        return "online", f"Kết nối được ({res.status_code})"
    except httpx.TimeoutException:
        return "offline", f"Hết thời gian chờ khi kết nối {origin}"
    except Exception as e:
        return "offline", f"Không kết nối được {origin}: {e}"


async def _check_tcp(host: str, port: int) -> tuple[str, str]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=_TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        return "online", f"Mở được cổng {host}:{port}"
    except asyncio.TimeoutError:
        return "offline", f"Hết thời gian chờ khi kết nối {host}:{port}"
    except Exception as e:
        return "offline", f"Không kết nối được {host}:{port}: {e}"


# --- dialling ----------------------------------------------------------------

async def dial(device: dict, number: str) -> tuple[bool, str]:
    """Ask the device to call `number`. Returns (success, detail in Vietnamese)."""
    kind = device.get("kind", "")
    address = (device.get("address") or "").strip()

    # Handset in the phone farm: ADB presses the number directly.
    if kind == "adb":
        if not address:
            return False, "Thiết bị chưa có serial ADB"
        from backend.config import settings
        return await adb_service.dial(address, number,
                                      slot=settings.phone_sim_slot)

    dial_url = (device.get("dial_url") or "").strip()
    if not dial_url:
        return False, (
            "Thiết bị chưa cấu hình 'Link gọi' nên hệ thống không tự bấm số được — "
            "bấm số thủ công trên máy rồi bấm 'Đã kết nối'"
        )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT * 2) as client:
            if "{number}" in dial_url:
                res = await client.get(dial_url.replace("{number}", number))
            else:
                res = await client.post(dial_url, json={"number": number})

        if res.status_code >= 400:
            return False, f"Thiết bị từ chối lệnh gọi (HTTP {res.status_code})"
        logger.info(f"Dialled {number} via {device.get('name')} ({res.status_code})")
        return True, f"Đã gửi lệnh gọi tới thiết bị ({res.status_code})"
    except httpx.TimeoutException:
        return False, "Hết thời gian chờ khi gửi lệnh gọi"
    except Exception as e:
        return False, f"Lỗi khi gửi lệnh gọi: {e}"


async def hangup(device: dict) -> tuple[bool, str]:
    """End the current call. Only ADB handsets support this programmatically."""
    if device.get("kind") != "adb":
        return False, "Chỉ máy trong phone farm (ADB) mới cúp máy tự động được"
    address = (device.get("address") or "").strip()
    if not address:
        return False, "Thiết bị chưa có serial ADB"
    return await adb_service.hangup(address)


# --- discovery ---------------------------------------------------------------

def suggest_devices() -> list[dict]:
    """Serial ports that look like a modem/phone, as *suggestions* to add.

    Pure filesystem globbing - no extra dependency, and nothing is written to
    the database: the user still confirms each device in the UI.
    """
    system = platform.system()
    if system == "Darwin":
        patterns = ["/dev/tty.usbmodem*", "/dev/tty.usbserial*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*"]
    elif system == "Windows":
        patterns = []  # COM ports are not visible through glob
    else:
        patterns = ["/dev/ttyUSB*", "/dev/ttyACM*"]

    found = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            found.append({
                "name": path.rsplit("/", 1)[-1],
                "kind": "usb_modem",
                "address": path,
            })
    return found
