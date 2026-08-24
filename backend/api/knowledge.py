"""Quản lý tài liệu tri thức từ giao diện web.

Đây là thứ AI ĐỌC ĐỂ TƯ VẤN. Trước đây nó chỉ là mấy file `.md` nằm trong
`knowledge/`, muốn sửa phải vào tận máy chủ - nên hệ thống chạy suốt bằng bốn
file mẫu của "Ngân hàng ABC" với lãi suất 7.9% bịa ra. Mọi con số bot đọc cho
khách đều lấy từ đây, nên không sửa được từ giao diện là lỗi nghiêm trọng chứ
không phải thiếu tiện nghi.

NHẬN CẢ BẢNG TÍNH: dữ liệu ngân hàng thật thường nằm trong Excel (biểu lãi suất,
biểu phí). Chuyển sang bảng markdown rồi nạp, thay vì bắt người dùng gõ lại tay.

KHÁC "Nguồn dữ liệu": bên kia nối tới file/CSDL NGOÀI và nạp lại theo lịch, dùng
cho bảng lớn hay đổi. Ở đây là tài liệu tĩnh của chính hệ thống - mô tả sản
phẩm, điều kiện, câu hỏi thường gặp.
"""

import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from backend.core.knowledge_rules import (MAU, bat_dau_giua_cau, cat_ngang_bang,
                                          soi_manh, soi_tai_lieu)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

GOC = Path("./knowledge")

# Thư mục cho phép. KHÔNG nhận tên thư mục tuỳ ý từ client: nó ghép thẳng vào
# đường dẫn file, nhận bừa là mở đường ghi đè file bất kỳ trên máy.
#
# `products` có ý nghĩa ĐẶC BIỆT, đừng đổi tên: RAGService._mat_na_loc chỉ
# lọc mảnh nằm trong thư mục này. Tài liệu sản phẩm đặt sai chỗ sẽ không được lọc,
# và bot lại đọc lãi suất của sản phẩm khác cho khách.
NHOM = {
    "products": "Sản phẩm — mỗi sản phẩm một file, dùng để lọc theo sản phẩm khi tư vấn",
    "faq": "Câu hỏi thường gặp",
    "chinh_sach": "Chính sách, điều kiện, quy định chung",
}

DUOI_VAN_BAN = {".md", ".txt"}
DUOI_BANG = {".csv", ".xlsx", ".xls"}
_TRAN_BYTE = 10 * 1024 * 1024


def _rag():
    """Import trễ: `backend.main` import ngược lại module này lúc dựng router."""
    try:
        from backend.main import app_state
        return app_state.rag
    except Exception:
        return None


def _ten_an_toan(ten: str) -> str:
    """Về tên file trần, chỉ chữ-số-gạch. Rỗng nghĩa là không hợp lệ."""
    ten = Path(ten.replace("\\", "/")).name          # bỏ mọi phần thư mục
    goc = re.sub(r"\.(md|txt|csv|xlsx|xls)$", "", ten, flags=re.I)
    goc = re.sub(r"[^0-9A-Za-z_-]+", "_", goc).strip("_")
    return goc[:60]


def _duong_dan(nhom: str, ten: str) -> Path | None:
    if nhom not in NHOM:
        return None
    goc = _ten_an_toan(ten)
    if not goc:
        return None
    p = (GOC / nhom / f"{goc}.md").resolve()
    # Chốt chặn cuối: kể cả khi hai bước trên hụt, đường dẫn vẫn phải nằm trong
    # thư mục tri thức.
    try:
        p.relative_to(GOC.resolve())
    except ValueError:
        return None
    return p


def _cac_dang_nguon(p: Path) -> list[str]:
    """Mọi dạng chuỗi `source` mà cùng một file có thể mang trong RAG.

    ChromaDB khớp `where={"source": ...}` bằng SO CHUỖI CHÍNH XÁC, không hiểu
    đường dẫn. Mà file này được nạp từ hai chỗ với hai dạng khác nhau:
        khởi động   `ingest_directory("./knowledge")` -> "knowledge/products/x.md"
        từ đây      đường tuyệt đối                   -> "C:\\duan\\...\\x.md"
    Chỉ xử một dạng thì: đếm ra 0 mảnh (báo nhầm "AI chưa đọc được"), và xoá
    không sạch nên sửa tài liệu xong RAG vẫn trả về CẢ BẢN CŨ - đúng kiểu lỗi
    khiến bot đọc lãi suất cũ cho khách.
    """
    ten = f"{p.parent.name}/{p.name}"
    return [
        str(p),
        str(p.resolve()),
        f"knowledge/{ten}",
        f"./knowledge/{ten}",
        str(Path("knowledge") / p.parent.name / p.name),
    ]


