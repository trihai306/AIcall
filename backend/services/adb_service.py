"""Drives Android handsets (a "phone farm") over ADB.

Each handset plugged into the USB hub is one calling device: ADB places the
call, reports the call state and hangs up. What ADB canNOT do is carry the
audio - it is a control channel, with no audio endpoint. The voice path is a
separate matter: on a rooted handset the Voice Bridge app carries it over the
same USB cable (see tools/voicebridge/).

Every adb invocation is wrapped in a timeout: a wedged USB link must never
block the event loop that is serving live calls.
"""

import asyncio
import logging
import re
import shutil

from backend.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0

# `adb devices -l` line: "R5CT30XXXX  device product:a54x model:SM_A546E ..."
_DEVICE_LINE = re.compile(
    r"^(?P<serial>\S+)\s+(?P<state>device|offline|unauthorized|bootloader)\b(?P<rest>.*)$"
)
_MODEL = re.compile(r"model:(\S+)")
_CALL_STATE = re.compile(r"mCallState=(\d)")

# telephony.registry mCallState
CALL_STATES = {0: "idle", 1: "ringing", 2: "offhook"}


def adb_available() -> bool:
    return shutil.which("adb") is not None


async def _run(*args: str, timeout: float = _TIMEOUT) -> tuple[int, str, str]:
    """Run an adb command. Returns (returncode, stdout, stderr)."""
    if not adb_available():
        return 127, "", "Chưa cài adb (Android Platform Tools)"
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
    except asyncio.TimeoutError:
        return 124, "", f"Hết thời gian chờ adb {' '.join(args)}"
    except Exception as e:
        return 1, "", f"Lỗi chạy adb: {e}"


async def list_handsets() -> tuple[list[dict], str]:
    """Every handset ADB can see. Returns (devices, error message if any).

    state: device = sẵn sàng, unauthorized = chưa bấm "Cho phép gỡ lỗi USB"
    trên máy, offline = mất kết nối USB.
    """
    if not adb_available():
        return [], "Chưa cài adb — cài Android Platform Tools rồi quét lại"

    code, out, err = await _run("devices", "-l")
    if code != 0:
        return [], err.strip() or "adb devices lỗi"

    handsets = []
    for line in out.splitlines()[1:]:            # bỏ dòng "List of devices attached"
        line = line.strip()
        if not line or line.startswith("*"):     # "* daemon started successfully"
            continue
        m = _DEVICE_LINE.match(line)
        if not m:
            continue
        model = _MODEL.search(m.group("rest"))
        handsets.append({
            "serial": m.group("serial"),
            "state": m.group("state"),
            "model": model.group(1).replace("_", " ") if model else "Android",
        })
    return handsets, ""


async def describe(serial: str) -> dict:
    """Extra detail for one handset: SIM operator, số thuê bao, pin."""
    info = {"serial": serial}

    _, brand, _ = await _run("-s", serial, "shell", "getprop", "ro.product.brand")
    _, model, _ = await _run("-s", serial, "shell", "getprop", "ro.product.model")
    _, ver, _ = await _run("-s", serial, "shell", "getprop", "ro.build.version.release")
    _, op, _ = await _run("-s", serial, "shell", "getprop", "gsm.operator.alpha")

    info["brand"] = brand.strip()
    info["model"] = model.strip()
    info["android"] = ver.strip()
    # Nhiều máy 2 SIM trả về "Viettel,Viettel" - lấy nhà mạng đầu tiên.
    info["operator"] = op.strip().split(",")[0]

    code, batt, _ = await _run("-s", serial, "shell", "dumpsys", "battery")
    if code == 0:
        m = re.search(r"level:\s*(\d+)", batt)
        info["battery"] = int(m.group(1)) if m else None

    return info



# Chỉ tính khi `InCallActivity` đang GIỮ FOCUS. Tìm nó trong toàn bộ `dumpsys
# window` là sai: cửa sổ vẫn nằm trong ngăn xếp sau khi cúp máy, nên trạng thái
# kẹt ở "offhook" vĩnh viễn - đã đo, báo offhook cả trước khi gọi lẫn sau khi cúp.
_FOCUS_INCALL = re.compile(r"mCurrentFocus=.*InCallActivity")


async def _man_hinh_cuoc_goi_dang_hien(serial: str) -> bool:
    code, out, _ = await _run("-s", serial, "shell", "dumpsys", "window")
    return code == 0 and bool(_FOCUS_INCALL.search(out))


