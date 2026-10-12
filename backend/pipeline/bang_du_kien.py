"""Bảng dữ kiện của từng sản phẩm, đọc thẳng từ tài liệu trong `knowledge/products`.

VÌ SAO CÓ TỆP NÀY. Đo 11-10-2026 trên kho thật của máy Win: 4.303 trong 8.548
câu trả lời chép cứng con số của tài liệu ("lãi suất 6%/năm", "tối đa 10 tỷ").
Tài liệu đổi một con số thì cả nghìn câu thành sai, và cách chữa cũ là TẮT hết
đáp án của tài liệu đó rồi nhờ mô hình soạn lại. Ở đây con số chỉ sống ở MỘT
nơi là tài liệu; câu trả lời giữ chỗ trống kiểu `{tiet_kiem.ky_han_36_thang}` và
được điền lúc nạp kho.

Không có danh sách sản phẩm hay danh sách loại số liệu nào trong mã: sản phẩm là
các tệp `.md` đang có, khoá của một dữ kiện là nhãn của chính dòng đó trong tài
liệu ("- Phí thường niên: 400.000đ/năm" -> `phi_thuong_nien`). Thêm một dòng vào
tài liệu là có thêm một dữ kiện, không sửa mã.

Thứ duy nhất ghi cứng là TỪ ĐƠN VỊ của tiếng Việt (triệu, tháng, tuổi...), vì
đó là ngôn ngữ chứ không phải dữ liệu sản phẩm.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.pipeline.ngu_canh_tai_lieu import _doc_tep, _goc_mac_dinh, _ma

# Đơn vị -> (loại, hệ số quy về đơn vị gốc của loại). "năm" quy về tháng để
# "60 tháng" trong tài liệu khớp "5 năm" trong câu trả lời.
_DON_VI = {
    "%": ("phan_tram", 1), "phần trăm": ("phan_tram", 1),
    "tỷ": ("tien", 10**9), "tỉ": ("tien", 10**9), "triệu": ("tien", 10**6),
    "tr": ("tien", 10**6), "nghìn": ("tien", 1000), "ngàn": ("tien", 1000),
    "k": ("tien", 1000), "đồng": ("tien", 1), "đ": ("tien", 1),
    "vnd": ("tien", 1), "vnđ": ("tien", 1),
    "tháng": ("thang", 1), "năm": ("thang", 12),
    "ngày": ("ngay", 1), "giờ": ("gio", 1), "phút": ("phut", 1),
    "tuổi": ("tuoi", 1), "lần": ("lan", 1),
}
_SO = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)[ \t]*("
    + "|".join(sorted((re.escape(k) for k in _DON_VI), key=len, reverse=True))
    + r")?(?![a-zà-ỹ])", re.I)
# "12 - 60 tháng", "10-50 triệu", "22 đến 60 tuổi": số đầu mượn đơn vị số sau.
_NOI_KHOANG = re.compile(r"^[ \t]*(?:-|–|—|đến|tới)[ \t]*$", re.I)
_CHO_TRONG = re.compile(r"\{([a-z0-9_]+(?:\.[a-z0-9_]+){1,2})(?:\|(\d+)(s)?)?\}")
_DAU_DONG = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")


@dataclass(frozen=True)
class So:
    """Một con số trong câu: giá trị đã quy đổi, loại, và đúng chữ đã viết."""
    gia_tri: Decimal
    loai: str            # tien | phan_tram | thang | ngay | gio | phut | tuoi | lan | ""
    chu: str             # "500 triệu", "7.9%", "12 tháng" (đã mượn đơn vị)
    tran: str            # chỉ con số như đã viết: "500", "7.9", "12"
    dau: int
    cuoi: int


@dataclass(frozen=True)
class DuKien:
    san_pham: str        # mã tệp: "vay_tin_chap"
    muc: str             # mã tiêu đề `##`: "thong_tin_san_pham"
    khoa: str            # mã nhãn: "lai_suat"
    nhan: str            # nhãn nguyên văn: "Lãi suất"
    gia_tri: str         # phần sau nhãn: "từ 7.9%/năm"
    cau_goc: str         # trọn dòng trong tài liệu
    dong: int            # số dòng, tính từ 1
    so: tuple[So, ...]   # con số của GIÁ TRỊ - thứ câu trả lời được phép điền
    so_nhan: tuple[So, ...] = ()   # con số nằm trong NHÃN: "Kỳ hạn 12 tháng"


@dataclass(frozen=True)
class BangDuKien:
    san_pham: str
    phien_ban: str       # băm nội dung tài liệu; đổi một ký tự là đổi phiên bản
    du_kien: tuple[DuKien, ...]

    def tim(self, khoa: str, muc: str = "") -> DuKien | None:
        """Dữ kiện theo khoá; khoá trùng ở nhiều mục thì phải nêu mục.

        Trùng mà không nêu mục -> None chứ không đoán: điền nhầm "lãi suất" của
        mục ưu đãi vào câu hỏi lãi suất thường là sai cam kết với khách.
        """
        trung = [d for d in self.du_kien
                 if d.khoa == khoa and (not muc or d.muc == muc)]
        return trung[0] if len(trung) == 1 else None

    def moi_so(self) -> set[tuple[str, Decimal]]:
        return {(s.loai, s.gia_tri) for d in self.du_kien
                for s in d.so + d.so_nhan if s.loai}


def _thap_phan(chu: str) -> Decimal | None:
    """"500.000" -> 500000, "7.9" / "7,9" -> 7.9, "1.250,5" -> 1250.5."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", chu):
        chu = re.sub(r"[.,]", "", chu)
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", chu):
        chu = chu.replace(".", "").replace(",", ".")
    else:
        chu = chu.replace(",", ".")
    try:
        return Decimal(chu)
    except InvalidOperation:
        return None


