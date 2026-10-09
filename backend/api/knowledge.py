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

import io
import hashlib
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.core.knowledge_rules import (MAU, bat_dau_giua_cau, cat_ngang_bang,
                                          soi_manh, soi_tai_lieu)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

GOC = Path("./knowledge")

# Lịch sử sửa để NGOÀI thư mục tri thức, và đó là quyết định an toàn chứ không
# phải tiện tay: `RAGService.ingest_directory` quét `rglob("*.md")`, nên bản cũ
# nằm trong `knowledge/` là RAG nạp luôn cả chúng - bot trả lời khách bằng lãi
# suất đã bị thay, mà không có gì báo.
GOC_LICH_SU = Path("./data/lich_su_tri_thuc")

# Giữ bao nhiêu bản cho mỗi tài liệu. Tài liệu tri thức chỉ vài KB nên 20 bản
# vẫn không đáng kể, mà đủ để lùi qua một buổi sửa nhiều lần.
SO_BAN_GIU = 20


class ThuVienTuDongConfig(BaseModel):
    enabled: bool = True
    questions_per_document: int = 120
    variants_per_answer: int = 4
    learn_history: bool = True


class ThuVienTuDongBuild(BaseModel):
    full_rebuild: bool = False


class HoiDapSave(BaseModel):
    nhom: str
    ten: str
    cau_hoi: list[str] = Field(default_factory=list, max_length=100)
    tra_loi: str = Field(min_length=1, max_length=20000)
    bat: bool = True
    tinh_huong: str | None = Field(default=None, max_length=80)


class HoiDapEdit(HoiDapSave):
    expected_updated_at: float = Field(allow_inf_nan=False)


class HoiDapAppend(BaseModel):
    nhom: str
    ten: str
    so_cau: int = Field(ge=1, le=300)


class CauThieuThem(BaseModel):
    nhom: str
    ten: str
    tra_loi: str = Field(min_length=1, max_length=20000)
    cau_hoi: str = Field(default="", max_length=300)

# Thư mục cho phép. KHÔNG nhận tên thư mục tuỳ ý từ client: nó ghép thẳng vào
# đường dẫn file, nhận bừa là mở đường ghi đè file bất kỳ trên máy.
#
# `products` có ý nghĩa ĐẶC BIỆT, đừng đổi tên: RAGService._mat_na_loc chỉ
# lọc mảnh nằm trong thư mục này. Tài liệu sản phẩm đặt sai chỗ sẽ không được lọc,
# và bot lại đọc lãi suất của sản phẩm khác cho khách.
NHOM_GOC = {
    "products": "Sản phẩm — mỗi sản phẩm một file, dùng để lọc theo sản phẩm khi tư vấn",
    "faq": "Câu hỏi thường gặp",
    "chinh_sach": "Chính sách, điều kiện, quy định chung",
}


def cac_nhom() -> dict[str, str]:
    """Nhóm = thư mục con của `knowledge/`, cộng ba nhóm gốc luôn có mặt.

    Không giữ danh sách nhóm trong file cấu hình riêng: thư mục CHÍNH LÀ sự
    thật, mà hai nguồn sự thật thì sớm muộn lệch nhau - lúc đó tài liệu nằm
    trong thư mục không có trong danh sách sẽ tàng hình khỏi giao diện.

    Bỏ qua thư mục ẩn: đó là chỗ hệ thống dùng, không phải nhóm tài liệu.
    """
    ra = dict(NHOM_GOC)
    try:
        for tm in sorted(GOC.iterdir()):
            if tm.is_dir() and not tm.name.startswith("."):
                ra.setdefault(tm.name, tm.name.replace("_", " "))
    except FileNotFoundError:
        pass
    return ra


@router.get("/thu-vien-tu-dong")
async def thu_vien_tu_dong_status():
    # Chạy ở luồng riêng: trang Tri thức AI gọi hàm này mỗi 2,5 giây, không
    # được để nó giữ vòng sự kiện (xem `_dem_tieng_da_nho`).
    import asyncio
    from backend.services.answer_bank_learning import bo_hoc_tra_loi
    return await asyncio.to_thread(bo_hoc_tra_loi.trang_thai)


@router.post("/thu-vien-tu-dong")
async def thu_vien_tu_dong_config(body: ThuVienTuDongConfig):
    from backend.services.answer_bank_learning import bo_hoc_tra_loi
    return bo_hoc_tra_loi.configure(
        enabled=body.enabled,
        questions_per_document=body.questions_per_document,
        variants_per_answer=body.variants_per_answer,
        learn_history=body.learn_history,
    )


@router.post("/thu-vien-tu-dong/build")
async def thu_vien_tu_dong_build(body: ThuVienTuDongBuild):
    from backend.services.answer_bank_learning import bo_hoc_tra_loi
    return bo_hoc_tra_loi.request_build(full_rebuild=body.full_rebuild)


@router.post("/thu-vien-tu-dong/cancel")
async def thu_vien_tu_dong_cancel():
    from backend.services.answer_bank_learning import bo_hoc_tra_loi
    return bo_hoc_tra_loi.cancel()