async def call_state(serial: str) -> tuple[str, str]:
    """Trạng thái cuộc gọi hiện tại: idle | ringing | offhook | unknown."""
    code, out, err = await _run(
        "-s", serial, "shell", "dumpsys", "telephony.registry"
    )
    if code != 0:
        return "unknown", err.strip() or "Không đọc được trạng thái"
    m = _CALL_STATE.search(out)
    if m:
        state = CALL_STATES.get(int(m.group(1)), "unknown")
        if state != "idle":
            return state, ""

    # Cùng lỗi với `precise_call_state`: `telephony.registry` báo mCallState=0
    # NGAY CẢ KHI máy đang gọi ra. Đối chiếu ảnh chụp màn hình 2026-08-06 - máy
    # hiện "Calling… 0396130621" mà trường này vẫn 0 suốt cuộc. Nên phải hỏi
    # thêm nguồn khác trước khi dám kết luận "rảnh".
    code2, tele, _ = await _run("-s", serial, "shell", "dumpsys", "telecom")
    if code2 == 0:
        t = tele.upper()
        if "STATE=ACTIVE" in t or "STATE: ACTIVE" in t:
            return "offhook", "telecom: đang nói chuyện"
        if any(k in t for k in ("STATE=DIALING", "STATE: DIALING",
                                "STATE=CONNECTING", "STATE=RINGING")):
            return "offhook", "telecom: đang gọi/đổ chuông"

    if await _man_hinh_cuoc_goi_dang_hien(serial):
        return "offhook", "màn hình cuộc gọi đang hiện"

    if m:
        return CALL_STATES.get(int(m.group(1)), "unknown"), ""
    return "unknown", "Máy không báo trạng thái cuộc gọi (có thể không có sóng/SIM)"


async def precise_call_state(serial: str) -> tuple[int, str]:
    """Trạng thái CHI TIẾT của cuộc gọi đang chạy: (mã, mô tả tiếng Việt).

    Phải dùng cái này chứ không phải `call_state` khi theo dõi cuộc gọi ĐI:
    `mCallState` nhảy sang offhook ngay lúc bắt đầu quay số, nên nhìn nó thì
    "đang đổ chuông" và "khách đã nhấc máy" giống hệt nhau — mà đó đúng là chỗ
    bộ quay số tự động cần phân biệt để biết có ai bắt máy hay không.

    Trả về (-1, lý do) khi không đọc được.
    """
    code, out, err = await _run("-s", serial, "shell", "dumpsys", "telephony.registry")
    if code != 0:
        return -1, err.strip() or "Không đọc được trạng thái cuộc gọi"
    m = _PRECISE_FG.search(out)
    if m:
        value = int(m.group(1))
        if value > 0:
            return value, PRECISE_CALL_STATES.get(value, f"mã {value}")

    # telephony.registry BÁO 0 CẢ KHI ĐANG GỌI. Bắt được 2026-08-06 trên máy
    # thật: màn hình hiện "Calling… 0396130621" mà mPreciseCallState in ra
    # "Ringing 0, Foreground 0, Background 0" suốt cả cuộc. Theo dõi 36 giây chỉ
    # thấy idle rồi kết luận nhầm là "cuộc gọi không hề chạy".
    #
    # Hậu quả nặng hơn nhiều so với báo cáo sai: `phone_call_service` chỉ bật
    # đường tiêm tiếng khi trạng thái == 1 (khách đã nhấc máy). Trường đó không
    # bao giờ lên -> đường tiêm KHÔNG BAO GIỜ được bật -> gọi từ app thì khách
    # không nghe thấy gì, trong khi script tiêm thẳng vẫn ra tiếng. Đúng triệu
    # chứng người dùng báo.
    #
    # `dumpsys telecom` cập nhật thật; `mCurrentFocus` là InCallActivity là dấu
    # hiệu chắc chắn thứ hai (đã đối chiếu với ảnh chụp màn hình).
    code2, tele, _ = await _run("-s", serial, "shell", "dumpsys", "telecom")
    if code2 == 0:
        t = tele.upper()
        if "STATE=ACTIVE" in t or "STATE: ACTIVE" in t:
            return 1, "Khách đã nhấc máy (telecom: ACTIVE)"
        if any(k in t for k in ("STATE=DIALING", "STATE: DIALING",
                                "STATE=CONNECTING", "STATE=RINGING")):
            return 3, "Đang đổ chuông (telecom)"

    # Không coi là đã nhấc máy: bật đường tiêm sớm thì tiếng AI phát lúc chưa
    # ai nghe.
    if await _man_hinh_cuoc_goi_dang_hien(serial):
        return 3, "Đang trong cuộc gọi (màn hình InCall)"

    if m:
        return 0, PRECISE_CALL_STATES.get(0, "rảnh")
    return -1, "Máy không báo trạng thái chi tiết (ROM cũ hoặc không có SIM)"


async def answer(serial: str) -> tuple[bool, str]:
    """Bắt máy cuộc gọi đến. KEYCODE_HEADSETHOOK (79) chạy trên nhiều ROM hơn
    KEYCODE_CALL (5), vốn hay bị hiểu thành "mở bàn phím gọi"."""
    code, _, err = await _run("-s", serial, "shell", "input", "keyevent", "79")
    if code == 0:
        return True, "Đã bắt máy"
    code2, _, err2 = await _run("-s", serial, "shell", "input", "keyevent", "5")
    if code2 == 0:
        return True, "Đã bắt máy (KEYCODE_CALL)"
    return False, (err2 or err).strip() or "Không bắt được máy"


