"""Đổi chữ số trong dataset train thành chữ tiếng Việt.

Vì sao cần: system prompt lúc chạy thật bắt "viết số thành chữ khi nói tiền,
ngày tháng" - vì đây là hệ thống gọi điện, TTS đọc "6.5%" ra sẽ sai. Nhưng model
học theo DATA chứ không theo system prompt: dataset còn chữ số thì model sinh ra
chữ số, và system prompt có ép cỡ nào cũng thua.

Đo được trên dataset 284 mẫu: 48 mẫu (17%) còn chữ số, và model train từ đó
tụt từ 7/8 xuống 3/8 điểm phong cách so với bản dataset sạch số.

    python training/llm/so_thanh_chu.py --vao data/training/x.jsonl --xem-truoc
    python training/llm/so_thanh_chu.py --vao data/training/x.jsonl --ra data/training/x_sach.jsonl
"""
import argparse
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_HANG_DON_VI = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _doc_ba_so(n: int, day_du: bool) -> str:
    """Đọc cụm 3 chữ số. day_du=True thì đọc cả 'không trăm' cho cụm giữa."""
    tram, chuc, dv = n // 100, (n // 10) % 10, n % 10
    ra = []
    if tram or day_du:
        ra += [_HANG_DON_VI[tram], "trăm"]
    if chuc == 0:
        if dv and (tram or day_du):
            ra += ["lẻ", _HANG_DON_VI[dv]]
        elif dv:
            ra += [_HANG_DON_VI[dv]]
    elif chuc == 1:
        ra += ["mười"]
        if dv == 5:
            ra += ["lăm"]           # mười lăm, không phải "mười năm"
        elif dv:
            ra += [_HANG_DON_VI[dv]]
    else:
        ra += [_HANG_DON_VI[chuc], "mươi"]
        if dv == 1:
            ra += ["mốt"]           # hai mươi mốt
        elif dv == 5:
            ra += ["lăm"]           # hai mươi lăm
        elif dv:
            ra += [_HANG_DON_VI[dv]]
    return " ".join(ra)


def doc_so_nguyen(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + doc_so_nguyen(-n)

    nhom, i = [], 0
    while n > 0:
        nhom.append(n % 1000)
        n //= 1000
        i += 1

    ten = ["", "nghìn", "triệu", "tỷ"]
    ra = []
    for idx in range(len(nhom) - 1, -1, -1):
        cum = nhom[idx]
        if cum == 0:
            continue
        # Cụm không phải cụm đầu thì đọc đầy đủ ("một trăm lẻ năm nghìn")
        ra.append(_doc_ba_so(cum, day_du=(idx != len(nhom) - 1)))
        if idx < len(ten) and ten[idx]:
            ra.append(ten[idx])
    return " ".join(x for x in ra if x)


def doc_so(chuoi: str) -> str:
    """Đọc một chuỗi số, có thể kèm phần thập phân: '6.5' -> 'sáu phẩy năm'."""
    chuoi = chuoi.replace(",", "")          # 1,000 -> 1000
    if "." in chuoi:
        nguyen, thap = chuoi.split(".", 1)
        phan_thap = " ".join(_HANG_DON_VI[int(c)] for c in thap if c.isdigit())
        return f"{doc_so_nguyen(int(nguyen or 0))} phẩy {phan_thap}"
    return doc_so_nguyen(int(chuoi))


# Đơn vị đi liền sau số, đọc thành chữ luôn cho tự nhiên.
_DON_VI = [
    (re.compile(r"(\d[\d.,]*)\s*%"), lambda m: f"{doc_so(m.group(1))} phần trăm"),
    (re.compile(r"(\d[\d.,]*)\s*đ\b", re.I), lambda m: f"{doc_so(m.group(1))} đồng"),
]
_SO_TRAN = re.compile(r"\d[\d.,]*\d|\d")


def chuyen(text: str) -> str:
    """Đổi mọi chữ số trong câu thành chữ."""
    for mau, thay in _DON_VI:
        text = mau.sub(thay, text)
    text = _SO_TRAN.sub(lambda m: doc_so(m.group(0)), text)
    return re.sub(r"\s{2,}", " ", text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vao", required=True)
    ap.add_argument("--ra", default=None, help="Không truyền thì ghi đè file vào")
    ap.add_argument("--xem-truoc", action="store_true", help="Chỉ in ra, không ghi")
    args = ap.parse_args()

    vao = Path(args.vao)
    dong, doi = [], []
    for i, l in enumerate(vao.read_text(encoding="utf-8").splitlines(), 1):
        l = l.strip()
        if not l:
            continue
        obj = json.loads(l)
        for m in obj.get("messages", []):
            if m.get("role") != "assistant":
                continue
            cu = m["content"]
            if re.search(r"\d", cu):
                moi = chuyen(cu)
                if moi != cu:
                    doi.append((i, cu, moi))
                    m["content"] = moi
        dong.append(json.dumps(obj, ensure_ascii=False))

    print(f"{len(dong)} mẫu | {len(doi)} câu trả lời còn chữ số\n")
    for i, cu, moi in doi[:12]:
        print(f"  dòng {i}")
        print(f"    trước: {cu[:110]}")
        print(f"    sau  : {moi[:110]}")
    if len(doi) > 12:
        print(f"  ... còn {len(doi)-12} câu")

    if args.xem_truoc:
        print("\n(xem trước - chưa ghi file nào)")
        return

    ra = Path(args.ra) if args.ra else vao
    ra.write_text("\n".join(dong) + "\n", encoding="utf-8")
    print(f"\n[OK] đã ghi {len(dong)} mẫu -> {ra}")


if __name__ == "__main__":
    main()
