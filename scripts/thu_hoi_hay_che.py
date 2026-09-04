"""Khách HỎI hay CHÊ: bộ thử cho cổng ngữ cảnh.

Chạy:
    .venv/bin/python scripts/thu_hoi_hay_che.py      (Mac)
    .venv\\python.exe scripts\\thu_hoi_hay_che.py    (Win)

Bắt buộc chạy lại sau khi đổi `vi_du` của nhóm chê trong tinh_huong_seed.json
hoặc đổi `TU_KHOA_CHU_DE` / `DIEU_KIEN_NGU_CANH`.

HAI TIÊU CHÍ, tiêu chí 2 là tuyệt đối:
  1. Phân đúng >= 18/23.
  2. Ở lượt bot CHƯA tư vấn chủ đề nào, KHÔNG câu nào được chấm thành chê -
     khách chưa nghe mức lãi thì không thể đang chê mức lãi.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_situation import (
    DIEU_KIEN_NGU_CANH, chon_tinh_huong, chuan_hoa, loc_theo_ngu_canh,
)

# (câu khách nói, chủ đề bot ĐÃ tư vấn, id mong đợi hoặc None = "miễn là không chê")
BO_THU = [
    # --- Hỏi, lượt đầu, bot chưa nói gì ---
    ("lãi suất bao nhiêu",                 set(),          "hoi_lai_suat"),
    ("lãi có cao không",                   set(),          "hoi_lai_suat"),
    ("lãi thế nào em",                     set(),          "hoi_lai_suat"),
    ("bên em lãi bao nhiêu phần trăm",     set(),          "hoi_lai_suat"),
    ("thế vay tối đa được bao nhiêu tiền", set(),          "hoi_han_muc"),

    # --- Chê, SAU khi bot đã tư vấn ---
    ("lãi cao thế",                        {"lai_suat"},   "che_lai_cao"),
    ("lãi cao quá em ơi",                  {"lai_suat"},   "che_lai_cao"),
    ("thế thì lãi cao rồi",                {"lai_suat"},   "che_lai_cao"),
    ("lãi vậy là cao đấy",                 {"lai_suat"},   "che_lai_cao"),
    ("sao lãi cao vậy",                    {"lai_suat"},   "che_lai_cao"),
    ("phí cao quá",                        {"phi"},        "che_phi_cao"),
    ("sao nhiều phí thế",                  {"phi"},        "che_phi_cao"),
    ("hạn mức thấp quá",                   {"han_muc"},    "che_han_muc_thap"),
    ("vay được có thế thôi à",             {"han_muc"},    "che_han_muc_thap"),

    # --- HỎI LẠI sau khi đã nghe: cổng mở rồi nhưng vẫn phải ra HỎI ---
    ("lãi suất bao nhiêu",                 {"lai_suat"},   "hoi_lai_suat"),
    ("lãi có cao không",                   {"lai_suat"},   "hoi_lai_suat"),
    ("nhắc lại lãi suất giúp anh",         {"lai_suat"},   "hoi_lai_suat"),

    # --- Cổng phải CHẶN: chưa tư vấn thì không thể là chê ---
    ("lãi cao thế",                        set(),          None),
    ("lãi cao quá",                        set(),          None),
    ("phí cao quá",                        set(),          None),
    # Câu CỤT - khách đang nói "không", tức HỎI. Đây là ca lật ngược ở biên 0.026.
    ("lãi cao kh",                         set(),          None),
    ("lãi cao",                            set(),          None),

    # --- So sánh: cố ý KHÔNG có điều kiện ---
    ("bên kia rẻ hơn",                     set(),          "so_sanh_ben_khac"),
]


def main() -> int:
    from backend.services.rag_service import RAGService
    rag = RAGService()
    rag.load()
    kho = json.loads((Path(__file__).resolve().parents[1]
                      / "data" / "tinh_huong_seed.json").read_text(encoding="utf-8"))
    kho_vec = {t["id"]: chuan_hoa(rag.embed(list(t["vi_du"])))
               for t in kho["tinh_huong"] if t.get("vi_du")}
    print(f"Kho: {len(kho_vec)} tình huống\n")

    dung = che_nham = 0
    for cau, da_tu_van, mong in BO_THU:
        q = chuan_hoa(rag.embed([cau]))[0]
        ra, diem = chon_tinh_huong(
            q, kho_vec, bo_qua=loc_theo_ngu_canh(DIEU_KIEN_NGU_CANH, da_tu_van))
        la_che = (ra or "").startswith("che_")
        ok = (ra == mong) if mong else not la_che
        dung += ok
        if not da_tu_van and la_che:
            che_nham += 1
        dau = "OK " if ok else "SAI"
        ctx = ",".join(sorted(da_tu_van)) or "-"
        print(f"{dau} {cau!r:36} [{ctx:9}] -> {str(ra):18} {diem:.3f}"
              f"{'' if ok else f'   (mong: {mong})'}")

    print(f"\nĐúng {dung}/{len(BO_THU)}")
    print(f"Chê nhầm khi bot chưa tư vấn gì: {che_nham} (phải là 0)")
    dat = dung >= 18 and che_nham == 0
    print("=> ĐẠT" if dat else "=> KHÔNG ĐẠT")
    return 0 if dat else 1


if __name__ == "__main__":
    raise SystemExit(main())