async def incoming_number(serial: str) -> str:
    """Số của người đang gọi đến, chuỗi rỗng nếu không đọc được.

    Không phải ROM nào cũng lộ số ra dumpsys, nên đây là thông tin có thì tốt:
    thiếu số thì phiên vẫn mở, chỉ là không tra được tên khách trong danh bạ.
    """
    _, out, _ = await _run("-s", serial, "shell", "dumpsys", "telecom")
    m = re.search(r"tel:([+\d]{6,15})", out)
    return m.group(1) if m else ""


async def dial(serial: str, number: str,
               slot: int | None = None) -> tuple[bool, str]:
    """Bấm số trên handset.

    Thử ACTION_CALL trước (gọi thẳng). Máy nào chặn quyền CALL_PHONE cho shell
    thì rơi về ACTION_DIAL + KEYCODE_CALL - mở bàn phím rồi bấm nút gọi.

    HAI VIỆC BẮT BUỘC TRƯỚC KHI BẤM SỐ, cả hai đều làm cuộc gọi hỏng ÂM THẦM:

    1. MỞ KHOÁ MÀN HÌNH. Màn khoá thì giao diện gọi không lên được và cuộc gọi
       đứng im ở trạng thái "rảnh" - nhìn từ ngoài giống hệt "không ai bắt máy".
    2. CHỈ ĐỊNH KHE SIM (`slot`, đánh số từ 0). Máy hai khe bật hộp "chọn SIM"
       cho số chưa gọi bao giờ, mà hộp đó chờ người bấm.

    Cả hai đã được xử lý trong `scripts/goi_va_noi.py` từ lâu nhưng đường thật
    (`dialer_service.dial` -> đây) thì không có - một trong nhiều chỗ hai đường
    lệch nhau.
    """
    number = number.replace(" ", "")
    await _run("-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    await _run("-s", serial, "shell", "wm", "dismiss-keyguard")
    await asyncio.sleep(0.6)

    them = (["--ei", "com.android.phone.extra.slot", str(slot)]
            if slot is not None and slot >= 0 else [])
    code, out, err = await _run(
        "-s", serial, "shell", "am", "start",
        "-a", "android.intent.action.CALL", "-d", f"tel:{number}", *them,
    )
    combined = f"{out}\n{err}"
    if code == 0 and "Error" not in combined and "Permission Denial" not in combined:
        logger.info(f"ADB dialled {number} on {serial}")
        return True, "Đã bấm số trên máy"

    # Fallback: mở dialer rồi gửi phím gọi
    code2, out2, err2 = await _run(
        "-s", serial, "shell", "am", "start",
        "-a", "android.intent.action.DIAL", "-d", f"tel:{number}",
    )
    if code2 != 0:
        return False, (err2 or err).strip() or "Không mở được bàn phím gọi"
    await asyncio.sleep(0.6)      # để dialer kịp hiện lên trước khi gửi phím
    code3, _, err3 = await _run("-s", serial, "shell", "input", "keyevent", "5")
    if code3 != 0:
        return False, err3.strip() or "Mở được bàn phím nhưng không bấm được nút gọi"
    logger.info(f"ADB dialled {number} on {serial} (fallback DIAL+KEYCODE_CALL)")
    return True, "Đã bấm số trên máy (qua bàn phím)"


async def hangup(serial: str) -> tuple[bool, str]:
    """Cúp máy. KEYCODE_ENDCALL bị chặn trên một số ROM - báo rõ khi thất bại."""
    code, _, err = await _run("-s", serial, "shell", "input", "keyevent", "6")
    if code != 0:
        return False, err.strip() or "Không cúp được máy — cúp thủ công trên handset"
    return True, "Đã cúp máy"


async def chuyen_cuoc_goi(serial: str, so: str) -> tuple[bool, str]:
    """Nối cuộc gọi đang chạy sang `so` bằng cách gọi hội nghị ba bên.

    Không dùng mã chuyển tiếp của nhà mạng (`**21*<số>#`): mã đó đặt CHUYỂN
    HƯỚNG cho MỌI cuộc gọi tới về sau, không phải chuyển cuộc đang nói — bật
    nhầm là mọi số gọi vào máy đều bị đẩy đi cho tới khi có người tắt tay.

    Cách ở đây giữ cuộc hiện tại, gọi thêm chuyên viên rồi ghép hai bên. Máy nào
    ROM chặn KEYCODE thì báo rõ để người vận hành nối tay.
    """
    so = so.replace(" ", "")
    if not so:
        return False, "Chưa khai số chuyên viên"

    truoc, _ = await precise_call_state(serial)
    if truoc not in (1, 2):
        return False, f"Máy không có cuộc gọi nào đang nói chuyện (trạng thái {truoc})"

    # Quay số thứ hai - hệ thống điện thoại tự giữ cuộc thứ nhất.
    code, out, err = await _run(
        "-s", serial, "shell", "am", "start",
        "-a", "android.intent.action.CALL", "-d", f"tel:{so}",
    )
    combined = f"{out}\n{err}"
    if code != 0 or "Error" in combined or "Permission Denial" in combined:
        return False, (
            f"Không gọi được số chuyên viên {so}: "
            f"{(err or out).strip()[:120] or 'máy từ chối lệnh gọi'}"
        )

    # Chờ chuyên viên bắt máy. Không bắt trong 25 giây thì coi như bận.
    for _ in range(25):
        await asyncio.sleep(1.0)
        ma, _mo_ta = await precise_call_state(serial)
        if ma == 1:
            break
    else:
        return False, f"Chuyên viên {so} không bắt máy sau 25 giây"

    # Ghép hai cuộc lại. KEYCODE_CALL trong lúc đang giữ một cuộc = "merge" trên
    # phần lớn ROM Android.
    code2, _, err2 = await _run("-s", serial, "shell", "input", "keyevent", "5")
    if code2 != 0:
        return False, (
            f"Đã gọi được {so} nhưng không ghép được hai cuộc: "
            f"{err2.strip() or 'ROM chặn phím'} — ghép tay trên máy"
        )
    return True, f"Đã nối máy sang {so}"


async def check(serial: str) -> tuple[str, str]:
    """Trạng thái handset cho cột Status: online | offline | error."""
    handsets, err = await list_handsets()
    if err:
        return "error", err

    found = next((h for h in handsets if h["serial"] == serial), None)
    if found is None:
        return "offline", f"Không thấy máy {serial} trong danh sách adb"
    if found["state"] == "unauthorized":
        return "error", "Máy chưa cho phép gỡ lỗi USB — mở khoá màn hình và bấm Cho phép"
    if found["state"] != "device":
        return "offline", f"Máy đang ở trạng thái '{found['state']}'"

    state, detail = await call_state(serial)
    if state == "unknown":
        return "online", f"Kết nối được, nhưng {detail}"
    return "online", f"Sẵn sàng (cuộc gọi: {state})"


# --- chẩn đoán: máy đã cắm/bật/kết nối được chưa -------------------------------

# Trạng thái đăng ký mạng thoại trong dumpsys telephony.registry
_VOICE_REG = re.compile(r"mVoiceRegState=(\d)")
_PRECISE_FG = re.compile(r"mForegroundCallState=(\d)")

# PreciseCallState. Với cuộc gọi ĐI, mCallState nhảy sang offhook ngay lúc bắt
# đầu quay số nên vô dụng; chỉ trường này mới phân biệt được "đang đổ chuông"
# với "khách đã nhấc máy".
PRECISE_CALL_STATES = {
    0: "rảnh", 1: "đang nói chuyện", 2: "đang giữ máy", 3: "đang quay số",
    4: "đang đổ chuông bên khách", 5: "có cuộc gọi đến", 6: "cuộc gọi chờ",
    7: "vừa ngắt", 8: "đang ngắt",
}


def _chk(cid: str, label: str, status: str, detail: str, hint: str = "") -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "hint": hint}


