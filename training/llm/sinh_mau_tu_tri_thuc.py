"""Sinh mẫu train từ chính tài liệu tri thức đang dùng để tư vấn.

VÌ SAO CẦN. Fine-tune đòi tối thiểu 200 mẫu (MIN_SAMPLES trong api/training.py),
mà soạn tay 200 cặp hỏi-đáp đúng luật phong cách là việc không ai làm nổi - nên
trang Training LLM đứng im từ đầu dự án với đúng 5 mẫu ví dụ. Trong khi đó
`knowledge/` đã có sẵn nội dung, và chính nó là thứ AI đọc lúc tư vấn thật.

BA CHỖ NỐI VÀO HỆ THỐNG, đừng thay bằng bản tự viết:

  `cat_manh`          cắt tài liệu ĐÚNG như RAG cắt, nên mỗi mảnh là đúng đơn vị
                      ngữ cảnh mà model sẽ nhận lúc chạy thật.
  `doc_so_trong_cau`  đọc số thành chữ ĐÚNG như đường thoại đọc. Dataset còn chữ
                      số thì model sinh ra chữ số, và system prompt ép cỡ nào
                      cũng thua - đo được: 17% mẫu dính số làm điểm phong cách
                      tụt từ 7/8 xuống 3/8 (xem training/llm/so_thanh_chu.py).
  `kiem_tra_tra_loi`  soi theo đúng luật của system prompt lúc chạy.

Thà ít mẫu sạch còn hơn nhiều mẫu dạy hỏng: cặp nào chuẩn hoá xong vẫn phạm luật
thì bỏ, và ghi rõ bỏ vì gì.

    python training/llm/sinh_mau_tu_tri_thuc.py --so-cap 20
    python training/llm/sinh_mau_tu_tri_thuc.py --nhom products --so-cap 10
"""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(GOC))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from backend.core.dataset_rules import kiem_tra_tra_loi  # noqa: E402
from backend.pipeline.text_normalizer import doc_so_trong_cau  # noqa: E402
from backend.services.rag_service import cat_manh  # noqa: E402

THU_MUC_TRI_THUC = GOC / "knowledge"
THU_MUC_RA = GOC / "data" / "training"

SYSTEM = ("Bạn là nhân viên tư vấn ngân hàng, đang gọi điện cho khách. "
          "Trả lời tối đa 2 câu, xưng em, gọi khách là anh/chị.")

# Model nhỏ hay chèn lời dẫn, tự đánh số, kẻ gạch ngang. Bắt đúng nhãn ở đầu
# dòng chứ không tách cả khối, để mấy thứ đó không làm mất cặp.
_NHAN = re.compile(r"^\s*(?:[-*•]\s*)?(?:\d+[.)]\s*)?(KH|TV)\s*[:：]\s*(.+?)\s*$",
                   re.IGNORECASE)


def doc_cap(text: str) -> list[tuple[str, str]]:
    """Rút các cặp (khách hỏi, tư vấn đáp) từ thứ model trả về.

    Một câu hỏi không có câu đáp đi liền sau thì bỏ - ghép nhầm với câu đáp của
    cặp khác là dạy model trả lời lạc đề.
    """
    cap: list[tuple[str, str]] = []
    hoi = None
    for dong in (text or "").splitlines():
        m = _NHAN.match(dong)
        if not m:
            continue
        vai, noi_dung = m.group(1).upper(), m.group(2).strip()
        if not noi_dung:
            continue
        if vai == "KH":
            hoi = noi_dung
        elif hoi:
            cap.append((hoi, noi_dung))
            hoi = None
    return cap


# Khoảng viết bằng gạch nối: "3-5 ngày", "1-2%". Đọc số xong nó thành "ba-năm",
# "một-hai" - TTS phát ra "ba năm" nghe như một khoảng THỜI GIAN, và dataset thì
# dạy model viết dấu gạch nối, thứ TTS không đọc được. Bắt được trên mẫu sinh
# thật từ faq_banking.md ("nợ xấu nhóm 3-5") và vay_mua_nha.md ("phí 1-2%").
#
# Chỉ đụng gạch nối GIỮA HAI SỐ, để không phá từ ghép.
_KHOANG_GACH = re.compile(r"(\d)\s*[-–—]\s*(\d)")


