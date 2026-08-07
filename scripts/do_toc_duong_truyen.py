"""Đo tốc độ đường truyền tiếng giữa server và điện thoại.

Nối THẲNG vào cổng TCP của app Voice Bridge qua adb forward, không qua pipeline,
để con số đo được là của riêng đường truyền chứ không lẫn thời gian STT/LLM/TTS.

Bốn thứ đo được:
  1. Chiều xuống (server -> điện thoại): ghi một cụm khung rồi xem socket nuốt
     bao nhanh. Phần "nuốt trước khi chặn" chính là đệm phát của máy.
  2. Chiều lên (điện thoại -> server): nhịp khung tới và độ giật, so với nhịp
     thời gian thực 20ms/khung.
  3. Trọn vòng: phát một tiếng bíp, đo tới lúc chính micro của máy nghe lại.
     Đây là con số khách cảm nhận được - gồm cả USB, đệm phát, đệm thu.
  4. Độ giật: khung tới đều hay bụm cục. Bụm cục thì VAD cắt lượt sai nhịp.

    python scripts/do_toc_duong_truyen.py
    python scripts/do_toc_duong_truyen.py --lan 5
"""

import argparse
import math
import socket
import statistics
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RATE = 8000
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000      # 160
FRAME_BYTES = FRAME_SAMPLES * 2              # 320


def doc_du(s: socket.socket, n: int) -> bytes:
    b = b""
    while len(b) < n:
        m = s.recv(n - len(b))
        if not m:
            raise ConnectionError("điện thoại đóng kết nối")
        b += m
    return b


def co_tone(frame: bytes, freq: float) -> tuple[bool, float]:
    """Có tiếng bíp ở tần số này không? Trả về (có, tỉ lệ năng lượng)."""
    import numpy as np
    x = np.frombuffer(frame, dtype=np.int16).astype("float32")
    if len(x) < 8:
        return False, 0.0
    ph = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    tong = ph.sum() or 1e-12
    k = int(round(freq * len(x) / RATE))
    quanh = ph[max(0, k - 1):k + 2].sum()
    ty = float(quanh / tong)
    return ty > 0.25, ty


