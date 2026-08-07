"""Đo thứ THẬT SỰ RA KHỎI LOA điện thoại, không chỉ thứ gửi xuống dây.

Cách làm: bật app ở chế độ đo (`--ei usage 2` -> phát ra LOA NGOÀI, vì loa áp tai
quá nhỏ so với nền phòng), bơm một file xuống, đồng thời thu lại bằng chính micro
của máy qua chiều lên. Chiều lên phải đặt 24000 thì mới nhìn được phần trên 4 kHz -
để 8000 là tự cắt mất đúng chỗ cần xem.

Phải chạy HAI lần để có đối chứng:
    python scripts/do_am_hoc_phone.py mau_duong_xuong_phone/F_sau_khi_sua.wav
    python scripts/do_am_hoc_phone.py mau_duong_xuong_phone/C_xuong_phone_8k.wav

Bản 8k phải cho vách dựng đứng ở 4 kHz, bản 24k thì không. Nếu cả hai giống nhau
thì đường đi đang bóp băng thông ở đâu đó, chưa phải máy phát đúng.
"""
import pathlib, socket, subprocess, sys, threading, time, wave
import numpy as np

GOC = pathlib.Path(__file__).resolve().parent.parent
PORT = 8123
FRAME_MS = 20
RATE_LEN = 24000        # thu ở 24k để nhìn được tới 12 kHz


def adb(*a):
    return subprocess.run(["adb", *a], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def pho(x: np.ndarray, sr: int) -> dict:
    n = len(x)
    ph = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    tong = ph.sum() or 1e-12
    nl = lambda lo, hi: float(ph[(f >= lo) & (f < hi)].sum() / tong)
    return {
        "0.3-1kHz": round(nl(300, 1000), 4),
        "1-3.4kHz": round(nl(1000, 3400), 4),
        "3.4-4kHz": round(nl(3400, 4000), 4),
        "TREN 4kHz": round(nl(4000, min(sr / 2, 10000)), 4),
    }


def main():
    nguon = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                         else "mau_duong_xuong_phone/F_sau_khi_sua.wav")
    if not nguon.is_absolute():
        nguon = GOC / nguon

    with wave.open(str(nguon), "rb") as w:
        rate_xuong, pcm = w.getframerate(), w.readframes(w.getnframes())
    fb = rate_xuong * FRAME_MS // 1000 * 2
    khung = [pcm[i:i + fb] for i in range(0, len(pcm) - fb + 1, fb)]
    print(f"nguồn : {nguon.name}  ({rate_xuong} Hz, {len(khung)*FRAME_MS/1000:.1f}s)")

    # app phải khởi động lại mới nạp tham số mới - đang chạy thì onStartCommand
    # vào nhánh 'if (running) return' và lệnh coi như trôi đi.
    adb("shell", "am", "force-stop", "com.tuktech.voicebridge")
    time.sleep(2)
    # ĐỪNG mở hết cỡ: loa ngay cạnh micro, mở 15 thì thu vỡ (đo được đỉnh chạm
    # trần 32768). Vỡ tiếng sinh hài bậc cao, làm dải trên 4kHz dội lên giả tạo -
    # đúng cái dải mình đang muốn kết luận, nên sẽ tự lừa mình.
    vol = sys.argv[2] if len(sys.argv) > 2 else "6"
    adb("shell", "media", "volume", "--stream", "3", "--set", vol)
    adb("shell", "am", "start-foreground-service",
        "-n", "com.tuktech.voicebridge/.BridgeService",
        "--ei", "src", "1", "--ei", "port", str(PORT),
        "--ei", "rate_xuong", str(rate_xuong), "--ei", "rate_len", str(RATE_LEN),
        "--ei", "usage", "2")
    time.sleep(3)
    adb("forward", f"tcp:{PORT}", f"tcp:{PORT}")

    s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    thu = bytearray()
    dung = threading.Event()

    def hut():
        # Phải extend chứ KHÔNG `thu += b`: trong hàm lồng, `+=` là phép gán nên
        # Python coi `thu` là biến cục bộ -> UnboundLocalError, luồng chết ngay
        # và bị except nuốt mất, chỉ thấy "thu được quá ít".
        try:
            while not dung.is_set():
                b = s.recv(8192)
                if not b:
                    break
                thu.extend(b)
        except Exception as e:
            print(f"  luồng thu dừng: {e}")

    threading.Thread(target=hut, daemon=True).start()

    next_at = time.perf_counter() + 0.06
    for f in khung:
        d = next_at - time.perf_counter()
        if d > 0:
            time.sleep(d)
        s.sendall(f)
        next_at += FRAME_MS / 1000
    time.sleep(0.5)
    dung.set()
    s.close()

    x = np.frombuffer(bytes(thu[: len(thu) // 2 * 2]), dtype=np.int16).astype(np.float32)
    if len(x) < RATE_LEN:
        print("thu được quá ít, không đo được"); return
    # Bỏ 0,5s đầu: lúc đó loa chưa kêu, chỉ có nền phòng.
    x = x[RATE_LEN // 2:]
    dinh = float(np.abs(x).max())
    vo = int((np.abs(x) >= 32000).sum())
    print(f"thu lại: {len(x)/RATE_LEN:.1f}s @ {RATE_LEN} Hz, đỉnh {dinh:.0f}/32767"
          f", mẫu chạm trần: {vo}")
    if dinh < 800:
        print("  -> quá nhỏ, nhiều khả năng loa chưa kêu hoặc vẫn ra loa áp tai")
        return
    if vo > 0:
        print("  -> THU BỊ VỠ, số liệu dải cao KHÔNG dùng được. Hạ âm lượng:")
        print(f"     python scripts/do_am_hoc_phone.py {sys.argv[1]} 4")
        return

    print("  " + str(pho(x / 32768.0, RATE_LEN)))
    ra = GOC / "mau_duong_xuong_phone" / f"THU_{nguon.stem}.wav"
    with wave.open(str(ra), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE_LEN)
        w.writeframes(x.astype(np.int16).tobytes())
    print(f"  đã ghi {ra.name}")


if __name__ == "__main__":
    main()