def chuan_hoa_tra_loi(s: str) -> str:
    """Đọc số thành chữ, y như đường thoại làm trước khi đưa cho TTS."""
    s = _KHOANG_GACH.sub(r"\1 đến \2", (s or "").strip())
    return doc_so_trong_cau(s)


def loc_cap(hoi: str, tra_loi: str) -> tuple[bool, str]:
    """Giữ hay bỏ, kèm lý do bỏ. Chỉ tính LỖI, cảnh báo thì vẫn giữ.

    Cảnh báo của `kiem_tra_tra_loi` là lệch thói quen giọng nói ("thiếu chữ ạ"),
    không phải vi phạm luật - loại theo nó thì gần như không còn mẫu nào.
    """
    if not (hoi or "").strip():
        return False, "thiếu câu hỏi"
    loi, _ = kiem_tra_tra_loi(tra_loi)
    return (False, "; ".join(loi)) if loi else (True, "")


def dung_prompt(manh: str, so_cap: int) -> str:
    """Prompt sinh mẫu.

    Luật ở đây phải khớp `dataset_rules`, không thì cặp nào sinh ra cũng bị bộ
    soi loại và cả lượt gọi thành vô ích.
    """
    return f"""Đọc đoạn tài liệu ngân hàng dưới đây, rồi viết {so_cap} cặp hội thoại
giữa KHÁCH HÀNG và NHÂN VIÊN TƯ VẤN qua điện thoại.

TÀI LIỆU:
\"\"\"
{manh}
\"\"\"

QUY TẮC BẮT BUỘC cho câu của tư vấn viên:
- Tối đa 2 câu, tối đa 25 từ.
- Viết số thành chữ: 7.9% viết là "bảy phẩy chín phần trăm".
- Mở đầu bằng "Dạ", xưng "em", gọi khách là "anh chị", kết câu có "ạ".
- Không gạch đầu dòng, không liệt kê quá hai thứ, không emoji, không markdown.
- Chỉ dùng thông tin có trong tài liệu trên. Không bịa thêm số.

ĐỊNH DẠNG - mỗi cặp đúng hai dòng, không thêm gì khác:
KH: <câu khách hỏi>
TV: <câu tư vấn trả lời>"""


def lam_mau(hoi: str, tra_loi: str, system: str = SYSTEM) -> dict:
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": hoi},
        {"role": "assistant", "content": tra_loi},
    ]}


def duong_dan_ngan(p: Path) -> str:
    """Đường dẫn gọn để in ra, KHÔNG bao giờ ném lỗi.

    Bắt được khi chạy thật: `--ra data\\training\\x.jsonl` làm `relative_to`
    ném ValueError ngay dòng in kết quả - SAU KHI file đã ghi xong. Script thoát
    mã lỗi, JobRunner báo job thất bại, trong khi dataset đã nằm trên đĩa.
    """
    try:
        return str(p.resolve().relative_to(GOC))
    except ValueError:
        return str(p)


def _cac_manh(nhom: str | None) -> list[tuple[str, str]]:
    """(tên tài liệu, mảnh) cho mọi tài liệu được chọn."""
    ra = []
    for p in sorted(THU_MUC_TRI_THUC.rglob("*.md")) + sorted(THU_MUC_TRI_THUC.rglob("*.txt")):
        if nhom and p.parent.name != nhom:
            continue
        for m in cat_manh(p.read_text(encoding="utf-8", errors="replace")):
            ra.append((p.stem, m))
    return ra


