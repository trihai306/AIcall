"""Đo ĐỘ TRỄ VÒNG của đường tiếng cuộc gọi - phần mà bản ghi không nhìn thấy.

Bản ghi cuộc gọi đóng dấu khung AI lúc nó RỜI backend và khung khách lúc backend
NHẬN được (`phone_call_service.py:1100`, `recorder.py`). Nên đo trên bản ghi chỉ
ra độ trễ NỘI BỘ; khách còn chờ thêm chặng USB -> máy -> GSM -> tai, cộng chặng
ngược lại. Script này đo đúng phần thiếu đó.

Cách đo: phát một chirp qua ĐÚNG đường phát thật, để nó đi hết vòng rồi vọng lại
vào mic ở đầu khách. Hai lần xuất hiện cùng nằm trên MỘT trục thời gian của bản
ghi hai kênh, nên hiệu vị trí là độ trễ vòng - không cần đồng bộ đồng hồ hai máy.

HẠN CHẾ CỦA `--trong-may`: chế độ này bắt buộc cho tiếng ra loa ngoài (usage=2,
MEDIA) thì mic mới nghe lại được, mà đường thật lại đi bằng usage=1
(VOICE_COMMUNICATION) và tiêm vào cuộc gọi. Hai đường có đệm và định tuyến khác
nhau, nên con số của `--trong-may` KHÔNG suy ra được cho đường thật - nó chỉ để
kiểm chứng rằng script bắt được vọng. Đo 07-09: bắt được 2/8 lần, hai lần bắt
được cho 693 và 701ms (lệch 6ms), sáu lần còn lại chirp không ra tới loa (dải
350-3300Hz trong mic không nhúc nhích). Con số dùng được phải lấy từ `--goi`.
"""
import sys

import numpy as np

# Windows mặc định cp1252: in tiếng Việt ra là script CHẾT giữa chừng, sau khi
# đã bật cầu tiếng và đang ghi. Đặt ngay đây, trước mọi lệnh in.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Băng thoại GSM thực dụng là 300-3400Hz; ra ngoài là bị cắt mất.
CHIRP_F0, CHIRP_F1 = 350.0, 3300.0
CHIRP_GIAY = 0.25
# Đệm AudioTrack chiều xuống trên máy (`BridgeService.demXuongMs`). Gói tiếng
# đem phát phải dày hơn hẳn con số này, không thì mảnh nằm lại trong đệm và
# không bao giờ ra tới loa: đo 07-09 với gói 250ms chỉ 2/8 lần tới nơi.
DEM_XUONG_MS = 500

# Đỉnh phải cao hơn nền ngần này lần độ lệch bền vững (MAD) mới coi là chirp
# thật. Đo trên tín hiệu dựng sẵn: nhiễu trắng suông cho 6,9 - tức tỉ lệ quanh 6
# là thứ bộ lọc đối sánh TỰ SINH RA từ nhiễu, không phải bằng chứng có tiếng.
# Vọng yếu nhất còn đáng tin (-45dB) cho 134. Ngưỡng 20 nằm giữa hai đám đó.
TIN_TOI_THIEU = 20.0


def tao_chirp(sr: int, giay: float = CHIRP_GIAY,
              f0: float = CHIRP_F0, f1: float = CHIRP_F1) -> np.ndarray:
    """Chirp quét tuyến tính, có vuốt hai đầu.

    Vuốt đầu/cuối vì cạnh vuông làm rò năng lượng ra ngoài băng thoại, phần rò
    đó bị GSM cắt và đỉnh tương quan tù đi.
    """
    n = int(sr * giay)
    t = np.arange(n) / sr
    x = np.sin(2 * np.pi * (f0 * t + (f1 - f0) / (2 * giay) * t ** 2))
    vuot = int(n * 0.15)
    cua = np.ones(n)
    cua[:vuot] = np.linspace(0, 1, vuot)
    cua[-vuot:] = np.linspace(1, 0, vuot)
    return x * cua


def _doi_sanh(x: np.ndarray, mau: np.ndarray) -> np.ndarray:
    """Bộ lọc đối sánh: tương quan tín hiệu với mẫu chirp, làm qua FFT."""
    n = 1 << (len(x) + len(mau)).bit_length()
    r = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(mau, n)), n)
    return np.abs(r[:len(x)])


def _dinh(r: np.ndarray, tu: int = 0, den: int | None = None) -> tuple[int, float]:
    """Vị trí đỉnh, và đỉnh cao hơn nền bao nhiêu lần độ lệch bền vững.

    Dùng MAD chứ không dùng độ lệch chuẩn: chính cái đỉnh ta đang tìm sẽ kéo độ
    lệch chuẩn lên và tự làm mình trông tầm thường đi.
    """
    lat = r[tu:den] if den is not None else r[tu:]
    if not len(lat):
        return -1, 0.0
    i = int(np.argmax(lat))
    giua = float(np.median(r))
    lech = float(np.median(np.abs(r - giua))) * 1.4826 or 1e-12
    return tu + i, (float(lat[i]) - giua) / lech