async def diagnose(serial: str) -> dict:
    """Chạy trọn danh sách kiểm tra cho một handset vừa cắm vào.

    Trả về từng mục riêng thay vì một chữ 'online/offline', vì khi cắm máy vào
    mà không gọi được thì nguyên nhân có thể ở bất kỳ khâu nào: chưa bật gỡ lỗi
    USB, chưa mở khoá, chưa lắp SIM, không có sóng... Gộp lại thành một trạng
    thái là bắt người dùng tự đoán.
    """
    checks: list[dict] = []

    # 1. adb có thấy máy không
    if not adb_available():
        checks.append(_chk("adb", "Kết nối ADB", "fail", "Máy tính chưa cài adb",
                           "Cài Android Platform Tools rồi thử lại"))
        return {"serial": serial, "checks": checks, "connected": False, "callable": False}

    handsets, err = await list_handsets()
    found = next((h for h in handsets if h["serial"] == serial), None)
    if err:
        checks.append(_chk("adb", "Kết nối ADB", "fail", err, ""))
        return {"serial": serial, "checks": checks, "connected": False, "callable": False}
    if found is None:
        checks.append(_chk("adb", "Kết nối ADB", "fail", "Không thấy máy trong danh sách adb",
                           "Kiểm tra dây USB, thử cổng khác, hoặc rút ra cắm lại"))
        return {"serial": serial, "checks": checks, "connected": False, "callable": False}
    if found["state"] == "unauthorized":
        checks.append(_chk("adb", "Kết nối ADB", "fail", "Máy chưa cho phép gỡ lỗi USB",
                           "Mở khoá màn hình điện thoại và bấm 'Cho phép' ở hộp thoại hiện ra"))
        return {"serial": serial, "checks": checks, "connected": False, "callable": False}
    if found["state"] != "device":
        checks.append(_chk("adb", "Kết nối ADB", "fail", f"Máy đang ở trạng thái '{found['state']}'",
                           "Rút ra cắm lại dây USB"))
        return {"serial": serial, "checks": checks, "connected": False, "callable": False}

    checks.append(_chk("adb", "Kết nối ADB", "ok", f"{found['model']} · {serial}"))
    connected = True

    # 2. máy đã khởi động xong chưa
    _, boot, _ = await _run("-s", serial, "shell", "getprop", "sys.boot_completed")
    if boot.strip() == "1":
        checks.append(_chk("boot", "Máy đã bật", "ok", "Đã khởi động xong"))
    else:
        checks.append(_chk("boot", "Máy đã bật", "warn", "Chưa khởi động xong",
                           "Chờ máy vào màn hình chính rồi kiểm tra lại"))

    # 3. màn hình / khoá
    _, power, _ = await _run("-s", serial, "shell", "dumpsys", "power")
    awake = "mWakefulness=Awake" in power
    _, trust, _ = await _run("-s", serial, "shell", "dumpsys", "trust")
    locked = "deviceLocked=1" in trust
    if locked:
        checks.append(_chk("screen", "Màn hình", "warn", "Đang khoá",
                           "Mở khoá máy — máy khoá thì nhiều lệnh điều khiển bị chặn"))
    else:
        checks.append(_chk("screen", "Màn hình", "ok",
                           "Đang bật, không khoá" if awake else "Đang tắt nhưng không khoá"))

    # 4. SIM
    _, sim, _ = await _run("-s", serial, "shell", "getprop", "gsm.sim.state")
    sim_raw = sim.strip()
    slots = [s for s in sim_raw.split(",") if s]
    if any(s.startswith("READY") or s.startswith("LOADED") for s in slots):
        checks.append(_chk("sim", "SIM", "ok", sim_raw))
    elif not sim_raw:
        checks.append(_chk("sim", "SIM", "warn", "Máy không báo trạng thái SIM", ""))
    else:
        checks.append(_chk("sim", "SIM", "fail", f"Không có SIM sẵn sàng ({sim_raw})",
                           "Lắp SIM vào máy — không có SIM thì không gọi ra được"))

    # 5. đăng ký mạng thoại
    _, reg, _ = await _run("-s", serial, "shell", "dumpsys", "telephony.registry", timeout=12.0)
    m = _VOICE_REG.search(reg)
    _, op, _ = await _run("-s", serial, "shell", "getprop", "gsm.operator.alpha")
    operator = op.strip().split(",")[0]
    if m and m.group(1) == "0":
        checks.append(_chk("network", "Sóng / mạng", "ok", operator or "Đã đăng ký mạng"))
    else:
        emergency = "mIsEmergencyOnly=true" in reg
        checks.append(_chk(
            "network", "Sóng / mạng", "fail",
            "Chỉ gọi được số khẩn cấp" if emergency else "Chưa đăng ký được mạng thoại",
            "Thường là do thiếu SIM; nếu đã có SIM thì kiểm tra sóng và chế độ máy bay"))

    # 6. cuộc gọi hiện tại
    mp = _PRECISE_FG.search(reg)
    if mp:
        code = int(mp.group(1))
        checks.append(_chk("call", "Cuộc gọi hiện tại", "ok" if code == 0 else "warn",
                           PRECISE_CALL_STATES.get(code, f"mã {code}")))

    # 7. pin
    _, batt, _ = await _run("-s", serial, "shell", "dumpsys", "battery")
    mb = re.search(r"level:\s*(\d+)", batt)
    if mb:
        lv = int(mb.group(1))
        checks.append(_chk("battery", "Pin", "ok" if lv >= 20 else "warn", f"{lv}%",
                           "" if lv >= 20 else "Cắm sạc — máy tụt pin giữa chiến dịch là mất cuộc gọi"))

    # 8. root (cần cho đường tiếng)
    code, out, _ = await _run("-s", serial, "shell", "su", "-c", "id", timeout=6.0)
    if "uid=0" in out:
        checks.append(_chk("root", "Quyền root", "ok", "Có — dùng được đường tiếng qua USB"))
    else:
        checks.append(_chk("root", "Quyền root", "warn", "Không có hoặc chưa cấp cho shell",
                           "Chỉ cần nếu muốn đưa tiếng cuộc gọi về máy tính"))

    # 9. app cầu nối tiếng
    _, pkg, _ = await _run("-s", serial, "shell", "pm", "path", "com.tuktech.voicebridge")
    if "package:" in pkg:
        priv = "priv-app" in pkg
        checks.append(_chk("bridge", "App cầu nối tiếng", "ok" if priv else "warn",
                           "Đã cài (privileged)" if priv else "Đã cài nhưng chưa phải privileged",
                           "" if priv else "Cài qua module Magisk để có quyền thu tiếng cuộc gọi"))
    else:
        checks.append(_chk("bridge", "App cầu nối tiếng", "warn", "Chưa cài",
                           "Xem tools/voicebridge/README.md"))

    callable_now = not any(c["status"] == "fail" for c in checks)
    return {"serial": serial, "checks": checks, "connected": connected, "callable": callable_now}