def tach_so(cau: str) -> list[So]:
    """Mọi con số trong `cau`, kèm đơn vị. Số trần (không đơn vị) có loại ""."""
    tho = []
    for m in _SO.finditer(cau):
        v = _thap_phan(m.group(1))
        if v is not None:
            tho.append((v, (m.group(2) or "").lower(), m))
    ra: list[So] = []

    def het(m: re.Match) -> int:
        # Không có đơn vị thì con số dừng ngay sau chữ số, không nuốt dấu cách.
        return m.end(2) if m.group(2) else m.end(1)

    for i, (v, dv, m) in enumerate(tho):
        cuoi = het(m)
        chu = cau[m.start():cuoi]
        if not dv and i + 1 < len(tho) and tho[i + 1][1] \
                and _NOI_KHOANG.match(cau[cuoi:tho[i + 1][2].start()]):
            dv = tho[i + 1][1]
            dv_chu = cau[tho[i + 1][2].start(2):tho[i + 1][2].end(2)]
            chu = f"{chu}{'' if dv_chu == '%' else ' '}{dv_chu}"
        loai, he_so = _DON_VI.get(dv, ("", 1))
        # "triệu đồng", "nghìn đồng": chữ "đồng" theo sau thuộc về con số này.
        duoi = re.match(r"[ \t]*(đồng|đ|vnd|vnđ)\b", cau[cuoi:], re.I) \
            if loai == "tien" and he_so > 1 else None
        if duoi:
            cuoi += duoi.end()
            chu = cau[m.start():cuoi]
        ra.append(So(v * he_so, loai, chu, m.group(1), m.start(), cuoi))
    return ra


