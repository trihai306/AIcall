"""Nhịp ĐOÁN TRƯỚC có đúng theo thời gian không, ở CẢ hai đường vào?

Đệm của phiên mang tần số riêng: trình duyệt 16kHz, đường thoại 8kHz. Hai ngưỡng
mở đoán trước từng chốt cứng theo BYTE của 16kHz, nên khi bỏ khâu đổi tần (đệm
thoại thành 8kHz) thì đường thoại lặng lẽ chạy đúng NỬA nhịp:

    mốc bắt đầu   1.25s -> 2.5s
    nhịp đoán     0.4s  -> 0.8s

Không có lỗi nào bắn ra, chỉ là AI nghĩ thưa đi một nửa - đúng thứ khó thấy nhất.
Script bơm tiếng theo từng khung 20ms và đếm xem đoán trước nổ ở giây thứ mấy.

    python scripts/do_nhip_doan_truoc.py
"""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline as SP

    print(f"\n  mốc bắt đầu {SP._SPEC_MIN_MS}ms | nhịp {SP._SPEC_STEP_MS}ms\n")
    loi = 0
    for ten, rate in (("trình duyệt", 16000), ("đường thoại", 8000)):
        ss = CallSession()
        ss.audio_rate = rate
        khung = rate * 2 * 20 // 1000          # 20ms PCM16
        moc = []
        for k in range(1, 301):                # 6 giây tiếng
            n = k * khung
            if n < SP._byte_cho_ms(ss, SP._SPEC_MIN_MS):
                continue
            if n - ss.spec_bytes < SP._byte_cho_ms(ss, SP._SPEC_STEP_MS):
                continue
            ss.spec_bytes = n
            moc.append(n / (rate * 2))

        cach = [round(moc[i] - moc[i - 1], 2) for i in range(1, len(moc))]
        print(f"  {ten} ({rate}Hz): nổ lần đầu ở {moc[0]:.2f}s,"
              f" sau đó mỗi {set(cach) if cach else '-'}s")
        print(f"    trong 6s tiếng: {len(moc)} lần nghĩ")
        if abs(moc[0] - SP._SPEC_MIN_MS / 1000) > 0.03:
            print("    ^^ SAI mốc bắt đầu"); loi += 1
        if cach and any(abs(c - SP._SPEC_STEP_MS / 1000) > 0.03 for c in cach):
            print("    ^^ SAI nhịp"); loi += 1
        print()

    print("  Hai đường phải cho CÙNG số lần nghĩ - khác là còn chỗ tính theo byte.")
    return 1 if loi else 0


if __name__ == "__main__":
    raise SystemExit(main())