# --- đường tiếng: app cầu nối + tiêm tiếng vào đường lên ------------------------

BRIDGE_PKG = "com.tuktech.voicebridge"
BRIDGE_SERVICE = f"{BRIDGE_PKG}/.BridgeService"
MIXCTL = "/data/local/tmp/mixctl"

# Nguồn thu của AudioRecord
SRC_MIC = 1          # thử khi chưa có SIM: nghe mic phòng thay cho tiếng khách
SRC_VOICE_CALL = 4   # tiếng cuộc gọi thật, cần quyền CAPTURE_AUDIO_OUTPUT


async def forward_port(serial: str, port: int) -> tuple[bool, str]:
    """Đưa cổng TCP của điện thoại về máy tính qua chính sợi cáp USB."""
    code, _, err = await _run("-s", serial, "forward", f"tcp:{port}", f"tcp:{port}")
    if code != 0:
        return False, err.strip() or "Không tạo được adb forward"
    return True, ""


async def start_bridge(serial: str, port: int = 8123, src: int = SRC_VOICE_CALL) -> tuple[bool, str]:
    """Bật app cầu nối tiếng trên máy.

    Bắt buộc dùng start-foreground-service: từ Android 8 trở đi, khởi động dịch
    vụ nền từ shell bị chặn thẳng ("app is in background uid null").

    Hai rate PHẢI khớp với hằng số bên phone_call_service, lệch là tiếng sai tốc
    độ - app cắt khung theo rate của nó còn PC cắt theo rate của mình.
    """
    code, out, err = await _run(
        "-s", serial, "shell", "am", "start-foreground-service",
        "-n", BRIDGE_SERVICE, "--ei", "src", str(src), "--ei", "port", str(port),
        "--ei", "rate_xuong", str(settings.phone_rate_xuong),
        "--ei", "rate_len", str(settings.phone_rate_len),
    )
    combined = f"{out}\n{err}"
    if code != 0 or "Error" in combined:
        return False, combined.strip() or "Không bật được app cầu nối"

    ok, msg = await forward_port(serial, port)
    if not ok:
        return False, msg
    return True, (f"Đã bật cầu nối (nguồn {src}, cổng {port}, "
                  f"xuống {settings.phone_rate_xuong}Hz / lên {settings.phone_rate_len}Hz)")