def _nhan_va_gia_tri(dong: str) -> tuple[str, str]:
    """"Lãi suất: từ 7.9%/năm" -> ("Lãi suất", "từ 7.9%/năm").

    Dòng không có nhãn ("Từ 18 tuổi trở lên") lấy phần chữ đứng trước con số
    đầu làm nhãn, tối đa bốn từ - đủ ổn định khi người soạn đổi con số, và đó
    đúng là thứ được phép đổi mà khoá không đổi.
    """
    if ":" in dong:
        nhan, _, gt = dong.partition(":")
        if nhan.strip() and gt.strip() and len(nhan) <= 60:
            return nhan.strip(), gt.strip()
    so = _SO.search(dong)
    dau = dong[:so.start()] if so else dong
    tu = re.findall(r"[^\W\d_]+", dau)[:4]
    if len(tu) < 2:               # "Từ 18 tuổi trở lên": một chữ "từ" không đủ phân biệt
        tu = re.findall(r"[^\W\d_]+", dong)[:4]
    return " ".join(tu), dong.strip()


def doc_bang(san_pham: str, noi_dung: str) -> BangDuKien:
    """Tài liệu markdown -> bảng dữ kiện. Chỉ nhận dòng CÓ con số kèm đơn vị."""
    ma_sp = _ma(san_pham)
    muc = ""
    ra: list[DuKien] = []
    da_co: dict[tuple[str, str], int] = {}
    for i, tho in enumerate(noi_dung.splitlines(), 1):
        dong = tho.strip()
        if not dong:
            continue
        if dong.startswith("#"):
            muc = _ma(dong.lstrip("#"))
            continue
        than = _DAU_DONG.sub("", dong)
        so = tuple(s for s in tach_so(than))
        if not any(s.loai for s in so):
            continue
        nhan, gia_tri = _nhan_va_gia_tri(than)
        khoa = _ma(nhan)
        if not khoa:
            continue
        # Hai dòng cùng nhãn trong MỘT mục (hai dòng "Ví dụ"): đánh số để không
        # dòng nào che dòng nào. Cùng nhãn ở hai mục thì phân biệt bằng mục.
        lan = da_co.get((muc, khoa), 0) + 1
        da_co[(muc, khoa)] = lan
        if lan > 1:
            khoa = f"{khoa}_{lan}"
        so_gt = tuple(tach_so(gia_tri))
        ra.append(DuKien(ma_sp, muc, khoa, nhan, gia_tri, than, i, so_gt or so,
                         tuple(tach_so(nhan)) if so_gt and gia_tri != than else ()))
    bam = hashlib.sha256(noi_dung.encode("utf-8")).hexdigest()[:16]
    return BangDuKien(ma_sp, bam, tuple(ra))


_NHO: dict[str, BangDuKien] = {}


def _thu_muc(goc: str | None) -> str:
    return os.path.join(goc or _goc_mac_dinh(), "knowledge", "products")


def cac_san_pham(goc: str | None = None) -> list[str]:
    """Mã các sản phẩm đang có tài liệu. Đây là danh mục sản phẩm duy nhất."""
    try:
        return sorted(t[:-3] for t in os.listdir(_thu_muc(goc)) if t.endswith(".md"))
    except OSError:
        return []


def bang_cua(san_pham: str, goc: str | None = None) -> BangDuKien | None:
    """Bảng của một sản phẩm, đọc lại khi tệp đổi (theo mtime + kích thước)."""
    ma = _ma(san_pham or "")
    if not ma:
        return None
    noi_dung = _doc_tep(os.path.join(_thu_muc(goc), f"{ma}.md"))
    if not noi_dung.strip():
        return None
    bam = hashlib.sha256(noi_dung.encode("utf-8")).hexdigest()[:16]
    cu = _NHO.get(f"{goc or ''}|{ma}")
    if cu and cu.phien_ban == bam:
        return cu
    moi = doc_bang(ma, noi_dung)
    _NHO[f"{goc or ''}|{ma}"] = moi
    return moi


def phien_ban_chung(goc: str | None = None) -> str:
    """Một mã cho toàn bộ tài liệu sản phẩm; đổi bất kỳ tệp nào là đổi mã."""
    cac = [(sp, bang_cua(sp, goc)) for sp in cac_san_pham(goc)]
    return hashlib.sha256("|".join(
        f"{sp}:{b.phien_ban if b else ''}" for sp, b in cac).encode()).hexdigest()[:16]


