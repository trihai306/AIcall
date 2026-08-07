"""Buổi train dạy model TỪ NÀO? Đếm token theo vai trong dữ liệu huấn luyện.

`train_lora.py` đưa cả đoạn hội thoại đã áp khuôn mẫu vào `dataset_text_field`
và KHÔNG che nhãn (không có `train_on_responses_only`). Nghĩa là model học sinh
ra TOÀN BỘ chuỗi: luật hệ thống, câu của khách, rồi mới tới câu trả lời.

Hệ quả đo được bằng tỉ lệ token:
  - Phần lớn tín hiệu học rơi vào LUẬT HỆ THỐNG - đoạn lặp y hệt ở mọi mẫu.
    Model thuộc lòng bài luật thay vì học tuân theo nó.
  - Model học SINH RA CÂU KHÁCH. Đây chính là lý do nó thỉnh thoảng hỏi ngược
    lại khách ("Lãi suất vay tín chấp hiện tại là bao nhiêu ạ?").
  - Câu trả lời - thứ DUY NHẤT cần học - chỉ chiếm một phần nhỏ.

Script đếm chính xác tỉ lệ đó trên bộ dữ liệu thật.

Chạy TRÊN MÁY WIN:  python scripts\\do_phan_bo_loss_train.py
"""

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEP = [PROJECT / "data" / "training" / "merged_dataset.jsonl",
       PROJECT / "data" / "training" / "_de_rieng" / "dataset_co_tai_lieu.jsonl"]


def main() -> int:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")

    for f in TEP:
        if not f.exists():
            continue
        n = 0
        t_sys = t_user = t_asst = 0
        trung = {}
        for dong in f.read_text(encoding="utf-8", errors="replace").splitlines():
            dong = dong.strip()
            if not dong:
                continue
            o = json.loads(dong)
            msgs = o.get("messages") or []
            n += 1
            khoa = json.dumps(msgs, ensure_ascii=False)
            trung[khoa] = trung.get(khoa, 0) + 1
            for m in msgs:
                d = len(tok(m.get("content", "")).input_ids)
                vai = m.get("role")
                if vai == "system":
                    t_sys += d
                elif vai == "user":
                    t_user += d
                elif vai == "assistant":
                    t_asst += d
        tong = t_sys + t_user + t_asst or 1
        lap = sum(v for v in trung.values() if v > 1)
        print(f"\n  {f.name}: {n} mẫu, {len(trung)} mẫu KHÁC NHAU"
              f" ({lap} bản ghi nằm trong nhóm trùng)")
        print(f"    luật hệ thống : {t_sys:>8} token  {t_sys/tong*100:5.1f}%")
        print(f"    câu của khách : {t_user:>8} token  {t_user/tong*100:5.1f}%")
        print(f"    CÂU TRẢ LỜI   : {t_asst:>8} token  {t_asst/tong*100:5.1f}%  <- thứ DUY NHẤT cần học")
        print(f"    -> {100 - t_asst/tong*100:.1f}% tín hiệu học đổ vào phần model KHÔNG BAO GIỜ nên sinh ra")

    print("\n  Cách sửa: `train_on_responses_only(trainer, ...)` của Unsloth, che")
    print("  nhãn phần system+user để loss chỉ tính trên câu trả lời.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