DUOI_VAN_BAN = {".md", ".txt"}
DUOI_BANG = {".csv", ".xlsx", ".xls"}
# Word đọc bằng thư viện chuẩn của Python (xem `_docx_sang_van_ban`).
# PDF thì không tự đọc được - phải thêm gói ngoài, mà máy chạy offline.
DUOI_WORD = {".docx"}
_TRAN_BYTE = 10 * 1024 * 1024


def _rag():
    """Import trễ: `backend.main` import ngược lại module này lúc dựng router."""
    try:
        from backend.main import app_state
        return app_state.rag
    except Exception:
        return None


def _ten_an_toan(ten: str) -> str:
    """Về tên file trần, chỉ chữ-số-gạch. Rỗng nghĩa là không hợp lệ.

    BỎ DẤU trước khi lọc ký tự, đừng băm thẳng: "Biểu phí dịch vụ" mà lọc thẳng
    ra "bi_u_ph_d_ch_v" - tên vô nghĩa, và với nhóm `products` thì lưới lọc sản
    phẩm neo theo tên file cũng hỏng theo.
    """
    import unicodedata

    ten = Path(ten.replace("\\", "/")).name          # bỏ mọi phần thư mục
    goc = re.sub(r"\.(md|txt|csv|xlsx|xls|docx)$", "", ten, flags=re.I)
    goc = unicodedata.normalize("NFD", goc)
    goc = "".join(c for c in goc if unicodedata.category(c) != "Mn")
    goc = goc.replace("đ", "d").replace("Đ", "D")
    goc = re.sub(r"[^0-9A-Za-z_-]+", "_", goc).strip("_")
    return goc[:60]


def _duong_dan(nhom: str, ten: str) -> Path | None:
    if nhom not in cac_nhom():
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
    return _thong_tin_chi_muc(p)["so_manh"]


def _thong_tin_chi_muc(p: Path) -> dict:
    """Trạng thái vector của file mà không chạy embedding.

    `can_cap_nhat` nghĩa là file trên đĩa đã đổi so với hash đang nằm trong
    ChromaDB. Kho cũ chưa có hash cũng được đánh dấu cần cập nhật đúng một lần
    để chuyển sang metadata mới.
    """
    rag = _rag()
    if rag is None:
        return {"so_manh": 0, "trang_thai": "chua_lap", "lap_luc": None}

    info = rag.thong_tin_nguon(_cac_dang_nguon(p))
    so_manh = int(info.get("so_manh") or 0)
    if not so_manh:
        return {"so_manh": 0, "trang_thai": "chua_lap", "lap_luc": None}

    noi_dung = p.read_text(encoding="utf-8", errors="replace")
    digest = hashlib.sha256(noi_dung.encode("utf-8")).hexdigest()
    hashes = set(info.get("hashes") or [])
    trang_thai = "da_lap" if hashes == {digest} else "can_cap_nhat"
    return {
        "so_manh": so_manh,
        "trang_thai": trang_thai,
        "lap_luc": info.get("indexed_at"),
    }


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
        try:
            rel = p.resolve().relative_to(GOC.resolve()).as_posix()
        except ValueError:
            rel = p.name
        rag.ingest_text(noi_dung, doc_id=p.stem, metadata={
            "source": src,
            "knowledge_root": str(GOC.resolve()),
            "knowledge_relpath": rel,
            **({"bank": "shinhan"} if rel.startswith("shinhan/") else {}),
        })
    return rag.dem_theo_nguon(src)


async def _dong_bo_hoi_dap(p: Path, nhom: str) -> dict:
    """Sau khi tài liệu đổi, tự chuẩn bị Q&A + voice cho đường gọi.

    Lưu tài liệu là thao tác chính nên lỗi Qwen/TTS không được làm mất bản vừa
    lưu. Service tự tắt bộ Q&A cũ nếu không sinh được bộ mới, còn API trả trạng
    thái để giao diện báo rõ cho người vận hành.
    """
    try:
        from backend.services.answer_bank_learning import bo_hoc_tra_loi
        from backend.services.knowledge_qa_service import nap_lai_duong_goi

        status = bo_hoc_tra_loi.document_changed(p)
        runtime = await nap_lai_duong_goi(build_voice=False)
        return {"ok": True, "queued": True, "runtime": runtime, "job": status["job"]}
    except Exception as e:
        logger.exception("Tri thức: không tự đồng bộ Q&A cho %s", p)
        return {"error": f"Tài liệu đã lưu nhưng chưa tạo được Q&A + voice: {e}"}