def tim_tre(ai: np.ndarray, khach: np.ndarray, sr: int,
            tre_toi_da_ms: float = 1500.0) -> tuple[float, float]:
    """Độ trễ vòng (ms) và độ tin của phép đo.

    `ai` là kênh bot của bản ghi (mốc tiếng rời backend), `khach` là kênh khách
    (mốc tiếng vọng về tới backend). Độ tin dưới `TIN_TOI_THIEU` nghĩa là không
    tìm thấy chirp trong kênh khách - lúc đó con số trả về không dùng được.
    """
    mau = tao_chirp(sr)
    i_ai, tin_ai = _dinh(_doi_sanh(np.asarray(ai, float), mau))
    if i_ai < 0 or tin_ai < TIN_TOI_THIEU:
        return 0.0, 0.0
    r_kh = _doi_sanh(np.asarray(khach, float), mau)
    het = i_ai + int(sr * tre_toi_da_ms / 1000)
    i_kh, tin_kh = _dinh(r_kh, tu=i_ai, den=min(het, len(r_kh)))
    if i_kh < 0:
        return 0.0, 0.0
    return (i_kh - i_ai) / sr * 1000.0, tin_kh


def _cac_moc_phat(r_ai: np.ndarray, sr: int, cach_toi_thieu_s: float = 1.0) -> list[int]:
    """Vị trí từng lần chirp rời backend, đọc trên kênh bot của bản ghi."""
    giua = float(np.median(r_ai))
    lech = float(np.median(np.abs(r_ai - giua))) * 1.4826 or 1e-12
    manh = np.nonzero((r_ai - giua) / lech >= TIN_TOI_THIEU)[0]
    if not len(manh):
        return []
    moc, cum = [], [manh[0]]
    for i in manh[1:]:
        if i - cum[-1] > sr * cach_toi_thieu_s:
            moc.append(max(cum, key=lambda k: r_ai[k]))
            cum = []
        cum.append(i)
    moc.append(max(cum, key=lambda k: r_ai[k]))
    return moc


def do_nhieu_lan(ai: np.ndarray, khach: np.ndarray, sr: int,
                 tre_toi_da_ms: float = 1500.0) -> list[tuple[float, float]]:
    """Độ trễ vòng của TỪNG lần phát: [(ms, độ tin), ...].

    Lần nào không tìm thấy vọng thì BỎ HẲN khỏi kết quả. Trả về một con số cho
    lần không đo được là cách nhanh nhất để kéo trung vị về phía sai.
    """
    mau = tao_chirp(sr)
    r_ai = _doi_sanh(np.asarray(ai, float), mau)
    r_kh = _doi_sanh(np.asarray(khach, float), mau)
    ket = []
    for i_ai in _cac_moc_phat(r_ai, sr):
        het = min(i_ai + int(sr * tre_toi_da_ms / 1000), len(r_kh))
        i_kh, tin = _dinh(r_kh, tu=i_ai, den=het)
        if i_kh >= 0 and tin >= TIN_TOI_THIEU:
            ket.append(((i_kh - i_ai) / sr * 1000.0, tin))
    return ket


# ==========================================================================
# Phần điều khiển: phát chirp qua đúng đường thật rồi đọc lại bản ghi.
# ==========================================================================

def doc_wav(wav: bytes) -> tuple[np.ndarray, int]:
    """WAV -> (mẫu float [-1,1], tần số lấy mẫu)."""
    import io
    import wave
    with wave.open(io.BytesIO(wav), "rb") as w:
        pcm = w.readframes(w.getnframes())
        return np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0, w.getframerate()


