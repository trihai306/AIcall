"""Buổi fine-tune F5 có THẬT SỰ đổi trọng số không, hay chỉ chép lại model gốc?

Bẫy đã mắc một lần (xem bộ nhớ f5tts-finetune-ba-loi-chan): `trainer.py` đọc
`start_update` từ checkpoint, mà bản ViVoice có `update=540000` nên vòng lặp
train KHÔNG CHẠY LẦN NÀO, script vẫn in "hoàn thành" và lưu ra một file mới -
chính là bản sao của model gốc. Nhìn từ ngoài y hệt một buổi train thành công:
có file, có dung lượng, có ngày giờ mới.

Cách duy nhất để biết: mở cả hai checkpoint ra và SO TRỌNG SỐ.

    python scripts\\kiem_train_f5_that.py
    python scripts\\kiem_train_f5_that.py --goc <ckpt gốc> --moi <ckpt sau train>
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOC = PROJECT / "models" / "tts" / "F5-TTS-Vietnamese-ViVoice" / "model_last.pt"
MOI = PROJECT / "models" / "tts" / "finetuned" / "giong_nam" / "model_last.pt"


def nap(p: Path):
    import torch
    return torch.load(str(p), map_location="cpu", weights_only=False)


def main() -> int:
    import torch

    ap = argparse.ArgumentParser()
    ap.add_argument("--goc", default=str(GOC))
    ap.add_argument("--moi", nargs="+", default=[str(MOI)])
    a = ap.parse_args()

    g = Path(a.goc)
    if not g.exists():
        print(f"  không thấy checkpoint gốc: {g}")
        return 1
    print(f"\n  gốc: {g}")
    ck_g = nap(g)
    sd_g = ck_g.get("ema_model_state_dict") or ck_g.get("model_state_dict") or ck_g
    print(f"    update = {ck_g.get('update', ck_g.get('step', '<không có>'))}"
          f" | {len(sd_g)} tensor")
    hong = 0

    for m in a.moi:
        p = Path(m)
        if not p.exists():
            print(f"\n  không thấy {p}")
            continue
        ck = nap(p)
        sd = ck.get("ema_model_state_dict") or ck.get("model_state_dict") or ck
        print(f"\n  so với: {p}")
        print(f"    update = {ck.get('update', ck.get('step', '<không có>'))}"
              f" | {len(sd)} tensor")

        chung = [k for k in sd_g if k in sd and hasattr(sd[k], "shape")]
        if not chung:
            print("    KHÔNG có tensor nào trùng tên - hai checkpoint khác cấu trúc")
            continue

        khac = 0
        ty_le = []          # lệch TƯƠNG ĐỐI so với độ lớn của chính trọng số
        for k in chung:
            a_t, b_t = sd_g[k], sd[k]
            # Bỏ đại lượng vô hướng như `step`: nó lệch 1260 và làm hỏng mọi
            # con số trung bình, che mất mức đổi thật của trọng số.
            if a_t.shape != b_t.shape or a_t.ndim == 0 or not a_t.is_floating_point():
                if a_t.shape == b_t.shape and not torch.equal(a_t, b_t):
                    khac += 1
                continue
            d = (a_t.float() - b_t.float()).abs()
            if d.max().item() > 0:
                khac += 1
            goc_lon = a_t.float().abs().mean().item() or 1e-12
            ty_le.append(d.mean().item() / goc_lon)

        print(f"    tensor khác nhau: {khac}/{len(chung)}")
        if ty_le:
            ty_le.sort()
            tb = sum(ty_le) / len(ty_le)
            print(f"    mức đổi tương đối: trung bình {tb*100:.2f}%"
                  f" | trung vị {ty_le[len(ty_le)//2]*100:.2f}%"
                  f" | lớn nhất {ty_le[-1]*100:.2f}%")
        # CHỈ coi là HỎNG khi KHÔNG tensor nào đổi - đó mới là "train chạy 0
        # bước". Đổi ÍT là chuyện bình thường của một buổi train ngắn: 42 bước
        # cho ra 0.01%, 1260 bước cho ra 0.19%. Bản đầu tôi gộp hai thứ này vào
        # cùng một mã lỗi nên chặn nhầm một buổi train chạy đúng.
        if khac == 0:
            print("    >>> Y HỆT MODEL GỐC. Buổi train KHÔNG chạy bước nào.")
            hong += 1
        elif ty_le and ty_le[len(ty_le)//2] < 1e-4:
            print("    >>> đã đổi, nhưng RẤT ÍT - đủ để biết train có chạy,")
            print("        chưa đủ để nghe ra khác biệt. Cần train dài hơn.")
        else:
            print("    >>> ĐÃ ĐỔI THẬT. Buổi train có chạy.")
    # Mã thoát KHÁC 0 khi có checkpoint không đổi: `train.ps1` dựa vào đó để
    # dừng hẳn thay vì in "Train xong" cho một buổi train rỗng.
    return 1 if hong else 0


if __name__ == "__main__":
    raise SystemExit(main())
