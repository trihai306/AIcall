"""Do diem khop RAG de chon NGUONG: bao nhieu thi coi la "khong tim thay".

Vi sao can: hoi ve tiet kiem / bao hiem - hai san pham `knowledge/` KHONG co
tai lieu nao - thi RAG van tra ve tai lieu vay tin chap, roi luoi chan tien lay
so cua san pham do ap vao. Do 8 vong ngay 05-09-2026:

    khach: "gui tiet kiem toi thieu bao nhieu tien"
    AI   : "gui tiet kiem toi thieu 200 trieu dong a"   <- 200tr la han muc VAY

Chon nguong phai DO chu khong doan: qua cao thi mat ca tai lieu dung, qua thap
thi khong chan duoc gi.

Chay:  .venv\\python.exe scripts\\do_nguong_rag.py
"""
import asyncio
import sys
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.rag_service import RAGService  # noqa: E402

# Cau hoi CO tai lieu that su tra loi duoc
CO = [
    "lãi suất vay tín chấp bao nhiêu",
    "hạn mức vay tín chấp bao nhiêu",
    "thủ tục vay tín chấp gồm những gì",
    "vay mua nhà lãi suất bao nhiêu",
    "thẻ tín dụng hạn mức bao nhiêu",
    "vay tín chấp là gì",
    "điều kiện vay tín chấp",
    "lãi suất bao nhiêu",
    "hạn mức được bao nhiêu",
    "thủ tục như nào",
]
# Cau hoi KHONG co tai lieu nao trong knowledge/
KHONG = [
    "gửi tiết kiệm tối thiểu bao nhiêu tiền",
    "bảo hiểm nhân thọ đóng bao nhiêu một năm",
    "sổ tiết kiệm mở tối thiểu bao nhiêu",
    "gói bảo hiểm rẻ nhất giá bao nhiêu",
    "lãi suất gửi tiết kiệm kỳ hạn 6 tháng",
    "mở tài khoản chứng khoán thế nào",
    "phí chuyển tiền quốc tế bao nhiêu",
    "vàng hôm nay giá bao nhiêu",
]


# Pipeline that NEO san pham cua phien vao truy van (`_truy_van_rag`), nen phai
# do ca hai chieu - khong neo thi so do khong phai bo canh that.
NEO = "vay tín chấp"


async def main():
    rag = RAGService()
    rag.load()
    ket = {}
    for nhan, ds in (("CO tai lieu", CO), ("KHONG co tai lieu", KHONG)):
        diem = []
        print(f"\n=== {nhan} ===")
        for q in ds:
            _, ct = await rag.retrieve_chi_tiet(q, top_k=2)
            cao = max((c["diem"] for c in ct if c["diem"] is not None), default=None)
            _, ct2 = await rag.retrieve_chi_tiet(f"{NEO} {q}", top_k=2, san_pham=NEO)
            cao2 = max((c["diem"] for c in ct2 if c["diem"] is not None), default=None)
            diem.append(cao2)
            nguon = ct2[0]["nguon"] if ct2 else "?"
            print(f"  khong neo={cao if cao is not None else '?':>6}  "
                  f"CO NEO={cao2 if cao2 is not None else '?':>6}  "
                  f"{q[:40]:<40} <- {nguon}")
        ket[nhan] = [d for d in diem if d is not None]   # do tren ban CO NEO

    print("\n" + "=" * 62)
    for nhan, ds in ket.items():
        if ds:
            print(f"{nhan:<20} min={min(ds):.3f}  max={max(ds):.3f}  "
                  f"tb={sum(ds)/len(ds):.3f}")
    if all(ket.values()):
        san = min(ket["CO tai lieu"])
        tran = max(ket["KHONG co tai lieu"])
        print(f"\nthap nhat cua nhom CO   : {san:.3f}")
        print(f"cao nhat  cua nhom KHONG: {tran:.3f}")
        print("-> " + (f"TACH DUOC, nguong dat giua: {(san+tran)/2:.3f}"
                       if san > tran else
                       "KHONG TACH DUOC bang mot nguong - hai nhom chong nhau"))

asyncio.run(main())