def _dem_manh(p: Path) -> int:
    rag = _rag()
    if rag is None:
        return 0
    tong = 0
    for src in dict.fromkeys(_cac_dang_nguon(p)):
        tong += rag.dem_theo_nguon(src)
    return tong


def _dem_soi(p: Path) -> dict:
    kq = soi_nhanh(p)
    return {"so_loi": len(kq["loi"]), "so_canh_bao": len(kq["canh_bao"])}


def _nap_lai_mot_tep(p: Path) -> int:
    """Gỡ mảnh cũ của file này rồi nạp lại. Trả về số mảnh sau khi nạp."""
    rag = _rag()
    if rag is None:
        return 0
    for src in dict.fromkeys(_cac_dang_nguon(p)):
        rag.xoa_theo_nguon(src)
    src = str(p.resolve())
    noi_dung = p.read_text(encoding="utf-8", errors="replace")
    if noi_dung.strip():
        rag.ingest_text(noi_dung, doc_id=p.stem, metadata={"source": src})
    return rag.dem_theo_nguon(src)


def _bang_sang_markdown(raw: bytes, duoi: str, ten: str) -> str:
    """Excel/CSV -> bảng markdown. Giữ nguyên chữ trong ô, không diễn giải."""
    import io

    import pandas as pd

    if duoi == ".csv":
        # utf-8-sig: file CSV xuất từ Excel trên Windows luôn có BOM, đọc bằng
        # utf-8 trần thì tên cột đầu tiên dính "﻿" và không khớp gì cả.
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="cp1258")
    else:
        df = pd.read_excel(io.BytesIO(raw))

    df = df.fillna("")
    if len(df) > 2000:
        df = df.head(2000)
    dong = ["# " + ten, ""]
    dong.append("| " + " | ".join(str(c) for c in df.columns) + " |")
    dong.append("|" + "|".join(["---"] * len(df.columns)) + "|")
    for _, r in df.iterrows():
        dong.append("| " + " | ".join(str(v).replace("|", "/") for v in r) + " |")
    return "\n".join(dong) + "\n"


# --- đọc -----------------------------------------------------------------------

@router.get("")
async def danh_sach():
    rag = _rag()
    tai_lieu = []
    for nhom in NHOM:
        thu_muc = GOC / nhom
        if not thu_muc.exists():
            continue
        for p in sorted(thu_muc.glob("*.md")) + sorted(thu_muc.glob("*.txt")):
            st = p.stat()
            tai_lieu.append({
                "ten": p.stem,
                "nhom": nhom,
                "tep": p.name,
                "kich_thuoc": st.st_size,
                "sua_doi": st.st_mtime,
                # Số mảnh trong RAG: 0 nghĩa là file có trên đĩa nhưng AI CHƯA
                # đọc được nó - phải bấm "Nạp lại". Không hiện ra thì người dùng
                # sửa xong tưởng đã xong, mà bot vẫn trả lời bằng bản cũ.
                "so_manh": _dem_manh(p),
                # Soi ngay trong danh sách: tài liệu cũ chưa ai mở ra sửa cũng
                # phải lộ vấn đề, không thì chỉ tài liệu vừa soạn mới được soi.
                **_dem_soi(p),
            })
    return {
        "tai_lieu": tai_lieu,
        "nhom": NHOM,
        "tong": len(tai_lieu),
        "duoi_nhan": sorted(DUOI_VAN_BAN | DUOI_BANG),
    }


@router.get("/noi-dung")
async def doc(nhom: str, ten: str):
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    if not p.exists():
        # File .txt cũ vẫn phải đọc được dù ta luôn ghi ra .md.
        alt = p.with_suffix(".txt")
        if not alt.exists():
            return {"error": f"Không có tài liệu '{ten}'"}
        p = alt
    return {
        "nhom": nhom, "ten": p.stem, "tep": p.name,
        "noi_dung": p.read_text(encoding="utf-8", errors="replace"),
    }


