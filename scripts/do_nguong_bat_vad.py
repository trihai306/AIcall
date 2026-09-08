"""Sàn ngưỡng BẬT của VAD nên để bao nhiêu? Đo trên toàn bộ bản ghi cuộc gọi thật.

Sinh ra từ cuộc 08c0d3e0 (07-09-2026): khách hỏi "lãi suất bao nhiêu" mà máy không
mở lượt, phải hỏi lại lần hai. Script này trả lời hai câu, mỗi câu một bảng:

  1. Mỗi sàn BỎ SÓT bao nhiêu phần trăm lời khách thật?
  2. Mỗi sàn MỞ THÊM bao nhiêu lượt (tức cái giá phải trả)?

Chạy:  .venv/python.exe scripts/do_nguong_bat_vad.py

BẪY đã mắc khi viết script này, đừng lặp lại:

  - Kênh TRÁI là khách, kênh PHẢI là AI. Đừng đoán theo mức: kênh khách TO HƠN
    (có cả tiếng chuông chờ). Cách xác định chắc chắn: cộng thời lượng có tiếng
    của từng kênh rồi đối chiếu với tổng thời lượng TTS ghi trong backend.log.

  - Gom cụm "một lời khách" phải CHỊU ĐƯỢC CHỖ TRŨNG giữa hai âm tiết. Bản đầu
    tiên đòi liên tục trên 250 nên loại sạch đúng những lời nói nhỏ cần khảo sát,
    và ra kết luận ngược: "700 chỉ bỏ sót 2/482". Gom với khe hở 160ms thì ra
    37/454 - gấp mười tám lần.

  - Phải loại đoạn AI đang nói, không thì tiếng AI vọng vào kênh khách bị đếm
    thành lời khách.
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KHUNG_MS = 20
SILENCE_END_MS, MIN_TURN_MS, ON_FRAMES = 1000, 130, 4
HE_SO_ON, HE_SO_TAT, NGUONG_TAT = 3.0, 1.8, 500.0
SAN = (300, 350, 400, 450, 500, 600, 700)


def rms_tung_khung(x, sr):
    h = int(sr * KHUNG_MS / 1000)
    n = len(x) // h * h
    return np.sqrt(np.mean(x[:n].reshape(-1, h) ** 2, axis=1)) * 32768


def mo_phong_luot(R, san, nen):
    """Mô phỏng đúng máy trạng thái trong `phone_call_service._read_loop`."""
    on = max(san, nen * HE_SO_ON)
    tat = max(NGUONG_TAT, nen * HE_SO_TAT)
    sil_can = SILENCE_END_MS // KHUNG_MS
    dang_noi = False
    streak = im = dau = 0
    ra = []
    for i, v in enumerate(R):
        if not dang_noi:
            streak = streak + 1 if v >= on else 0
            if streak >= ON_FRAMES:
                dang_noi, streak, im, dau = True, 0, 0, i
        elif v < tat:
            im += 1
            if im >= sil_can:
                dang_noi = False
                if (i - im - dau) * KHUNG_MS >= MIN_TURN_MS:
                    ra.append((dau, i - im))
        else:
            im = 0
    return ra


def cum_loi_khach(KH, AI):
    """Những đoạn NGHI LÀ một lời khách thật, để làm mẫu số cho tỉ lệ bỏ sót.

    Khe hở 160ms: chỗ trũng giữa hai âm tiết vẫn thuộc cùng một lời. Đòi đỉnh
    >= 500 để loại tiếng nền; loại đoạn AI đang nói để khỏi đếm tiếng vọng.
    """
    idx = np.where(KH >= 150)[0]
    if len(idx) == 0:
        return []
    cum, a, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > 8:
            cum.append((a, p + 1))
            a = i
        p = i
    cum.append((a, p + 1))
    return [KH[i:j] for i, j in cum
            if (j - i) >= 20 and KH[i:j].max() >= 500
            and AI[max(0, i - 5):j + 5].mean() <= 25]


def chuoi_dai_nhat(seg, nguong):
    best = cur = 0
    for v in seg:
        cur = cur + 1 if v >= nguong else 0
        best = max(best, cur)
    return best


def main():
    thu_muc = sys.argv[1] if len(sys.argv) > 1 else os.path.join(GOC, "data", "recordings")
    files = sorted(glob.glob(os.path.join(thu_muc, "**", "*.opus"), recursive=True))
    if not files:
        print(f"Không tìm thấy bản ghi nào trong {thu_muc}")
        return

    loi_khach, so_luot = [], {s: 0 for s in SAN}
    nen_tat_ca, n_file = [], 0
    for f in files:
        try:
            x, sr = sf.read(f, always_2d=True)
        except Exception as e:
            print(f"  bỏ qua {os.path.basename(f)}: {e}")
            continue
        if x.shape[1] < 2:
            continue
        KH, AI = rms_tung_khung(x[:, 0], sr), rms_tung_khung(x[:, 1], sr)
        nen = float(np.percentile(KH, 20))
        nen_tat_ca.append(nen)
        loi_khach += cum_loi_khach(KH, AI)
        for s in SAN:
            so_luot[s] += len(mo_phong_luot(KH, s, nen))
        n_file += 1

    print(f"{n_file} bản ghi, {len(loi_khach)} lời khách thật")
    print(f"nền kênh: trung vị {np.median(nen_tat_ca):.0f}, "
          f"p90 {np.percentile(nen_tat_ca, 90):.0f}, max {max(nen_tat_ca):.0f}")
    print("  -> nhánh `nền × 3` chỉ vượt sàn khi sàn dưới "
          f"{max(nen_tat_ca) * HE_SO_ON:.0f}\n")

    print("sàn | mở được lời khách | bỏ sót | tổng lượt mở (cái giá)")
    for s in SAN:
        mo = sum(1 for seg in loi_khach if chuoi_dai_nhat(seg, s) >= ON_FRAMES)
        print(f"{s:4d} | {mo:4d}/{len(loi_khach)} ({100 * mo / len(loi_khach):5.1f}%) "
              f"| {len(loi_khach) - mo:4d}   | {so_luot[s]:5d}")

    sot700 = [seg for seg in loi_khach if chuoi_dai_nhat(seg, 700) < ON_FRAMES]
    if sot700:
        d = np.array([seg.max() for seg in sot700])
        print(f"\n{len(sot700)} lời bị sàn 700 bỏ sót - đỉnh: min {d.min():.0f}, "
              f"trung vị {np.median(d):.0f}, max {d.max():.0f}")
        for s in (400, 500, 600):
            cuu = sum(1 for seg in sot700 if chuoi_dai_nhat(seg, s) >= ON_FRAMES)
            print(f"  hạ về {s} cứu được {cuu}/{len(sot700)}")


if __name__ == "__main__":
    main()