async def stop_bridge(serial: str, port: int = 8123) -> tuple[bool, str]:
    await _run("-s", serial, "shell", "am", "stopservice", "-n", BRIDGE_SERVICE)
    await _run("-s", serial, "forward", "--remove", f"tcp:{port}")
    return True, "Đã tắt cầu nối"


DUONG_TIEM = ("codec", "usb")


def _tuyen_codec(on: bool) -> list[tuple[str, str]]:
    """Trộn tiếng vào đường lên NGAY TRONG CODEC.

        AudioTrack -> SPUS -> SIFS1 -> UAIF0 -> codec AIF1RX1
                   -> AIF1TX1 Input 2 (dây mic) -> UAIF0 -> ABOX NSRC1 -> modem

    PHẢI đặt cả `ABOX UAIF0 SPK` lẫn `AIF1TX1 Input 2`, thiếu một là đầu bên kia
    im lặng hoàn toàn: khi gọi bằng loa áp tai, ABOX đẩy tiếng phát ra UAIF1
    (mạch khuếch đại) chứ không qua codec, nên AIF1RX1 rỗng và trộn nó vào
    AIF1TX1 chỉ là trộn im lặng.

    Dùng `Input 2` chứ không `Input 1`: HAL dựng lại chuỗi micro ở Input 1 mỗi
    lần đổi tuyến, còn Input 2 nó không đụng - đo được là giữ nguyên suốt.

    Dùng SIFS1 chứ không SIFS0: SIFS0 mang cả đường xuống của modem, mà
    VOICE_DOWNLINK thu đúng SIFS0 - để chung thì AI nghe lại chính nó, STT phiên
    âm ra rác và VAD tự cắt lời mình.

    Tắt HẾT bốn đầu vào khác của mixer đường lên: codec cộng cả 4 cổng, để hở
    cổng nào thì tiếng phòng lọt vào và thành vòng hồi tiếp với loa áp tai.
    """
    if not on:
        return ([(f"ABOX SPUS OUT{i}", "SIFS0") for i in range(6)] +
                [("ABOX UAIF0 SPK", "RESERVED"),
                 ("AIF1TX1 Input 2", "None"), ("AIF1TX2 Input 2", "None"),
                 ("AIF1TX1 Input 1", "ASRC1IN1L"),
                 ("AIF1TX2 Input 1", "ASRC1IN1R")] +
                [(f"AIF1TX{tx} Input {i}", "None") for tx in (1, 2) for i in (3, 4)])
    # DỌN DẤU VẾT CỦA ĐƯỜNG USB (`ABOX NSRC1`, `ABOX ERAP info USB On`) dù đường
    # này không dùng tới chúng. Không dọn thì chạy đường usb một lần rồi quay về
    # codec là đầu bên kia IM LẶNG HOÀN TOÀN, mà đọc lại control vẫn thấy đủ cả
    # `UAIF0 SPK = SIFS1` lẫn `AIF1TX1 Input 2 = AIF1RX1` nên trông như đã đúng.
    #
    # Đã mắc (2026-08-05): cuộc gọi thật đọc ra `ERAP info USB On = 1` sót lại từ
    # lần thử đường usb trước đó. Cờ ấy báo cho khối xử lý tiếng rằng nguồn đường
    # lên là THIẾT BỊ NGOÀI, trong khi tuyến thật lại đang lấy từ codec - lệch
    # nhau nên tiếng không lên tới modem.
    #
    # Bài học chung: mỗi đường tiêm phải ĐỊNH NGHĨA ĐỦ trạng thái nó cần, đừng
    # giả định đường kia đã tự dọn. Hai đường dùng chung một bộ control.
    # CHỈ chuyển hướng SPUS OUT0 - luồng CỦA TA (AudioTrack đi RDMA0 -> SPUS0).
    # Năm cổng còn lại để nguyên trên SIFS0.
    #
    # Bản cũ dồn cả sáu cổng sang SIFS1 và điều đó GIẾT ĐƯỜNG THU: `VOICE_DOWNLINK`
    # thu ở SIFS0, dồn hết đi thì không còn gì nuôi SIFS0. Đo bằng A/B trên hai
    # cuộc gọi thật liền nhau, chỉ khác đúng biến này:
    #
    #     bật tiêm   kênh khách đỉnh 11379 nhưng CHỈ 0,4% thời lượng có tiếng,
    #                cả cuộc gọi bắt được đúng một chớp 140ms -> 0 lượt
    #     tắt tiêm   STT nghe được, LLM trả lời, 1 lượt hội thoại trọn vẹn
    #
    # Triệu chứng cực kỳ dễ đổ nhầm: nhìn từ ngoài chỉ thấy "khách nói mà AI
    # không trả lời", và mọi control đường tiêm đọc lại đều đúng.
    return ([("ABOX SPUS OUT0", "SIFS1")] +
            [("ABOX UAIF0 SPK", "SIFS1"),
             ("ABOX NSRC1", "UAIF0"), ("ABOX ERAP info USB On", "0"),
             ("AIF1TX1 Input 2", "AIF1RX1"), ("AIF1TX2 Input 2", "AIF1RX1")] +
            [(f"AIF1TX{tx} Input {i}", "None") for tx in (1, 2) for i in (1, 3, 4)])