# --- thử -----------------------------------------------------------------------
#
# Sửa tài liệu xong phải THỬ được ngay tại đây. Trước đây muốn biết AI có lấy
# đúng tài liệu không thì phải mở tab Chat gọi hẳn một lượt - nên hầu như không
# ai thử, và tài liệu sai chỉ lộ ra khi khách đã nghe nhầm số.


async def hoi_thu(cau_hoi: str, san_pham: str = "", top_k: int = 4) -> dict:
    """Chạy đúng truy vấn mà đường thoại chạy, nhưng giữ lại phần bị vứt đi.

    Tách khỏi hàm route vì route khai báo tham số bằng `Form(...)`: gọi thẳng
    trong test thì các tham số không truyền sẽ mang object của FastAPI chứ không
    phải giá trị mặc định.
    """
    cau_hoi = (cau_hoi or "").strip()
    if not cau_hoi:
        return {"error": "Nhập câu khách hay hỏi rồi bấm Hỏi thử"}

    rag = _rag()
    if rag is None:
        return {"error": "RAG chưa sẵn sàng - đợi backend nạp xong rồi thử lại"}

    t0 = time.perf_counter()
    try:
        _, chi_tiet = await rag.retrieve_chi_tiet(
            cau_hoi, top_k=max(1, min(int(top_k or 4), 10)), san_pham=(san_pham or "").strip())
    except Exception as e:
        logger.warning("Tri thức: hỏi thử lỗi: %s", e)
        return {"error": f"Không truy vấn được: {e}"}

    manh = [{
        "nguon": c.get("nguon") or "",
        "diem": c.get("diem"),
        "bi_loc": bool(c.get("bi_loc")),
        "doan": c.get("doan") or "",
    } for c in chi_tiet]

    return {
        "cau_hoi": cau_hoi,
        "san_pham": (san_pham or "").strip(),
        "manh": manh,
        "so_lay": sum(1 for m in manh if not m["bi_loc"]),
        # Đếm riêng: mảnh bị lưới lọc bỏ là dấu vết của lỗi "RAG lạc sản phẩm".
        # Thấy mảnh vay_mua_nha bị loại khi đang tư vấn vay tín chấp thì biết
        # lưới đang ăn; thấy nó KHÔNG bị loại thì biết lưới đang hở.
        "so_bi_loc": sum(1 for m in manh if m["bi_loc"]),
        "ms": round((time.perf_counter() - t0) * 1000),
    }


@router.post("/hoi-thu")
async def hoi_thu_api(cau_hoi: str = Form(""), san_pham: str = Form(""),
                      top_k: int = Form(4)):
    return await hoi_thu(cau_hoi, san_pham, top_k)


@router.get("/manh")
async def xem_manh(nhom: str, ten: str):
    """Các mảnh kho vector ĐANG giữ cho tài liệu này."""
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    rag = _rag()
    if rag is None:
        return {"error": "RAG chưa sẵn sàng - đợi backend nạp xong rồi thử lại"}

    doan_list: list[str] = []
    for src in dict.fromkeys(_cac_dang_nguon(p)):
        doan_list = rag.lay_theo_nguon(src)
        if doan_list:
            break

    manh = [{
        "stt": i,
        "doan": d,
        "so_chu": len(d),
        "cat_ngang_bang": cat_ngang_bang(d),
        "bat_dau_giua_cau": bat_dau_giua_cau(d),
    } for i, d in enumerate(doan_list, 1)]

    return {
        "nhom": nhom, "ten": _ten_an_toan(ten), "tep": p.name,
        "so_manh": len(manh),
        # Có file trên đĩa mà kho trống nghĩa là AI CHƯA đọc bản này. Không nói
        # thẳng thì người dùng sửa xong tưởng đã xong, mà bot vẫn đọc bản cũ.
        "chua_nap": not manh,
        "manh": manh,
    }


def soi_nhanh(p: Path) -> dict:
    """Soi một file trên đĩa. Lỗi đọc file không được làm hỏng cả danh sách."""
    try:
        return soi_tai_lieu(p.read_text(encoding="utf-8", errors="replace"),
                            nhom=p.parent.name, ten=p.stem)
    except Exception as e:
        logger.warning("Tri thức: không soi được %s: %s", p, e)
        return {"loi": [], "canh_bao": []}