def co_cho_trong(cau: str) -> bool:
    return bool(_CHO_TRONG.search(cau or ""))


def dien(cau: str, goc: str | None = None) -> tuple[str, list[str]]:
    """Điền chỗ trống trong `cau`. Trả (câu đã điền, các chỗ trống KHÔNG điền được).

    `{vay_tin_chap.lai_suat}`            -> trọn giá trị: "từ 7.9%/năm"
    `{vay_tin_chap.thoi_han|2}`          -> con số thứ hai, kèm đơn vị: "60 tháng"
    `{vay_tin_chap.thoi_han|1s}`         -> chỉ con số, không đơn vị: "12"
    `{the_tin_dung.cac_loai_the.the_gold|3}` -> nêu cả mục khi khoá trùng

    Còn chỗ trống không điền được thì nơi gọi PHẢI bỏ câu đó: đọc "{...}" cho
    khách nghe, hay đọc câu thiếu con số, đều tệ hơn để mô hình tự trả lời.
    """
    thieu: list[str] = []

    def thay(m: re.Match) -> str:
        phan = m.group(1).split(".")
        bang = bang_cua(phan[0], goc)
        dk = bang.tim(phan[-1], phan[1] if len(phan) == 3 else "") if bang else None
        if dk is None:
            thieu.append(m.group(0))
            return m.group(0)
        if m.group(2) is None:
            return dk.gia_tri
        vt = int(m.group(2))
        if not 1 <= vt <= len(dk.so):
            thieu.append(m.group(0))
            return m.group(0)
        return dk.so[vt - 1].tran if m.group(3) else dk.so[vt - 1].chu

    return _CHO_TRONG.sub(thay, cau or ""), thieu


def so_lech(cau: str, san_pham: str, goc: str | None = None) -> list[So]:
    """Con số trong `cau` mà tài liệu của `san_pham` KHÔNG có.

    Dùng để soi kho: câu chép cứng con số cũ sẽ lộ ra ngay sau khi tài liệu
    đổi. Số trần không đơn vị bị bỏ qua (số thứ tự, "nhóm 3", "KT3").
    """
    bang = bang_cua(san_pham, goc)
    if bang is None:
        return []
    co = bang.moi_so()
    return [s for s in tach_so(cau) if s.loai and (s.loai, s.gia_tri) not in co]