# .docx là file zip chứa word/document.xml. Đọc bằng `zipfile` + `ElementTree`
# của Python, KHÔNG thêm thư viện ngoài: máy chạy offline, mỗi phụ thuộc thêm là
# một thứ có thể thiếu lúc dựng lại trên máy khác.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _chu_trong(nut) -> str:
    """Gộp chữ của một đoạn hoặc một ô.

    Word tách một câu thành nhiều <w:r> khi có soát chính tả hay đổi định dạng
    giữa chừng, nên phải nối các <w:t> lại chứ không lấy cái đầu tiên. <w:tab>
    và <w:br> là khoảng trắng, bỏ hẳn thì chữ dính vào nhau.
    """
    ra = []
    for con in nut.iter():
        if con.tag == _W + "t":
            ra.append(con.text or "")
        elif con.tag in (_W + "tab", _W + "br"):
            ra.append(" ")
    return "".join(ra).strip()


def _docx_sang_van_ban(raw: bytes) -> str:
    """File Word -> văn bản, bảng giữ nguyên dạng bảng markdown.

    Bảng là phần quan trọng nhất: biểu lãi suất trong Word là ca dùng chính, mà
    mất bảng thì số rời khỏi tên cột và AI đọc số không biết của ai.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError("Không đọc được file Word (.docx). File .doc đời cũ thì "
                         "mở bằng Word rồi lưu lại dạng .docx.") from e

    than = ET.fromstring(xml).find(_W + "body")
    if than is None:
        raise ValueError("File Word rỗng hoặc hỏng")

    dong: list[str] = []
    for nut in than:
        if nut.tag == _W + "p":
            chu = _chu_trong(nut)
            if chu:
                dong.append(chu)
        elif nut.tag == _W + "tbl":
            hang = [[_chu_trong(o) for o in tr.findall(_W + "tc")]
                    for tr in nut.findall(_W + "tr")]
            hang = [h for h in hang if any(c for c in h)]
            if not hang:
                continue
            rong = max(len(h) for h in hang)
            def _ke(o: list[str]) -> str:
                o = list(o) + [""] * (rong - len(o))
                return "| " + " | ".join(c.replace("|", "/") for c in o) + " |"
            dong.append("")
            dong.append(_ke(hang[0]))
            dong.append("|" + "|".join(["---"] * rong) + "|")
            dong += [_ke(h) for h in hang[1:]]
            dong.append("")

    return "\n".join(dong).strip() + "\n"


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
    for nhom in cac_nhom():
        thu_muc = GOC / nhom
        if not thu_muc.exists():
            continue
        for p in sorted(thu_muc.glob("*.md")) + sorted(thu_muc.glob("*.txt")):
            st = p.stat()
            chi_muc = _thong_tin_chi_muc(p)
            tai_lieu.append({
                "ten": p.stem,
                "nhom": nhom,
                "tep": p.name,
                "kich_thuoc": st.st_size,
                "sua_doi": st.st_mtime,
                # Số mảnh trong RAG: 0 nghĩa là file có trên đĩa nhưng AI CHƯA
                # đọc được nó - phải bấm "Nạp lại". Không hiện ra thì người dùng
                # sửa xong tưởng đã xong, mà bot vẫn trả lời bằng bản cũ.
                "so_manh": chi_muc["so_manh"],
                "trang_thai_chi_muc": chi_muc["trang_thai"],
                "lap_chi_muc_luc": chi_muc["lap_luc"],
                # Soi ngay trong danh sách: tài liệu cũ chưa ai mở ra sửa cũng
                # phải lộ vấn đề, không thì chỉ tài liệu vừa soạn mới được soi.
                **_dem_soi(p),
            })
    return {
        "tai_lieu": tai_lieu,
        "nhom": cac_nhom(),
        "tong": len(tai_lieu),
        "duoi_nhan": sorted(DUOI_VAN_BAN | DUOI_BANG | DUOI_WORD),
    }


@router.post("/lap-chi-muc")
async def lap_chi_muc(nhom: str = Form(...), ten: str = Form(...),
                      force: bool = Form(False)):
    """Tạo/cập nhật vector cho đúng một tài liệu.

    Đây là thao tác embedding bằng BGE-M3. Qwen 9B chỉ đọc các mảnh được RAG
    tìm ra ở bước trả lời, không dùng Qwen để tạo vector.
    """
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    if not p.exists():
        alt = p.with_suffix(".txt")
        if not alt.exists():
            return {"error": f"Không có tài liệu '{ten}'"}
        p = alt

    rag = _rag()
    if rag is None:
        return {"error": "RAG chưa sẵn sàng"}

    truoc = _thong_tin_chi_muc(p)
    if truoc["trang_thai"] == "da_lap" and not force:
        return {
            "ok": True,
            "bo_qua": True,
            "ten": p.stem,
            "nhom": nhom,
            "so_manh": truoc["so_manh"],
            "model": "BAAI/bge-m3",
            "ms": 0,
        }

    t0 = time.perf_counter()
    so_manh = _nap_lai_mot_tep(p)
    sau = _thong_tin_chi_muc(p)
    return {
        "ok": True,
        "bo_qua": False,
        "ten": p.stem,
        "nhom": nhom,
        "so_manh": so_manh,
        "trang_thai_chi_muc": sau["trang_thai"],
        "model": "BAAI/bge-m3",
        "ms": round((time.perf_counter() - t0) * 1000),
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


@router.get("/hoi-dap")
async def hoi_dap_da_tao(nhom: str, ten: str):
    """Các câu hỏi-đáp Qwen đã chuẩn bị từ đúng một tài liệu."""
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    if not p.exists():
        p = p.with_suffix(".txt")
    if not p.exists():
        return {"error": f"Không có tài liệu '{ten}'"}

    from backend.services.knowledge_qa_service import danh_sach
    from backend.config import settings

    items = danh_sach(nhom, p.stem)
    active = [item for item in items if item["bat"]]
    voice = {"status": ("disabled" if not settings.tieng_san_bat else
                        "ready" if all(item["voice_ready"] for item in active) else "queued")}
    return {"nhom": nhom, "ten": p.stem, "so_dong": len(items), "items": items, "voice": voice}


@router.post("/tao-hoi-dap")
async def tao_hoi_dap(nhom: str = Form(...), ten: str = Form(...),
                      so_cau: int = Form(12), cau_hoi_nhan_vien: str = Form("")):
    """Qwen đọc tài liệu -> Q&A -> vector -> WAV sẵn cho đường gọi.

    Nếu ``cau_hoi_nhan_vien`` có dữ liệu, mỗi dòng là một câu thực tế nhân viên
    đã gặp và Qwen chỉ soạn câu trả lời cho các câu đó. Để trống thì Qwen tự nghĩ
    các câu khách hàng có khả năng hỏi từ nội dung tài liệu.
    """
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}
    if not p.exists():
        p = p.with_suffix(".txt")
    if not p.exists():
        return {"error": f"Không có tài liệu '{ten}'"}

    from backend.services.knowledge_qa_service import (tao_va_luu,
                                                       tach_cau_hoi_nhan_vien)

    cau_nv = tach_cau_hoi_nhan_vien(cau_hoi_nhan_vien)
    try:
        return await tao_va_luu(
            nhom, p.stem,
            p.read_text(encoding="utf-8", errors="replace"),
            so_cau=max(1, min(int(so_cau or 12), 300)),
            cau_hoi_nhan_vien=cau_nv,
        )
    except Exception as e:
        logger.exception("Tri thức: không tạo được hỏi-đáp cho %s/%s", nhom, p.stem)
        return {"error": f"Không tạo được bộ hỏi-đáp: {e}"}


def _editor_source(nhom: str, ten: str) -> Path:
    p = _duong_dan(nhom, ten)
    if p is None:
        raise HTTPException(400, "Tên hoặc nhóm không hợp lệ")
    if not p.exists():
        p = p.with_suffix(".txt")
    if not p.is_file():
        raise HTTPException(404, f"Không có tài liệu '{ten}'")
    return p


@router.post("/hoi-dap")
async def them_hoi_dap(body: HoiDapSave):
    from backend.services import answer_bank_editor as editor
    p = _editor_source(body.nhom, body.ten)
    try:
        saved = await editor.save(body.nhom, p.stem, body.cau_hoi, body.tra_loi, body.bat)
    except editor.EditorError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    if body.tinh_huong is not None:
        from backend.services import answer_bank_gaps as gaps
        gaps.dat_nhom(saved["item"]["id"], body.tinh_huong)
    return saved


@router.patch("/hoi-dap/{answer_id}")
async def sua_hoi_dap(answer_id: str, body: HoiDapEdit):
    from backend.services import answer_bank_editor as editor
    p = _editor_source(body.nhom, body.ten)
    try:
        return await editor.save(body.nhom, p.stem, body.cau_hoi, body.tra_loi, body.bat,
                                 answer_id=answer_id, expected_updated_at=body.expected_updated_at)
    except editor.EditorError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/tao-them-hoi-dap")
async def tao_them_hoi_dap(body: HoiDapAppend):
    from backend.services import answer_bank_editor as editor
    p = _editor_source(body.nhom, body.ten)
    try:
        return await editor.append(body.nhom, p.stem, body.so_cau)
    except editor.EditorError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except Exception as exc:
        logger.exception("Không tạo thêm được hỏi-đáp cho %s/%s", body.nhom, p.stem)
        raise HTTPException(503, f"Chưa tạo thêm được đáp án: {exc}") from exc


# ── Câu chưa có đáp án: lượt mô hình phải TỰ VIẾT vì kho không có ─────────
#
# Mục tiêu là bớt dần phần mô hình sinh. Sổ này cho biết đúng chỗ kho còn
# thiếu, xếp theo số lần khách thật đã hỏi; soạn đáp án ở đây là lần sau câu
# đó chỉ còn được CHỌN trong kho. Xem `services/answer_bank_gaps.py`.

# Tài liệu chứa các câu giao tiếp không thuộc sản phẩm nào ("em tên gì", khách
# phân vân, khách cảm ơn...). Đáp án nào cũng phải thuộc một tài liệu nguồn.
TAI_LIEU_GIAO_TIEP = ("faq", "giao_tiep_chung")


def _tai_lieu_cho_dap_an() -> list[dict]:
    from backend.services import answer_bank_learning as learning
    docs, _errors = learning._documents()
    return [{"nhom": d.group, "ten": d.stem} for d in docs]


def _goi_y_tai_lieu(san_pham: str, tai_lieu: list[dict]) -> dict | None:
    from backend.services.bang_hoi_dap import _cung_san_pham
    for d in tai_lieu:
        if d["nhom"] == "products" and _cung_san_pham(d["ten"], san_pham):
            return d
    return next((d for d in tai_lieu if (d["nhom"], d["ten"]) == TAI_LIEU_GIAO_TIEP), None)


@router.get("/cau-chua-co")
async def cau_chua_co(trang_thai: str = "open", ngay: int = 7):
    from backend.services import answer_bank_gaps as gaps
    if trang_thai not in {"open", "ignored", "answered"}:
        raise HTTPException(400, "Trạng thái không hợp lệ")
    tai_lieu = _tai_lieu_cho_dap_an()
    items = gaps.danh_sach_thieu(trang_thai)
    for item in items:
        item["goi_y"] = _goi_y_tai_lieu(item["san_pham"], tai_lieu)
    return {"items": items, "thong_ke": gaps.thong_ke(ngay), "tai_lieu": tai_lieu}


@router.post("/cau-chua-co/{key}/trang-thai")
async def cau_chua_co_trang_thai(key: str, trang_thai: str = Form(...)):
    from backend.services import answer_bank_gaps as gaps
    if trang_thai not in {"open", "ignored"}:
        raise HTTPException(400, "Trạng thái không hợp lệ")
    if not gaps.dat_trang_thai(key, trang_thai):
        raise HTTPException(404, "Không còn câu này trong sổ")
    return {"ok": True}


@router.post("/cau-chua-co/{key}/them")
async def cau_chua_co_them(key: str, body: CauThieuThem):
    """Soạn đáp án cho một câu khách đã hỏi mà kho chưa có.

    Lời khách được ghi làm câu hỏi mẫu của đáp án, nên lần sau khách hỏi đúng
    câu đó là đọc thẳng - không qua Qwen, không qua mô hình sinh.
    """
    from backend.services import answer_bank_editor as editor
    from backend.services import answer_bank_gaps as gaps
    miss = gaps.lay_thieu(key)
    if miss is None:
        raise HTTPException(404, "Không còn câu này trong sổ")
    p = _editor_source(body.nhom, body.ten)
    cau_hoi = (body.cau_hoi or miss["cau_hoi"]).strip()
    try:
        saved = await editor.save(body.nhom, p.stem, [cau_hoi], body.tra_loi, True)
    except editor.EditorError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    gaps.dat_trang_thai(key, "answered", saved["item"]["id"])
    return {"ok": True, "answer_id": saved["item"]["id"], "voice": saved.get("voice")}


class TuHoi(BaseModel):
    so_cau: int = Field(default=40, ge=3, le=200)
    tai_lieu: str = Field(default="", max_length=300)
    kieu: str = Field(default="tu_hoi", pattern="^(tu_hoi|doi_thoai|doi_thuong)$")


@router.get("/tu-hoi")
async def tu_hoi_trang_thai():
    from backend.services import answer_bank_selfask as selfask
    return selfask.trang_thai()


class NhapDoiThuong(BaseModel):
    dong: list[dict] = Field(min_length=1, max_length=3000)


@router.post("/tu-hoi/nhap-doi-thuong")
async def tu_hoi_nhap_doi_thuong(body: NhapDoiThuong):
    """Nhập hàng loạt câu giao tiếp đời thường soạn bên ngoài; câu đạt luật vào hàng chờ duyệt."""
    from backend.services import answer_bank_selfask as selfask
    return await selfask.nhap_doi_thuong(body.dong)


@router.get("/tu-hoi/luat")
async def tu_hoi_luat():
    """Bộ luật của hai vai trong chế độ đối thoại, để người vận hành đọc được."""
    from backend.services import answer_bank_selfask as selfask
    return {"vai_khach": [{"la": v[0], "quan_tam": v[1]} for v in selfask.VAI_KHACH],
            "luat_khach": selfask.LUAT_KHACH, "luat_tu_van": selfask.LUAT_TU_VAN,
            "canh_doi_thuong": [{"nhom": c[0], "canh": c[1]} for c in selfask.CANH_DOI_THUONG],
            "luat_khach_doi_thuong": selfask.LUAT_KHACH_DOI_THUONG,
            "luat_tu_van_doi_thuong": selfask.LUAT_TU_VAN_DOI_THUONG}


@router.post("/tu-hoi")
async def tu_hoi_bat_dau(body: TuHoi):
    """Qwen đóng vai khách tự đặt câu hỏi, soạn đáp án có căn cứ cho câu kho chưa có."""
    from backend.services import answer_bank_selfask as selfask
    return selfask.bat_dau(body.so_cau, body.tai_lieu, body.kieu)


class DuyetDapAn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=3000)
    chap_nhan: bool


@router.get("/cho-duyet")
async def cho_duyet_danh_sach():
    from backend.services import answer_bank_gaps as gaps
    return {"items": gaps.danh_sach_cho_duyet()}


@router.post("/cho-duyet")
async def cho_duyet_quyet_dinh(body: DuyetDapAn):
    """Bật các đáp án AI tự soạn đã được người duyệt, hoặc xoá hẳn nếu từ chối."""
    from backend.services import answer_bank_gaps as gaps
    from backend.services import answer_bank_editor as editor
    bat = gaps.duyet(body.ids, body.chap_nhan)
    voice = await editor._publish(bat) if bat else None
    return {"ok": True, "da_bat": len(bat), "con_lai": gaps.so_cho_duyet(), "voice": voice}


class GanTinhHuong(BaseModel):
    tinh_huong: str = Field(default="", max_length=80)


@router.get("/theo-tinh-huong")
async def theo_tinh_huong():
    """Đáp án gom theo nhóm tình huống của khách (bận, từ chối, nghi ngờ...)."""
    from backend.services import answer_bank_gaps as gaps
    return {"nhom": gaps.theo_nhom()}


@router.post("/hoi-dap/{answer_id}/tinh-huong")
async def gan_tinh_huong(answer_id: str, body: GanTinhHuong):
    from backend.services import answer_bank_gaps as gaps
    gaps.dat_nhom(answer_id, body.tinh_huong)
    return {"ok": True}


@router.get("/lua-chon-da-nho")
async def lua_chon_da_nho():
    from backend.services import answer_bank_gaps as gaps
    return {"items": gaps.danh_sach_lua_chon()}


@router.delete("/lua-chon-da-nho/{key}")
async def xoa_lua_chon_da_nho(key: str):
    from backend.services import answer_bank_gaps as gaps
    if not gaps.xoa_lua_chon(key):
        raise HTTPException(404, "Không còn lựa chọn này")
    return {"ok": True}


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


@router.post("/nhom")
async def them_nhom(ten: str = Form(...)):
    """Thêm một nhóm tài liệu. Nhóm chỉ là thư mục con của `knowledge/`.

    KHÔNG đụng tới ý nghĩa đặc biệt của `products`: `RAGService._mat_na_loc`
    chỉ lọc mảnh nằm trong thư mục đó, nên nhóm mới là chỗ chứa tài liệu chung
    chứ không thành sản phẩm để lọc.
    """
    # Từ chối thẳng chứ không "làm sạch rồi dùng": "../../etc" mà lọc còn "etc"
    # thì người dùng gõ nhầm một đằng, hệ thống tạo ra một nẻo mà không báo gì.
    if re.search(r"[/\\]|\.\.", ten or ""):
        return {"error": "Tên nhóm không được chứa dấu gạch chéo hay hai chấm"}
    ma = _ten_an_toan(ten).lower()
    if not ma:
        return {"error": "Tên nhóm chỉ dùng chữ, số và gạch dưới"}
    if ma in cac_nhom():
        return {"error": f"Nhóm '{ma}' đã có rồi"}
    (GOC / ma).mkdir(parents=True, exist_ok=True)
    logger.info("Tri thức: thêm nhóm %s", ma)
    return {"ok": True, "ma": ma, "nhan": ma.replace("_", " "), "nhom": cac_nhom()}


def _bo_dau_giu_vi_tri(s: str) -> str:
    """Bỏ dấu nhưng GIỮ NGUYÊN ĐỘ DÀI, để vị trí khớp ánh xạ thẳng về chuỗi gốc.

    `_khong_dau` gộp mọi ký tự lạ thành "_" nên độ dài đổi, dùng nó để lấy vị
    trí là trích ra đoạn lệch chỗ. Bắt được trên máy thật: gõ "no xau" ra đúng
    tài liệu nhưng đoạn trích lại là dòng tiêu đề ở đầu file, nên vẫn phải mở ra
    dò tay - đúng thứ mà ô tìm sinh ra để khỏi phải làm.
    """
    import unicodedata

    ra = []
    for c in s:
        if c in "đĐ":
            ra.append("d" if c == "đ" else "D")
            continue
        goc = "".join(x for x in unicodedata.normalize("NFD", c)
                      if unicodedata.category(x) != "Mn")
        ra.append(goc[0] if goc else c)
    return "".join(ra).lower()


def _trich_quanh(noi_dung: str, vi_tri: int, rong: int = 90) -> str:
    dau = max(0, vi_tri - rong // 3)
    doan = noi_dung[dau:dau + rong].replace("\n", " ").strip()
    return ("…" if dau else "") + doan + ("…" if dau + rong < len(noi_dung) else "")


@router.get("/tim")
async def tim(q: str = ""):
    """Tìm trong NỘI DUNG lẫn tên file.

    Người vận hành nhớ "cái tài liệu nói về CIC" chứ không nhớ nó tên gì, nên ô
    tìm chỉ lọc theo tên là tìm trượt. Bỏ dấu khi so: gõ nhanh thì không ai bỏ
    dấu, mà tìm trượt một lần là bỏ cuộc luôn.

    Đọc thẳng từ đĩa, không dựng chỉ mục: số tài liệu ở đây tính bằng chục.
    """
    from backend.core.knowledge_rules import _khong_dau

    tu = (q or "").strip()
    if not tu:
        return {"q": "", "ket_qua": []}
    moc = _khong_dau(tu)

    ket_qua = []
    for nhom in cac_nhom():
        thu_muc = GOC / nhom
        if not thu_muc.exists():
            continue
        for p in sorted(thu_muc.glob("*.md")) + sorted(thu_muc.glob("*.txt")):
            noi_dung = p.read_text(encoding="utf-8", errors="replace")
            if moc in _khong_dau(p.stem):
                ket_qua.append({"ten": p.stem, "nhom": nhom, "khop": "tên",
                                "trich": _trich_quanh(noi_dung, 0)})
                continue
            vi_tri = _bo_dau_giu_vi_tri(noi_dung).find(_bo_dau_giu_vi_tri(tu))
            if vi_tri >= 0:
                ket_qua.append({"ten": p.stem, "nhom": nhom, "khop": "nội dung",
                                "trich": _trich_quanh(noi_dung, vi_tri)})
    return {"q": tu, "ket_qua": ket_qua}


# --- lịch sử sửa ---------------------------------------------------------------
#
# Đây là chỗ duy nhất quyết định con số bot đọc cho khách, mà ghi đè là mất trắng
# bản cũ - sửa nhầm lãi suất lúc gấp thì không có đường lùi.


def _thu_muc_lich_su(nhom: str, ten: str) -> Path | None:
    p = _duong_dan(nhom, ten)
    return None if p is None else GOC_LICH_SU / nhom / p.stem


def _cac_ban(nhom: str, ten: str) -> list[Path]:
    """Các bản đã lưu, MỚI NHẤT ĐỨNG ĐẦU."""
    tm = _thu_muc_lich_su(nhom, ten)
    if tm is None or not tm.exists():
        return []
    return sorted(tm.glob("*.md"), key=lambda x: x.name, reverse=True)


def _giu_ban_cu(p: Path, nhom: str, ten: str) -> None:
    """Cất bản đang có trước khi ghi đè. Không có file thì không cất gì.

    Lỗi cất bản cũ KHÔNG được chặn việc ghi: người dùng đang sửa lãi suất, chặn
    lại vì lịch sử hỏng là chặn đúng việc quan trọng hơn.
    """
    if not p.exists():
        return
    tm = _thu_muc_lich_su(nhom, ten)
    if tm is None:
        return
    try:
        tm.mkdir(parents=True, exist_ok=True)
        # Mốc kèm mili-giây: hai lần lưu trong cùng một giây là chuyện thường khi
        # bấm Ctrl+S liên tục, trùng tên thì bản trước bị đè MẤT HẲN. Mili-giây
        # vẫn trùng được (đo được: 25 lần lưu liên tiếp chỉ còn 16 bản), nên
        # trùng thì thêm hậu tố - hậu tố đứng sau nên thứ tự theo tên vẫn đúng
        # thứ tự thời gian.
        goc_moc = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        moc, dem = goc_moc, 0
        while (tm / f"{moc}.md").exists():
            dem += 1
            moc = f"{goc_moc}_{dem}"
        (tm / f"{moc}.md").write_text(p.read_text(encoding="utf-8", errors="replace"),
                                      encoding="utf-8")
        for cu in _cac_ban(nhom, ten)[SO_BAN_GIU:]:
            cu.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Tri thức: không lưu được bản cũ của %s: %s", p, e)


def _duong_dan_ban(nhom: str, ten: str, moc: str) -> Path | None:
    """Đường dẫn một bản trong lịch sử. `moc` đến từ client nên phải chặn."""
    tm = _thu_muc_lich_su(nhom, ten)
    if tm is None or not re.fullmatch(r"[0-9_]{1,32}", moc or ""):
        return None
    p = (tm / f"{moc}.md").resolve()
    try:
        p.relative_to(tm.resolve())
    except ValueError:
        return None
    return p


@router.get("/lich-su")
async def lich_su(nhom: str, ten: str):
    ban = [{
        "moc": p.stem,
        "kich_thuoc": p.stat().st_size,
        "luc": p.stat().st_mtime,
    } for p in _cac_ban(nhom, ten)]
    return {"nhom": nhom, "ten": ten, "ban": ban, "so_ban_giu": SO_BAN_GIU}


@router.get("/lich-su/noi-dung")
async def lich_su_noi_dung(nhom: str, ten: str, moc: str):
    p = _duong_dan_ban(nhom, ten, moc)
    if p is None or not p.exists():
        return {"error": "Không có bản này trong lịch sử"}
    return {"nhom": nhom, "ten": ten, "moc": moc,
            "noi_dung": p.read_text(encoding="utf-8", errors="replace")}


@router.post("/khoi-phuc")
async def khoi_phuc(nhom: str = Form(...), ten: str = Form(...), moc: str = Form(...)):
    """Đưa tài liệu về một bản cũ.

    Bản ĐANG CÓ cũng vào lịch sử: khôi phục nhầm cũng phải lùi lại được, không
    thì hoàn tác thành một chiều và người dùng mất bản mới.
    """
    ban = _duong_dan_ban(nhom, ten, moc)
    if ban is None or not ban.exists():
        return {"error": "Không có bản này trong lịch sử"}
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ"}

    _giu_ban_cu(p, nhom, ten)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ban.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    so_manh = _nap_lai_mot_tep(p)
    hoi_dap = await _dong_bo_hoi_dap(p, nhom)
    logger.info("Tri thức: khôi phục %s về bản %s (%d mảnh)", p, moc, so_manh)
    return {"ok": True, "ten": p.stem, "nhom": nhom, "moc": moc,
            "so_manh": so_manh, "hoi_dap": hoi_dap}


# --- ghi -----------------------------------------------------------------------

@router.post("/luu")
async def luu(nhom: str = Form(...), ten: str = Form(...), noi_dung: str = Form("")):
    p = _duong_dan(nhom, ten)
    if p is None:
        return {"error": "Tên hoặc nhóm không hợp lệ. Tên chỉ dùng chữ, số, gạch."}
    _giu_ban_cu(p, nhom, ten)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    so_manh = _nap_lai_mot_tep(p)
    hoi_dap = await _dong_bo_hoi_dap(p, nhom)
    logger.info("Tri thức: lưu %s (%d mảnh)", p, so_manh)
    return {"ok": True, "ten": p.stem, "nhom": nhom, "so_manh": so_manh,
            "hoi_dap": hoi_dap}


@router.post("/upload")
async def upload(file: UploadFile = File(...), nhom: str = Form("products"),
                 ten: str = Form("")):
    nhom_hop_le = cac_nhom()
    if nhom not in nhom_hop_le:
        return {"error": f"Nhóm không hợp lệ. Chọn: {', '.join(nhom_hop_le)}"}

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
    elif duoi in DUOI_WORD:
        try:
            noi_dung = _docx_sang_van_ban(raw)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Không đọc được file Word: {e}"}
    elif duoi in DUOI_VAN_BAN or not duoi:
        noi_dung = raw.decode("utf-8", errors="replace")
    else:
        return {"error": f"Chưa đọc được đuôi '{duoi}'. Nhận: "
                         f"{', '.join(sorted(DUOI_VAN_BAN | DUOI_BANG | DUOI_WORD))}. "
                         "File PDF thì mở ra, chọn hết rồi dán vào ô Soạn tài liệu."}

    p = _duong_dan(nhom, goc_ten)
    if p is None:
        return {"error": "Tên file không hợp lệ"}
    ghi_de = p.exists()
    _giu_ban_cu(p, nhom, ten)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    so_manh = _nap_lai_mot_tep(p)
    hoi_dap = await _dong_bo_hoi_dap(p, nhom)
    logger.info("Tri thức: tải lên %s (%d mảnh, ghi đè=%s)", p, so_manh, ghi_de)
    return {
        "ok": True, "ten": p.stem, "nhom": nhom, "so_manh": so_manh,
        "ghi_de": ghi_de, "so_dong": noi_dung.count("\n") + 1,
        "xem_truoc": noi_dung[:400], "hoi_dap": hoi_dap,
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
    # Cất bản cuối trước khi xoá: lỡ tay xoá vẫn lấy lại được.
    _giu_ban_cu(p, nhom, ten)
    ten_goc = p.stem
    p.unlink()
    try:
        from backend.services.answer_bank_learning import bo_hoc_tra_loi
        from backend.services.knowledge_qa_service import nap_lai_duong_goi
        status = bo_hoc_tra_loi.document_changed(p)
        runtime = await nap_lai_duong_goi(build_voice=False)
        hoi_dap = {"ok": True, "queued": True, "runtime": runtime,
                   "job": status["job"]}
    except Exception as e:
        logger.exception("Tri thức: không gỡ được Q&A của %s/%s", nhom, ten_goc)
        hoi_dap = {"error": f"Đã xóa tài liệu nhưng chưa gỡ được Q&A: {e}"}
    logger.info("Tri thức: xoá %s", p)
    return {"ok": True, "da_xoa": p.name, "hoi_dap": hoi_dap}


@router.post("/nap-lai")
async def nap_lai():
    """Đồng bộ thư mục tăng dần. Dùng khi sửa file thẳng trên đĩa."""
    rag = _rag()
    if rag is None:
        return {"error": "RAG chưa sẵn sàng"}
    t0 = time.perf_counter()
    kq = rag.ingest_directory(str(GOC)) or {}
    return {
        "ok": True,
        "ms": round((time.perf_counter() - t0) * 1000),
        "so_tai_lieu": kq.get("files", 0),
        "da_cap_nhat": kq.get("changed", 0),
        "giu_nguyen": kq.get("skipped", 0),
        "manh_da_don": kq.get("stale_chunks", 0),
    }