async def soi(noi_dung: str, nhom: str = "products", ten: str = "") -> dict:
    """Soi tài liệu đang soạn + cắt thử, chưa cần lưu.

    KHÔNG đụng tới RAG: người vận hành hay soạn tài liệu ngay lúc backend còn
    đang nạp model, mà soi là việc thuần văn bản.
    """
    kq = soi_tai_lieu(noi_dung or "", nhom=nhom, ten=ten)
    manh = soi_manh(noi_dung or "")
    return {**kq, "so_manh": len(manh), "manh": manh}


@router.post("/soi")
async def soi_api(noi_dung: str = Form(""), nhom: str = Form("products"),
                  ten: str = Form("")):
    return await soi(noi_dung, nhom, ten)


@router.get("/mau")
async def lay_mau(nhom: str = "products"):
    """Mẫu cấu trúc để người viết khỏi phải đoán viết thế nào cho AI đọc tốt."""
    if nhom not in MAU:
        return {"error": f"Nhóm không hợp lệ. Chọn: {', '.join(MAU)}"}
    return {"nhom": nhom, "noi_dung": MAU[nhom]}


# --- ghi -----------------------------------------------------------------------

@router.post("/luu")
async def luu(nhom: str = Form(...), ten: str = Form(...), noi_dung: str = Form("")):
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ. Tên chỉ dùng chữ, số, gạch."}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    so_manh = _nap_lai_mot_tep(p)
    logger.info("Tri thức: lưu %s (%d mảnh)", p, so_manh)
    return {"ok": True, "ten": p.stem, "nhom": nhom, "so_manh": so_manh}


@router.post("/upload")
async def upload(file: UploadFile = File(...), nhom: str = Form("products"),
                 ten: str = Form("")):
    if nhom not in NHOM:
        return {"error": f"Nhóm không hợp lệ. Chọn: {', '.join(NHOM)}"}

    raw = await file.read()
    if not raw:
        return {"error": "File rỗng"}
    if len(raw) > _TRAN_BYTE:
        return {"error": f"File quá lớn ({len(raw)//1024//1024} MB), tối đa 10 MB"}

    goc_ten = ten.strip() or (file.filename or "tai_lieu")
    duoi = Path(file.filename or "").suffix.lower()

    if duoi in DUOI_BANG:
        try:
            noi_dung = _bang_sang_markdown(raw, duoi, _ten_an_toan(goc_ten))
        except Exception as e:
            return {"error": f"Không đọc được bảng: {e}"}
    elif duoi in DUOI_VAN_BAN or not duoi:
        noi_dung = raw.decode("utf-8", errors="replace")
    else:
        return {"error": f"Chưa đọc được đuôi '{duoi}'. Nhận: "
                         f"{', '.join(sorted(DUOI_VAN_BAN | DUOI_BANG))}. "
                         "File Word/PDF thì lưu lại thành .txt rồi tải lên."}

    p = _duong_dan(nhom, goc_ten)
    if p is None:
        return {"error": "Tên file không hợp lệ"}
    ghi_de = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    so_manh = _nap_lai_mot_tep(p)
    logger.info("Tri thức: tải lên %s (%d mảnh, ghi đè=%s)", p, so_manh, ghi_de)
    return {
        "ok": True, "ten": p.stem, "nhom": nhom, "so_manh": so_manh,
        "ghi_de": ghi_de, "so_dong": noi_dung.count("\n") + 1,
        "xem_truoc": noi_dung[:400],
    }


@router.delete("")
async def xoa(nhom: str, ten: str):
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    if not p.exists():
        p = p.with_suffix(".txt")
    if not p.exists():
        return {"error": f"Không có tài liệu '{ten}'"}
    rag = _rag()
    if rag:
        for src in dict.fromkeys(_cac_dang_nguon(p)):
            rag.xoa_theo_nguon(src)
    p.unlink()
    logger.info("Tri thức: xoá %s", p)
    return {"ok": True, "da_xoa": p.name}


@router.post("/nap-lai")
async def nap_lai():
    """Nạp lại toàn bộ thư mục. Dùng khi sửa file thẳng trên đĩa."""
    rag = _rag()
    if rag is None:
        return {"error": "RAG chưa sẵn sàng"}
    t0 = time.perf_counter()
    rag.clear()
    rag.ingest_directory(str(GOC))
    return {
        "ok": True,
        "ms": round((time.perf_counter() - t0) * 1000),
        "so_tai_lieu": len(list(GOC.rglob("*.md"))) + len(list(GOC.rglob("*.txt"))),
    }