def wav_chirp(sr: int = 24000) -> bytes:
    """Chirp có im lặng bao quanh, đóng gói WAV - định dạng `play()` nhận.

    Im lặng hai đầu KHÔNG phải để cho đẹp: nó làm gói dày hơn đệm AudioTrack
    của máy, nhờ vậy chirp mới thật sự ra tới loa. Nó cũng tách chirp khỏi mép
    gói, nên bộ lọc đối sánh không phải làm việc với một mảnh bị cắt cụt.
    """
    import io
    import wave
    im = np.zeros(int(sr * DEM_XUONG_MS / 1000))
    x = np.clip(np.concatenate([im, tao_chirp(sr), im]) * 0.6, -1, 1)
    pcm = (x * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def bao_cao(ket: list[tuple[float, float]], nhan: str) -> float | None:
    """In kết quả. Trả trung vị, hoặc None nếu không đủ căn cứ để kết luận."""
    if not ket:
        print(f"\n{nhan}: KHÔNG ĐO ĐƯỢC - không tìm thấy chirp vọng về lần nào.")
        return None
    v = np.array([k[0] for k in ket])
    print(f"\n{nhan}: {len(ket)} lần đo")
    for i, (tre, tin) in enumerate(ket, 1):
        print(f"   lần {i}: {tre:7.1f}ms  (đỉnh cao hơn nền {tin:.0f} lần)")
    print(f"   trung vị {np.median(v):.0f}ms | lệch chuẩn {v.std():.0f}ms | "
          f"min {v.min():.0f} max {v.max():.0f}")
    if v.std() > 30:
        print("   ⚠ lệch chuẩn > 30ms: số này CHƯA ĐẠT nghiệm thu, đừng dùng để kết luận")
    return float(np.median(v))


def phan_tich_file(duong_dan: str) -> list[tuple[float, float]]:
    import soundfile as sf
    x, sr = sf.read(duong_dan, always_2d=True)
    if x.shape[1] < 2:
        raise SystemExit(f"{duong_dan} không phải bản ghi hai kênh")
    return do_nhieu_lan(x[:, 1], x[:, 0], sr)      # kênh phải = bot, trái = khách


async def chay(a) -> int:
    import asyncio
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    serial = a.serial or settings.phone_serial
    # Trong máy: thu bằng mic của máy, và BẮT BUỘC cho tiếng ra LOA NGOÀI
    # (usage=2). Loa áp tai quá nhỏ để chính mic của máy nghe lại - đo lần đầu
    # 07-09 với loa áp tai cho 8/8 lần không thấy chirp, dải chirp trong mic còn
    # giảm 0,069 -> 0,042. Gọi thật thì giữ mặc định: đường tiêm vào cuộc gọi
    # cần đúng VOICE_COMMUNICATION, và tiếng ra loa ở đầu KHÁCH chứ không phải
    # ở máy này.
    src = adb_service.SRC_MIC if a.trong_may else 3     # 3 = VOICE_DOWNLINK
    ok, msg = await adb_service.start_bridge(
        serial, port=a.port, src=src, usage=2 if a.trong_may else None,
        dem_xuong=a.dem_xuong)
    print(f"[1] cầu tiếng: {msg}")
    if not ok:
        return 1

    session = CallSession(customer_name="Đo trễ vòng")
    bridge = PhoneCallBridge(None, session, port=a.port, serial=serial)
    bridge.tam_dung_nghe = True          # không có pipeline, chỉ ghi
    await bridge.start(ghi_am=True)
    print(f"[2] đang ghi: phiên {session.session_id}")

    try:
        if a.goi:
            print(f"[3] gọi {a.goi} — BẮT MÁY, BẬT LOA NGOÀI, đặt cạnh máy rồi im lặng")
            ok, msg = await adb_service.dial(serial, a.goi)
            print(f"    {msg}")
            if not ok:
                return 1
            for i in range(45):
                await asyncio.sleep(1)
                tt, _ = await adb_service.precise_call_state(serial)
                if tt == 1:
                    print(f"    {i}s: ĐÃ NỐI MÁY")
                    break
            else:
                print("    không ai bắt máy")
                return 1
            # ĐÚNG MỘT LẦN, sau khi đã nối máy. Ghi mixer nhiều lần giữa cuộc
            # gọi làm RỚT cuộc gọi - xem PhoneCallManager.start.
            await asyncio.sleep(0.8)
            ok_inj, msg_inj = await adb_service.set_uplink_injection(serial, True)
            print(f"    {msg_inj}")
            if not ok_inj:
                print("    KHÔNG đặt được đường tiêm -> đầu kia sẽ không nghe thấy chirp")

        wav = wav_chirp()
        print(f"[4] phát chirp {a.lan} lần, cách nhau {a.nghi}s")
        await asyncio.sleep(1.0)                     # để bản ghi có đoạn nền
        for i in range(a.lan):
            await bridge.play(wav)
            print(f"    lần {i + 1}/{a.lan}")
            await asyncio.sleep(a.nghi)
        await asyncio.sleep(1.0)
    finally:
        if a.goi:
            await adb_service.hangup(serial)
        await bridge.stop()
        await adb_service.stop_bridge(serial, port=a.port)

    duong = session.recording_path
    if not duong:
        print("[5] KHÔNG có bản ghi -> không đo được")
        return 1
    print(f"[5] bản ghi: {duong}")
    nhan = "TRỌN VÒNG (có GSM)" if a.goi else "TRONG MÁY (backend <-> máy, chưa có GSM)"
    bao_cao(phan_tich_file(duong), nhan)
    return 0


def main() -> int:
    import argparse
    import asyncio
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--trong-may", action="store_true",
                   help="không gọi: chirp ra loa máy, mic chính máy đó thu lại")
    g.add_argument("--goi", metavar="SỐ", help="gọi thật rồi đo trọn vòng")
    g.add_argument("--phan-tich", metavar="FILE", help="đọc lại một bản ghi đã có")
    p.add_argument("--lan", type=int, default=8, help="số lần phát chirp (mặc định 8)")
    p.add_argument("--nghi", type=float, default=2.5, help="giây giữa hai lần")
    p.add_argument("--port", type=int, default=8123)
    p.add_argument("--serial", default="")
    p.add_argument("--dem-xuong", type=int, default=None,
                   help="đệm AudioTrack trên máy (ms). Bỏ trống = giữ mặc định 500. "
                        "Hạ xuống CHỈ để đo xem nó chiếm bao nhiêu trong độ trễ.")
    a = p.parse_args()
    if a.phan_tich:
        bao_cao(phan_tich_file(a.phan_tich), a.phan_tich)
        return 0
    return asyncio.run(chay(a))


if __name__ == "__main__":
    raise SystemExit(main())
