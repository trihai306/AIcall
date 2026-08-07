"""Hạ ngưỡng im lặng xuống 500ms thì AI cắt lời khách bao nhiêu lần?

`SILENCE_END_MS` quyết định "khách im bao lâu thì coi là dứt lời". Để thấp thì AI
đáp nhanh nhưng chen ngang giữa câu; để cao thì an toàn mà khách phải chờ. Đây
KHÔNG phải chuyện chọn con số đẹp - nó phụ thuộc vào cách nói của chính người
đang gọi.

Lịch sử trong dự án: từng để 480ms, người dùng báo "khách nói chưa xong đã nhảy
vào mồm rồi", nên nâng lên 750ms.

Script đo trên KÊNH KHÁCH của các bản ghi cuộc gọi thật (stereo, trái = khách):
tìm mọi khoảng nghỉ GIỮA các đoạn có tiếng, rồi đếm xem bao nhiêu khoảng rơi vào
vùng nguy hiểm - đủ dài để ngưỡng THẤP coi là dứt lời, nhưng thực ra khách còn
nói tiếp.

    python scripts/do_khoang_nghi_khach.py
    python scripts/do_khoang_nghi_khach.py --nguong 400 500 600 750
"""

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def khoang_nghi(khach: np.ndarray, sr: int, nguong_rms: float,
                frame_ms: int = 20) -> list[float]:
    """Độ dài (ms) của mọi khoảng im GIỮA hai đoạn có tiếng.

    Chỉ lấy khoảng NẰM GIỮA: khoảng im ở đầu và cuối bản ghi không phải "nghỉ
    giữa câu" mà là lúc chưa nói / đã nói xong.
    """
    N = sr * frame_ms // 1000
    rms = np.array([np.sqrt((khach[i:i + N] ** 2).mean()) * 32768
                    for i in range(0, len(khach) - N, N)])
    co = rms >= nguong_rms
    if co.sum() < 2:
        return []
    dau, cuoi = int(np.argmax(co)), len(co) - int(np.argmax(co[::-1])) - 1

    ra, dem = [], 0
    for v in co[dau:cuoi + 1]:
        if v:
            if dem:
                ra.append(dem * frame_ms)
            dem = 0
        else:
            dem += 1
    return ra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nguong", type=int, nargs="+", default=[400, 500, 600, 750])
    # Bỏ khoảng nghỉ QUÁ DÀI: đó là lúc khách ngồi nghe AI nói, không phải
    # nghỉ giữa câu. Không lọc thì chúng lấn át và mọi ngưỡng đều trông như
    # nhau (đo lần đầu ra 27.8% vs 23.5%, gần như bằng nhau vì lý do này).
    ap.add_argument("--toi-da", type=int, default=2000,
                    help="ms; dài hơn thì coi là chờ giữa lượt, không tính")
    a = ap.parse_args()

    import soundfile as sf

    from backend.services import phone_call_service as PS

    goc = PROJECT / "data" / "recordings"
    tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
    if not tep:
        print(f"  không thấy bản ghi nào trong {goc}")
        return 1

    tat_ca: list[float] = []
    print(f"\n  ngưỡng VAD tắt = {PS.VAD_RMS_OFF:.0f} | chỉ tính khoảng nghỉ "
          f"<= {a.toi_da}ms (dài hơn là chờ giữa lượt)\n")
    for f in tep:
        x, sr = sf.read(str(f), dtype="float32", always_2d=True)
        nghi = khoang_nghi(x[:, 0], sr, PS.VAD_RMS_OFF)
        if not nghi:
            continue
        nghi = [k for k in nghi if k <= a.toi_da]
        if not nghi:
            continue
        tat_ca += nghi
        print(f"  {f.name:<22} {len(nghi):>3} khoảng nghỉ, dài nhất "
              f"{max(nghi):>5.0f}ms")

    if not tat_ca:
        print("  không bản ghi nào có đủ tiếng khách để đo")
        return 1

    tat_ca.sort()
    n = len(tat_ca)
    print(f"\n  Tổng {n} khoảng nghỉ giữa câu, trên {len(tep)} bản ghi")
    for p in (50, 75, 90, 95, 99):
        print(f"    phân vị {p:>2}: {tat_ca[min(n-1, int(n*p/100))]:>5.0f}ms")

    print(f"\n  {'ngưỡng':>8}{'số lần CẮT LỜI':>18}{'tỉ lệ':>9}  ý nghĩa")
    print("  " + "-" * 70)
    for ng in sorted(a.nguong):
        cat = sum(1 for k in tat_ca if k >= ng)
        print(f"  {ng:>6}ms{cat:>16}{100*cat/n:>8.1f}%  "
              f"{'AI chen ngang ' + str(cat) + ' lần' if cat else 'không cắt lần nào'}")

    print("\n  'Cắt lời' = khoảng nghỉ GIỮA CÂU dài hơn ngưỡng, tức máy tưởng khách")
    print("  đã dứt lời trong khi họ còn đang nói tiếp.")
    print("  Lưu ý: bị cắt KHÔNG mất câu - `ghep_cau_bi_cat` nối phần sau vào phần")
    print("  trước. Cái mất là khách nghe AI chen ngang, nghe rất máy móc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