def _tuyen_usb(on: bool) -> list[tuple[str, str]]:
    """Đưa tiếng lên bằng ĐƯỜNG THIẾT BỊ NGOÀI mà Samsung dựng sẵn.

    Lấy nguyên từ `incall-usb-headset-mic` trong /vendor/etc/mixer_paths.xml của
    máy - đường HAL dùng khi cắm tai nghe USB, để tiếng micro của tai nghe lên
    modem:

        ABOX SPUS OUT6 = SIFS2      luồng phát -> SIFS2
        ABOX SIFS2     = SPUS OUT6
        ABOX NSRC1     = SIFS2      đường lên lấy thẳng từ SIFS2
        ABOX SIFM1     = WDMA
        ABOX ERAP info USB On = 1   BÁO nguồn là thiết bị ngoài

    Khác đường codec ở hai điểm: không qua codec và UAIF0 chút nào, và có cờ
    ERAP. Cờ đó nói cho khối xử lý tiếng biết nguồn KHÔNG PHẢI micro cầm tay nên
    nó không áp bộ khử ồn/chỉnh mức vốn dành cho micro lên tín hiệu đã sạch của
    ta - đây là thứ duy nhất giải thích được vì sao mọi thay đổi định tuyến khác
    đều cho kết quả y hệt nhau.

    Dùng SPUS OUT0..5 thay vì OUT6 vì tiếng đi qua AudioTrack (RDMA0 -> SPUS0),
    không qua RDMA6 như tai nghe USB thật.
    """
    if not on:
        return ([(f"ABOX SPUS OUT{i}", "SIFS0") for i in range(6)] +
                [("ABOX NSRC1", "UAIF0"), ("ABOX ERAP info USB On", "0"),
                 ("ABOX UAIF0 SPK", "RESERVED"),
                 ("AIF1TX1 Input 1", "ASRC1IN1L"),
                 ("AIF1TX2 Input 1", "ASRC1IN1R")])
    return ([(f"ABOX SPUS OUT{i}", "SIFS2") for i in range(6)] +
            [("ABOX SIFS2", "SPUS OUT0"),
             ("ABOX NSRC1", "SIFS2"),
             ("ABOX SIFM1", "WDMA"),
             ("ABOX ERAP info USB On", "1"),
             ("ABOX UAIF0 SPK", "RESERVED")] +
            [(f"AIF1TX{tx} Input {i}", "None")
             for tx in (1, 2) for i in (1, 2, 3, 4)])


