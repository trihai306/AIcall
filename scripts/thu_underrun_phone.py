"""Bắn một đoạn tiếng LIÊN TỤC xuống app cầu nối và đếm underrun trong đúng lúc đó.

Vì sao cần: logcat lúc nào cũng có 'underrun' ở quãng lặng giữa hai lượt — đó là
bình thường, không hại gì. Chỉ underrun XẢY RA TRONG LÚC ĐANG PHÁT mới làm rè.
Script bơm tiếng đều 20ms/khung rồi đếm underrun trong đúng cửa sổ đó.

Chạy: python scripts/thu_underrun_phone.py [lead_ms]
"""
import socket, subprocess, sys, time, wave, pathlib, re

GOC = pathlib.Path(__file__).resolve().parent.parent
WAV = GOC / "mau_duong_xuong_phone" / "C_xuong_phone_8k.wav"
PORT = 8123
FRAME_MS = 20


def adb(*args, **kw):
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def main():
    lead = float(sys.argv[1]) / 1000 if len(sys.argv) > 1 else 0.06
    wav = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else WAV
    if not wav.is_absolute():
        wav = GOC / wav

    with wave.open(str(wav), "rb") as w:
        rate, pcm = w.getframerate(), w.readframes(w.getnframes())
    fb = rate * FRAME_MS // 1000 * 2
    khung = [pcm[i:i + fb] for i in range(0, len(pcm) - fb + 1, fb)]
    print(f"tiếng: {len(khung)} khung x {FRAME_MS}ms = {len(khung)*FRAME_MS/1000:.1f}s @ {rate}Hz")
    print(f"mồi (LEAD) = {lead*1000:.0f} ms")

    adb("forward", f"tcp:{PORT}", f"tcp:{PORT}")
    adb("logcat", "-c")

    s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # App chạy SONG CÔNG: nó bơm luồng thu lên liên tục. Không đọc thì đệm đầy,
    # TCP nghẽn ngược và phiên bị ngắt giữa chừng.
    import threading
    dung = threading.Event()

    def hut():
        try:
            while not dung.is_set():
                if not s.recv(4096):
                    break
        except Exception:
            pass

    threading.Thread(target=hut, daemon=True).start()

    t0 = time.perf_counter()
    next_at = t0 + lead
    for f in khung:
        d = next_at - time.perf_counter()
        if d > 0:
            time.sleep(d)
        s.sendall(f)
        next_at += FRAME_MS / 1000
    phat_xong = time.perf_counter() - t0
    time.sleep(0.4)                      # để máy phát nốt phần trong đệm
    dung.set()
    s.close()

    out = adb("logcat", "-d", "-t", "600").stdout
    dong = [l for l in out.splitlines() if "underrun" in l.lower()]
    print(f"\nbơm xong trong {phat_xong:.2f}s (tiếng dài {len(khung)*FRAME_MS/1000:.1f}s)")
    print(f"UNDERRUN trong lúc phát: {len(dong)}")
    for l in dong[:8]:
        print("   " + re.sub(r"\s+", " ", l)[:120])


if __name__ == "__main__":
    main()
