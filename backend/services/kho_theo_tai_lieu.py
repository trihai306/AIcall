"""Giữ con số trong kho trả lời đi theo tài liệu, không chép cứng.

Trước 11-10-2026: tài liệu đổi một ký tự là `prepare_sources` TẮT rồi XOÁ mọi
đáp án sinh từ tài liệu đó và xếp hàng cho Qwen soạn lại, kèm dựng lại tiếng.
Đổi lãi suất 7.9 -> 8.5 cũng đi đúng đường đó, trong lúc chờ thì kho trống.

Ở đây mỗi đáp án có con số được giữ thêm một MẪU ở bảng phụ `hoi_dap_mau`
("lãi suất từ {vay_tin_chap.lai_suat|1}/năm"). Cột `hoi_dap.tra_loi` vẫn là câu
chữ đầy đủ như cũ - mọi nơi đang đọc cột đó (bộ chọn, dựng tiếng, trang quản
lý, `row_is_current`) không phải biết gì về mẫu. Khi tài liệu chỉ đổi CON SỐ
(cấu trúc chữ y nguyên), `ap_dung_doi_so` điền lại mẫu và ghi câu mới vào
`tra_loi`; đáp án không có mẫu mà còn nói con số cũ thì bị tắt riêng dòng đó.
Tài liệu đổi cả câu chữ thì vẫn đi đường soạn lại như trước.
"""

import hashlib
import logging
import re
import time