def main() -> int:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8123)
    ap.add_argument("--lan", type=int, default=3, help="Số lần đo trọn vòng")
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--amp", type=int, default=14000)
    args = ap.parse_args()

    print(f"Nối tới {args.host}:{args.port} (app Voice Bridge qua adb forward) ...")
    s = socket.create_connection((args.host, args.port), timeout=10)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("  đã nối\n")

    # --- 2 & 4. Chiều lên: nhịp khung tới và độ giật ------------------------
    print("CHIỀU LÊN (điện thoại -> server)")
    n = 150                                        # 3 giây
    moc = []
    t0 = time.perf_counter()
    for _ in range(n):
        doc_du(s, FRAME_BYTES)
        moc.append(time.perf_counter())
    troi = moc[-1] - t0
    khoang = [(b - a) * 1000 for a, b in zip(moc, moc[1:])]
    print(f"  {n} khung trong {troi*1000:.0f} ms"
          f"  (thời gian thực phải là {n*FRAME_MS} ms)")
    print(f"  nhịp trung bình {statistics.mean(khoang):.2f} ms/khung"
          f"  | trung vị {statistics.median(khoang):.2f}")
    print(f"  giật: lệch chuẩn {statistics.pstdev(khoang):.2f} ms"
          f"  | nhanh nhất {min(khoang):.2f}  chậm nhất {max(khoang):.2f}")
    bum = sum(1 for k in khoang if k < 2.0)
    print(f"  khung tới bụm cục (<2ms sau khung trước): {bum}/{len(khoang)}"
          f"  ({bum/len(khoang)*100:.0f}%)")

    # --- 1. Chiều xuống: đệm máy chứa được bao nhiêu ------------------------
    # CHÚ Ý ĐỌC SỐ NÀY CHO ĐÚNG: đây là DUNG LƯỢNG ĐỆM của điện thoại, KHÔNG
    # phải hành vi của sản phẩm. Đường thật đi qua `_write_loop`, nó đã bám nhịp
    # 20ms/khung và chỉ giữ trước 60ms - xem LEAD trong phone_call_service.py.
    # Ghi thẳng vào socket như dưới đây là đi vòng qua bộ điều nhịp đó.
    print("\nCHIỀU XUỐNG (server -> điện thoại) — đo DUNG LƯỢNG ĐỆM")
    im = bytes(FRAME_BYTES)
    m = 150
    t1 = time.perf_counter()
    for _ in range(m):
        s.sendall(im)
    t_ghi = (time.perf_counter() - t1) * 1000
    print(f"  ghi {m} khung ({m*FRAME_MS} ms tiếng) hết {t_ghi:.0f} ms")
    if t_ghi < m * FRAME_MS * 0.5:
        print(f"  -> đệm (socket + AudioTrack) chứa được ít nhất"
              f" {m*FRAME_MS - t_ghi:.0f} ms tiếng")
        print(f"     Đây là lý do _write_loop PHẢI bám nhịp thời gian thực:")
        print(f"     ghi thẳng thì {m*FRAME_MS} ms tiếng nằm sẵn trong máy, cắt lời")
        print(f"     dọn hàng đợi cũng không lấy lại được.")
    else:
        print(f"  -> máy chặn theo nhịp thời gian thực, đệm nhỏ")

    # --- 3. Trọn vòng: bíp ra loa, micro nghe lại --------------------------
    print("\nTRỌN VÒNG (bíp ra loa -> micro nghe lại)")
    print("  Cần loa điện thoại đang mở. Không nghe thấy thì báo 'không đo được'.")
    vong = []
    for lan in range(1, args.lan + 1):
        # dọn khung cũ đang trên đường
        s.settimeout(0.05)
        try:
            while True:
                s.recv(65536)
        except Exception:
            pass
        s.settimeout(10)

        ph, step = 0.0, 2 * math.pi * args.freq / RATE
        bip = bytearray()
        for _ in range(FRAME_SAMPLES * 15):        # 300ms
            bip += int(args.amp * math.sin(ph)).to_bytes(2, "little", signed=True)
            ph += step
        t2 = time.perf_counter()
        s.sendall(bytes(bip))

        thay = None
        han = t2 + 3.0
        while time.perf_counter() < han:
            f = doc_du(s, FRAME_BYTES)
            co, ty = co_tone(f, args.freq)
            if co:
                thay = (time.perf_counter() - t2) * 1000
                break
        if thay is None:
            print(f"  lần {lan}: không nghe thấy bíp vọng lại")
        else:
            vong.append(thay)
            print(f"  lần {lan}: {thay:.0f} ms")
        time.sleep(0.5)

    s.close()

    print("\n" + "=" * 62)
    print(f"Chiều lên : {statistics.mean(khoang):.1f} ms/khung"
          f" (chuẩn {FRAME_MS}), giật ±{statistics.pstdev(khoang):.1f} ms")
    print(f"Chiều xuống: ghi {m*FRAME_MS} ms tiếng hết {t_ghi:.0f} ms")
    if vong:
        print(f"Trọn vòng : {statistics.mean(vong):.0f} ms"
              f" (thấp nhất {min(vong):.0f}, cao nhất {max(vong):.0f})")
        print("  Gồm: USB xuống + đệm phát + đường âm loa->mic + đệm thu + USB lên.")
    else:
        print("Trọn vòng : KHÔNG ĐO ĐƯỢC - micro không nghe thấy tiếng loa.")
        print("  Mở loa ngoài to lên rồi chạy lại, hoặc đây là con số không cần thiết")
        print("  cho cuộc gọi thật (lúc đó uplink/downlink tách nhau, không vọng).")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