def goi_y_cho_trong(cau: str, san_pham: str, goc: str | None = None) -> tuple[str, int, int]:
    """Đổi con số chép cứng trong `cau` thành chỗ trống.

    Trả (câu mới, số con số đã đổi, số con số KHÔNG đổi được).

    Một con số trong câu trả lời đóng một trong hai vai, và lẫn hai vai là sai
    nặng: trong "gửi 36 tháng có lãi suất 6%", 6% là GIÁ TRỊ lấy từ tài liệu còn
    36 tháng là ĐIỀU KIỆN khách chọn. Đổi "36 tháng" thành chỗ trống của dòng
    "Kỳ hạn: 1 - 36 tháng" thì hôm tài liệu nâng trần lên 48, câu thành "gửi 48
    tháng có lãi suất 6%" - bịa. Nên:
    - mỗi con số được gán cho dữ kiện mà CẢ DÒNG của nó (nhãn + giá trị) khớp
      nhiều con số nhất của câu; hoà điểm thì để nguyên cho người duyệt;
    - con số nằm trong NHÃN của một dữ kiện đã chọn là điều kiện -> giữ nguyên.
      Tài liệu bỏ dòng đó thì chỗ trống đi kèm không điền được và câu bị loại.
    """
    bang = bang_cua(san_pham, goc)
    if bang is None or co_cho_trong(cau):
        return cau, 0, 0
    cac_so = [s for s in tach_so(cau) if s.loai]
    trong_cau = {(s.loai, s.gia_tri) for s in cac_so}

    def diem(dk: DuKien) -> int:
        return len({(s.loai, s.gia_tri) for s in dk.so + dk.so_nhan} & trong_cau)

    def ten(dk: DuKien) -> str:
        return (f"{dk.san_pham}.{dk.khoa}" if bang.tim(dk.khoa) is not None
                else f"{dk.san_pham}.{dk.muc}.{dk.khoa}")

    tu_cau = set(_ma(cau).split("_"))

    def trung_nhan(dk: DuKien) -> float:
        tu = [t for t in _ma(dk.nhan).split("_") if not t.isdigit()]
        return round(sum(t in tu_cau for t in tu) / len(tu), 3) if tu else 0.0

    chon: dict[int, tuple[DuKien, int]] = {}
    for s in cac_so:
        ung = [(dk, vt) for dk in bang.du_kien for vt, x in enumerate(dk.so, 1)
               if (x.loai, x.gia_tri) == (s.loai, s.gia_tri)]
        # Dòng nhiều con số đi thành BỘ ("vay 100 triệu trong 36 tháng thì trả
        # 3.4 triệu") chỉ được dùng khi câu nhắc đủ cả bộ. Khớp lẻ một số là
        # trùng hợp: "mức 200 triệu nằm trong hạn mức" nói về số khách nêu, đã
        # từng bị gán nhầm vào dòng ví dụ "vay 200 triệu...".
        ung = [(dk, vt) for dk, vt in ung if len(dk.so) < 3 or diem(dk) == len(
            {(x.loai, x.gia_tri) for x in dk.so + dk.so_nhan})]
        if not ung:
            continue
        # Hoà điểm con số thì xét tới chữ: "hoàn tiền 3%" thuộc dòng "Hoàn tiền"
        # chứ không thuộc dòng "Cashback: 1-3%". Vẫn hoà thì thôi, không đoán.
        cao = max((diem(dk), trung_nhan(dk)) for dk, _ in ung)
        nhat = [(dk, vt) for dk, vt in ung if (diem(dk), trung_nhan(dk)) == cao]
        if len({(dk.muc, dk.khoa) for dk, _ in nhat}) == 1:
            chon[s.dau] = nhat[0]
    dieu_kien = {(x.loai, x.gia_tri) for dk, _ in chon.values() for x in dk.so_nhan}

    doi = khong = 0
    ra = cau
    # Thay từ cuối về đầu để vị trí các con số phía trước không xê dịch.
    for s in sorted(cac_so, key=lambda s: -s.dau):
        if (s.loai, s.gia_tri) in dieu_kien:
            continue
        if s.dau not in chon:
            khong += 1
            continue
        dk, vt = chon[s.dau]
        # Số đầu của một khoảng ("12 - 60 tháng") không mang đơn vị trong câu:
        # điền lại cũng chỉ con số, không thì thành "12 tháng - 60 tháng".
        # Câu viết đơn vị khác tài liệu ("5 triệu" so với "5 triệu đồng") cũng
        # chỉ điền con số và giữ đơn vị của câu, để điền lại ra đúng câu cũ.
        nguon = dk.so[vt - 1]
        if cau[s.dau:s.cuoi].strip() == s.tran:
            ra = f"{ra[:s.dau]}{{{ten(dk)}|{vt}s}}{ra[s.cuoi:]}"
        elif s.chu != nguon.chu and s.tran == nguon.tran:
            cuoi_so = s.dau + cau[s.dau:s.cuoi].index(s.tran) + len(s.tran)
            ra = f"{ra[:s.dau]}{{{ten(dk)}|{vt}s}}{ra[cuoi_so:]}"
        else:
            ra = f"{ra[:s.dau]}{{{ten(dk)}|{vt}}}{ra[s.cuoi:]}"
        doi += 1
    return ra, doi, khong