async def sinh(nhom: str | None, so_cap: int, so_lan_thu: int, ra_path: Path) -> dict:
    import ollama

    from backend.config import settings

    client = ollama.AsyncClient(host=settings.ollama_base_url)
    manh = _cac_manh(nhom)
    if not manh:
        print("Không có tài liệu nào trong knowledge/. Thêm tài liệu trước đã.")
        return {"giu": 0, "bo": 0}

    print(f"{len(manh)} mảnh từ {len({t for t, _ in manh})} tài liệu, "
          f"xin {so_cap} cặp mỗi mảnh -> tối đa {len(manh) * so_cap} mẫu")

    mau: list[dict] = []
    ly_do_bo: dict[str, int] = {}
    trung = set()

    for i, (ten, noi_dung) in enumerate(manh, 1):
        t0 = time.perf_counter()
        giu_manh = 0
        for lan in range(1, so_lan_thu + 1):
            can = so_cap - giu_manh
            if can <= 0:
                break
            try:
                r = await client.chat(
                    model=settings.ollama_model,
                    messages=[{"role": "user", "content": dung_prompt(noi_dung, can)}],
                    think=False,
                    # temperature cao hơn đường thoại: lần thử lại phải ra câu
                    # KHÁC, không thì thử lại chỉ tốn thời gian.
                    options={"num_predict": 100 * can + 200,
                             "temperature": 0.6 + 0.1 * lan},
                )
                out = (r.get("message") or {}).get("content") if isinstance(r, dict) \
                    else getattr(getattr(r, "message", None), "content", "")
            except Exception as e:
                print(f"  [{i}/{len(manh)}] {ten}: gọi model lỗi: {e}")
                break

            for hoi, tl in doc_cap(out or ""):
                tl = chuan_hoa_tra_loi(tl)
                ok, vi_sao = loc_cap(hoi, tl)
                if not ok:
                    ly_do_bo[vi_sao] = ly_do_bo.get(vi_sao, 0) + 1
                    continue
                khoa = hoi.lower().strip()
                if khoa in trung:
                    ly_do_bo["trùng câu hỏi"] = ly_do_bo.get("trùng câu hỏi", 0) + 1
                    continue
                trung.add(khoa)
                mau.append(lam_mau(hoi, tl))
                giu_manh += 1
                if giu_manh >= so_cap:
                    break

        print(f"  [{i}/{len(manh)}] {ten}: giữ {giu_manh}/{so_cap} "
              f"({time.perf_counter() - t0:.1f}s) — tổng {len(mau)}")

    ra_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ra_path, "w", encoding="utf-8") as f:
        for m in mau:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    bo = sum(ly_do_bo.values())
    print(f"\nGiữ {len(mau)} mẫu, bỏ {bo}.")
    for vi_sao, n in sorted(ly_do_bo.items(), key=lambda x: -x[1]):
        print(f"  bỏ {n:3d}: {vi_sao}")
    print(f"Đã ghi: {duong_dan_ngan(ra_path)}")
    if len(mau) < 200:
        print(f"CHÚ Ý: fine-tune cần tối thiểu 200 mẫu, đang có {len(mau)}. "
              "Tăng --so-cap hoặc thêm tài liệu vào knowledge/.")
    print("Mẫu là NHÁP ĐÃ QUA KIỂM, không phải dữ liệu vàng - đọc lại các con số "
          "trước khi train.")
    return {"giu": len(mau), "bo": bo}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nhom", default=None, help="products / faq / chinh_sach")
    ap.add_argument("--so-cap", type=int, default=20, help="số cặp mỗi mảnh")
    ap.add_argument("--so-lan-thu", type=int, default=3,
                    help="số lần hỏi lại model cho một mảnh khi chưa đủ cặp sạch")
    ap.add_argument("--ra", default=None, help="đường dẫn file .jsonl ra")
    a = ap.parse_args()

    ten = a.ra or (THU_MUC_RA / f"tu_tri_thuc_{time.strftime('%Y%m%d_%H%M')}.jsonl")
    kq = asyncio.run(sinh(a.nhom, max(1, a.so_cap), max(1, a.so_lan_thu), Path(ten)))
    sys.exit(0 if kq["giu"] else 1)


if __name__ == "__main__":
    main()
