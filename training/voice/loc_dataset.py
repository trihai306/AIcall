"""Lọc dataset giọng trước khi train: loại đoạn có transcript không đáng tin.

Vì sao cần: transcript của dataset thường do ASR sinh, mà README đã cảnh báo
"transcript sai = giọng train ra đọc sai". Soát tay 200-300 file thì gần như
không ai làm, nên thực tế là train luôn với dữ liệu bẩn.

Script này không thay người nghe, nhưng loại được những đoạn mà CHÍNH mô hình
nhận dạng cũng không chắc - đó là nhóm dễ sai nhất. Với clone giọng, một dataset
nhỏ mà sạch cho kết quả tốt hơn dataset to mà lẫn lời sai.

Đoạn bị loại được CHUYỂN sang thư mục <dataset>_loai, không xoá.

    python training/voice/loc_dataset.py                  # xem trước, không đụng file
    python training/voice/loc_dataset.py --thuc-hien      # chuyển thật
"""
import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET = PROJECT_DIR / "tools" / "F5-TTS-Vietnamese" / "data" / "your_dataset"

# Ngưỡng lấy theo cùng bộ số đã đo cho STT (backend/services/stt_service.py):
# giọng thật quanh -0.02, nhiễu từ -0.24 trở xuống.
NGUONG_TU_TIN = -0.30
NGUONG_KHONG_TIENG = 0.6
# F5-TTS học tốt nhất trên đoạn 2-15s. Ngắn quá thì không đủ ngữ điệu, dài quá
# thì một lỗi transcript làm hỏng cả đoạn dài.
GIAY_TOI_THIEU = 1.5
GIAY_TOI_DA = 20.0
# Nói quá chậm hoặc quá nhanh so với transcript = nhiều khả năng nghe sót chữ.
TU_MOI_GIAY_MIN = 1.2
TU_MOI_GIAY_MAX = 7.0

_RAC = re.compile(r"^(hãy subscribe|subscribe|cảm ơn( các bạn)?( đã xem)?"
                  r"|ghiền mì gõ|hết rồi|xin chào|\.|…|\s)*$", re.IGNORECASE)


def soi(wav: Path, stt_server: str) -> tuple[list[str], dict]:
    """Trả (danh sách lý do loại, số đo). Rỗng nghĩa là giữ."""
    import httpx
    import soundfile as sf

    txt_path = wav.with_suffix(".txt")
    text = txt_path.read_text(encoding="utf-8").strip() if txt_path.exists() else ""
    giay = sf.info(str(wav)).duration

    r = httpx.post(f"{stt_server}/inference",
                   files={"file": ("a.wav", wav.read_bytes(), "audio/wav")},
                   data={"language": "vi", "response_format": "verbose_json",
                         "temperature": "0"},
                   timeout=90.0)
    kq = r.json()
    doan = kq.get("segments") or []
    tu_tin = min((d.get("avg_logprob", 0.0) for d in doan), default=0.0)
    khong_tieng = max((d.get("no_speech_prob", 0.0) for d in doan), default=0.0)

    so_tu = len(text.split())
    tu_giay = so_tu / giay if giay > 0 else 0

    ly_do = []
    if not text:
        ly_do.append("transcript rỗng")
    elif so_tu < 2:
        ly_do.append(f"chỉ {so_tu} chữ")
    if _RAC.match(text):
        ly_do.append("khớp mẫu câu ASR hay bịa")
    if tu_tin <= NGUONG_TU_TIN:
        ly_do.append(f"độ tin thấp {tu_tin:.2f}")
    if khong_tieng >= NGUONG_KHONG_TIENG:
        ly_do.append(f"no_speech {khong_tieng:.2f}")
    if giay < GIAY_TOI_THIEU:
        ly_do.append(f"quá ngắn {giay:.1f}s")
    if giay > GIAY_TOI_DA:
        ly_do.append(f"quá dài {giay:.1f}s")
    if text and not (TU_MOI_GIAY_MIN <= tu_giay <= TU_MOI_GIAY_MAX):
        ly_do.append(f"nhịp bất thường {tu_giay:.1f} chữ/giây")

    return ly_do, {"giay": giay, "tu_tin": tu_tin, "so_tu": so_tu, "text": text}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--stt-server", default="http://localhost:8178")
    ap.add_argument("--thuc-hien", action="store_true",
                    help="Chuyển file bị loại đi thật. Không có cờ này chỉ xem trước.")
    args = ap.parse_args()

    d = Path(args.dataset)
    wavs = sorted(d.glob("*.wav"))
    if not wavs:
        sys.exit(f"[ERROR] Không có file wav nào trong {d}")

    thu_muc_loai = d.parent / (d.name + "_loai")
    giu, loai, tong_giay_giu, tong_giay_loai = [], [], 0.0, 0.0

    print(f"Soi {len(wavs)} đoạn trong {d.name}\n")
    for i, w in enumerate(wavs, 1):
        try:
            ly_do, so = soi(w, args.stt_server)
        except Exception as e:
            print(f"  [WARN] {w.name}: không soi được ({e}) - giữ lại")
            giu.append(w)
            continue
        if ly_do:
            loai.append((w, ly_do, so))
            tong_giay_loai += so["giay"]
        else:
            giu.append(w)
            tong_giay_giu += so["giay"]
        if i % 50 == 0:
            print(f"  ... {i}/{len(wavs)}")

    print(f"\n=== KẾT QUẢ ===")
    print(f"  giữ  : {len(giu):3d} đoạn · {tong_giay_giu/60:.1f} phút")
    print(f"  loại : {len(loai):3d} đoạn · {tong_giay_loai/60:.1f} phút")

    if loai:
        print(f"\n  Đoạn bị loại (tối đa 25 dòng):")
        for w, ly_do, so in loai[:25]:
            print(f"    {w.name}  {so['giay']:.1f}s  [{'; '.join(ly_do)}]")
            print(f"        {so['text'][:80]}")
        if len(loai) > 25:
            print(f"    ... còn {len(loai)-25} đoạn")

    # F5-TTS cần tối thiểu ~10 phút để giọng nhận ra được (theo README).
    if tong_giay_giu < 10 * 60:
        print(f"\n  [CẢNH BÁO] Chỉ còn {tong_giay_giu/60:.1f} phút sau khi lọc, "
              f"dưới mốc 10 phút. Giọng train ra sẽ chưa mượt.")

    if not args.thuc_hien:
        print(f"\n  (xem trước - chưa đụng file nào. Thêm --thuc-hien để chuyển thật)")
        return

    if loai:
        thu_muc_loai.mkdir(parents=True, exist_ok=True)
        for w, _, _ in loai:
            w.rename(thu_muc_loai / w.name)
            t = w.with_suffix(".txt")
            if t.exists():
                t.rename(thu_muc_loai / t.name)
        print(f"\n  Đã chuyển {len(loai)} đoạn -> {thu_muc_loai}")
    print(f"  Dataset còn {len(giu)} đoạn, {tong_giay_giu/60:.1f} phút - sẵn sàng train.")


if __name__ == "__main__":
    main()