async def giu_duong_tiem(serial: str, duong: str | None = None,
                         chu_ky: float = 5.0):
    """Canh đường tiêm suốt cuộc gọi, và CHỈ đặt lại khi nó thật sự bị ghi đè.

    HAL không đụng tới đường tiêm trong một cuộc gọi bình thường, nhưng mọi lần
    đổi tuyến (bật loa ngoài, cắm tai nghe, cuộc gọi chờ) đều làm nó chạy lại
    `mixer_paths.xml` và ghi đè `ABOX UAIF0 SPK`. Nên vẫn phải canh.

    NHƯNG ĐỪNG GHI VÔ ĐIỀU KIỆN. Bản đầu trong `scripts/goi_va_noi.py` cứ 5 giây
    lại ghi hơn 20 control vào khối âm thanh GIỮA LÚC ĐANG GỌI, và chính nó LÀM
    RỚT CUỘC GỌI. Đo tận tay (2026-08-05, cùng máy cùng SIM, cách nhau vài phút):

        gọi trần, không đụng gì        36.1s   REMOTE / NORMAL
        cầu tiếng + ghi lại mỗi 5s     12-19s  ERROR / OUT_OF_SERVICE
        cầu tiếng + KHÔNG ghi lại      32.2s   REMOTE / NORMAL

    Cả ba lần rớt đều báo "Mobile network not available" nên rất dễ đổ oan cho
    nhà mạng — đã đổ oan thật một lần, chỉ tách ra được nhờ gọi một cuộc TRẦN để
    so (`scripts/goi_tran_khong_tiem.py`).

    ĐỌC thì vô hại, GHI mới phá. Nên đọc trước, lệch mới ghi.
    """
    canh = ("ABOX UAIF0 SPK", "AIF1TX1 Input 2")
    while True:
        await asyncio.sleep(chu_ky)
        try:
            hien = await doc_duong_tiem(serial)
            lech = [k for k in canh if hien.get(k) in (None, "None", "RESERVED")]
            if lech:
                logger.info("[phone] HAL ghi đè %s -> đặt lại đường tiêm",
                            ", ".join(lech))
                await set_uplink_injection(serial, True, duong)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"[phone] canh đường tiêm lỗi (bỏ qua): {e}")


async def doc_duong_tiem(serial: str) -> dict[str, str]:
    """Đọc lại các control quyết định đường lên, để xác nhận đã đặt được.

    Đặt xong mà không đọc lại thì không biết HAL có giật lại không - đã mất nhiều
    cuộc gọi vì tin rằng lệnh set là đủ.
    """
    ten = ([f"AIF1TX1 Input {i}" for i in (1, 2, 3, 4)] +
           ["ABOX NSRC1", "ABOX UAIF0 SPK", "ABOX SPUS OUT0",
            "ABOX ERAP info USB On"])
    lenh = "; ".join(f'{MIXCTL} get "{t}"' for t in ten)
    _, out, _ = await _run("-s", serial, "shell", f"su -c '{lenh}'", timeout=25.0)
    ra: dict[str, str] = {}
    for dong in out.splitlines():
        m = re.match(r"(.+?)\[0\] = (\d+)(?: \((.*)\))?", dong.strip())
        if m:
            ra[m.group(1)] = m.group(3) or m.group(2)
    return ra


async def set_uplink_injection(serial: str, on: bool,
                               duong: str | None = None) -> tuple[bool, str]:
    """Bật/tắt đường đưa tiếng AI vào chiều lên của cuộc gọi.

    Hai đường, chọn bằng `settings.phone_duong_tiem` hoặc tham số `duong`:

      "codec"  trộn trong codec ở `AIF1TX1 Input 2`. Đã chạy được - người bên kia
               nghe thấy giọng AI - nhưng báo tiếng "dè".
      "usb"    dùng đường thiết bị ngoài Samsung dựng sẵn cho tai nghe USB, kèm
               cờ `ERAP info USB On`.

    Gọi lại được nhiều lần: HAL dựng lại tuyến mỗi khi đổi định tuyến, nên hàm
    này thường được chạy định kỳ để giữ đường tiêm.
    """
    duong = (duong or settings.phone_duong_tiem or "codec").lower()
    if duong not in DUONG_TIEM:
        return False, f"Đường tiêm không hợp lệ: {duong} (chọn {'/'.join(DUONG_TIEM)})"

    dat = _tuyen_usb(on) if duong == "usb" else _tuyen_codec(on)

    # Gộp thành MỘT lệnh su. Gọi rời từng cái là hơn chục lượt adb (~1,4 giây),
    # mà hàm này còn chạy định kỳ - đủ để nghẽn vòng phát tiếng.
    # Bọc nháy kép cho CẢ TÊN LẪN GIÁ TRỊ: cả hai đều có thể chứa dấu cách
    # ("AIF1TX1 Input 2", "SPUS OUT0"). Bọc thiếu giá trị thì shell tách đôi và
    # mixctl chỉ nhận "SPUS" rồi báo không nằm trong danh sách.
    lenh = "; ".join(f'{MIXCTL} set "{ten}" "{gt}"' for ten, gt in dat)
    code, out, err = await _run("-s", serial, "shell", f"su -c '{lenh}'",
                                timeout=25.0)
    so_ok = out.count("da dat")
    if code != 0 or so_ok < len(dat):
        return False, (f"Không đặt được đường tiêm '{duong}' — "
                       f"{so_ok}/{len(dat)} control: {(err or out).strip()[:120]}")
    if not on:
        return True, "Đường lên: trả về micro"
    return True, ("Đường lên [usb]: tiếng AI -> SIFS2 -> NSRC1 -> modem"
                  " (không qua codec, có cờ ERAP)" if duong == "usb" else
                  "Đường lên [codec]: tiếng AI -> SIFS1 -> UAIF0 -> AIF1TX1"
                  " (micro đã tắt)")