from backend.pipeline import bang_du_kien as bdk

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hoi_dap_mau (
 id TEXT PRIMARY KEY, mau TEXT NOT NULL, san_pham TEXT NOT NULL,
 updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tai_lieu_cau_truc (
 source_path TEXT PRIMARY KEY, cau_truc TEXT NOT NULL, phien_ban TEXT NOT NULL,
 updated_at REAL NOT NULL);
"""


def chuan_bi(conn) -> None:
    conn.executescript(_SCHEMA)


def cau_truc(noi_dung: str) -> str:
    """Băm của tài liệu sau khi che mọi con số: bằng nhau = chỉ đổi con số."""
    che = re.sub(r"\d+(?:[.,]\d+)*", "#", noi_dung or "")
    return hashlib.sha256(che.encode("utf-8")).hexdigest()[:16]


def san_pham_cua(rel: str) -> str:
    """"products/vay_tin_chap.md" -> "vay_tin_chap"; tệp khác -> ""."""
    m = re.fullmatch(r"products/([^/]+)\.(?:md|txt)", rel or "")
    return bdk._ma(m.group(1)) if m else ""


def mau_cho(tra_loi: str, san_pham: str, goc: str | None = None) -> str:
    """Mẫu của một câu trả lời, hoặc "" khi không lập được mẫu an toàn.

    An toàn = mọi con số đều gán được, và điền lại mẫu ra ĐÚNG câu đang có
    từng ký tự. Lệch một ký tự là lần điền sau sẽ âm thầm đổi câu đã duyệt (và
    phải dựng lại tiếng), nên thà để dòng đó chép cứng rồi soi bằng `so_lech`.
    """
    mau, doi, khong = bdk.goi_y_cho_trong(tra_loi, san_pham, goc)
    if not doi or khong:
        return ""
    lai, thieu = bdk.dien(mau, goc)
    return mau if not thieu and lai == tra_loi else ""


def lap_mau(conn, goc: str | None = None, *, ghi: bool = True) -> dict:
    """Lập mẫu cho mọi đáp án đang bật của các sản phẩm có tài liệu.

    Không sửa `hoi_dap`. Chạy lại bao nhiêu lần cũng được: dòng đã có mẫu mà
    câu chữ vẫn khớp thì giữ, câu chữ đã bị sửa tay thì lập lại theo câu mới.
    """
    chuan_bi(conn)
    sps = set(bdk.cac_san_pham(goc))
    dem = {"co_mau": 0, "chep_cung_con_dung": 0, "so_khong_co_trong_tai_lieu": 0,
           "khong_co_so": 0, "khong_gan_san_pham": 0}
    lech: list[tuple[str, str]] = []
    moi: list[tuple[str, str, str, float]] = []
    for ma, tra_loi, san_pham in conn.execute(
            "SELECT id, tra_loi, san_pham FROM hoi_dap WHERE bat = 1").fetchall():
        sp = bdk._ma(san_pham or "")
        if not any(s.loai for s in bdk.tach_so(tra_loi or "")):
            dem["khong_co_so"] += 1
        elif sp not in sps:
            dem["khong_gan_san_pham"] += 1
        elif bdk.so_lech(tra_loi, sp, goc):
            dem["so_khong_co_trong_tai_lieu"] += 1
            lech.append((ma, tra_loi))
        else:
            mau = mau_cho(tra_loi, sp, goc)
            if mau:
                dem["co_mau"] += 1
                moi.append((ma, mau, sp, time.time()))
            else:
                dem["chep_cung_con_dung"] += 1
    if ghi:
        with conn:
            conn.execute("DELETE FROM hoi_dap_mau")
            conn.executemany("INSERT INTO hoi_dap_mau VALUES (?,?,?,?)", moi)
            for sp in sps:
                bang = bdk.bang_cua(sp, goc)
                noi_dung = bdk._doc_tep(f"{bdk._thu_muc(goc)}/{sp}.md")
                conn.execute("INSERT OR REPLACE INTO tai_lieu_cau_truc VALUES (?,?,?,?)",
                             (f"products/{sp}.md", cau_truc(noi_dung),
                              bang.phien_ban if bang else "", time.time()))
    return {**dem, "lech": lech}


def chi_doi_so(conn, rel: str, noi_dung: str) -> bool:
    """Tài liệu `rel` có phải chỉ đổi con số so với lần lập mẫu gần nhất không."""
    if not san_pham_cua(rel):
        return False
    chuan_bi(conn)
    cu = conn.execute("SELECT cau_truc FROM tai_lieu_cau_truc WHERE source_path=?",
                      (rel,)).fetchone()
    return bool(cu) and cu[0] == cau_truc(noi_dung)


def ap_dung_doi_so(conn, rel: str, van_tay: str, goc: str | None = None) -> dict:
    """Viết lại đáp án của tài liệu `rel` theo con số mới. Gọi trong giao dịch.

    Chỉ gọi khi `chi_doi_so` trả True. Với từng đáp án đang bật của sản phẩm:
    - có mẫu, điền được, và câu mới không còn con số nào ngoài tài liệu
      -> ghi câu mới, đánh dấu cần dựng lại tiếng nếu câu đổi;
    - có mẫu mà không điền được, hoặc chép cứng mà nay lệch tài liệu -> tắt.
    `van_tay` là dấu vân tay mới của tài liệu, ghi vào nguồn gốc để
    `row_is_current` tiếp tục coi các dòng được giữ là còn hiệu lực.
    """
    sp = san_pham_cua(rel)
    bdk._NHO.pop(f"{goc or ''}|{sp}", None)
    now = time.time()
    mau = dict(conn.execute("SELECT id, mau FROM hoi_dap_mau WHERE san_pham=?", (sp,)))
    kq = {"viet_lai": 0, "giu_nguyen": 0, "tat": 0, "da_tat": []}
    for ma, tra_loi, san_pham in conn.execute(
            "SELECT id, tra_loi, san_pham FROM hoi_dap WHERE bat = 1").fetchall():
        if bdk._ma(san_pham or "") != sp:
            continue
        cau, thieu = bdk.dien(mau[ma], goc) if ma in mau else (tra_loi, [])
        if thieu or bdk.so_lech(cau, sp, goc):
            conn.execute("UPDATE hoi_dap SET bat=0, updated_at=? WHERE id=?", (now, ma))
            kq["tat"] += 1
            kq["da_tat"].append(ma)
        elif cau != tra_loi:
            conn.execute("UPDATE hoi_dap SET tra_loi=?, updated_at=? WHERE id=?",
                         (cau, now, ma))
            conn.execute("UPDATE answer_bank_entries SET voice_ready=0 WHERE hoi_dap_id=?",
                         (ma,))
            kq["viet_lai"] += 1
        else:
            kq["giu_nguyen"] += 1
    conn.execute("UPDATE answer_bank_entries SET source_hash=? WHERE source_path=? "
                 "AND hoi_dap_id IN (SELECT id FROM hoi_dap WHERE bat=1)", (van_tay, rel))
    bang = bdk.bang_cua(sp, goc)
    conn.execute("UPDATE tai_lieu_cau_truc SET phien_ban=?, updated_at=? WHERE source_path=?",
                 (bang.phien_ban if bang else "", now, rel))
    logger.info("Tài liệu %s chỉ đổi con số: viết lại %d đáp án, giữ %d, tắt %d",
                rel, kq["viet_lai"], kq["giu_nguyen"], kq["tat"])
    return kq
