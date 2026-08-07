"""Chấm CHẤT LƯỢNG câu trả lời của AI, chạy lặp lại được để so trước/sau.

Vì sao cần: prompt của dự án đã sửa nhiều lần và mỗi lần lại sinh tác dụng phụ ở
chỗ khác mà không ai biết (xem bộ nhớ: ví dụ trong prompt rò ra thành lãi suất
thật, "ạ" lải nhải, RAG lạc sản phẩm). Không có mốc đo thì mọi thay đổi prompt
đều là đoán.

Bộ câu lấy NGUYÊN VĂN từ bản ghi STT của các cuộc gọi thật, **kể cả câu bị phiên
âm méo** - đó mới là thứ mô hình thật sự nhận được. Câu gõ sạch cho kết quả đẹp
hơn thực tế và che mất đúng loại lỗi đang cần bắt.

Bốn tiêu chí, chấm tự động:
  1. TRẢ LỜI THẲNG - có chạm vào thứ khách hỏi không (`phai`)
  2. KHÔNG BỊA     - không nêu con số/khẳng định sai (`cam`)
  3. KHÔNG CHÉP    - không mở đầu bằng câu mẫu trong prompt khi tài liệu CÓ dữ liệu
  4. KHÔNG SAI QUYỀN LỢI - không biến hạn mức SẢN PHẨM thành hạn mức của KHÁCH

    python scripts/cham_chat_luong.py
    python scripts/cham_chat_luong.py --lan 3
    python scripts/cham_chat_luong.py --model tuvan-qwen
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SP = "vay tín chấp"

# Câu mẫu/câu lùi NẰM TRONG PROMPT. Mô hình chép chúng làm câu mở đầu bất kể ngữ
# cảnh - đo được 07-08: hỏi "bao lâu giải ngân" (tài liệu CÓ ghi 24 giờ) mà mở
# đầu bằng "em xin phép kiểm tra lại" rồi mới trả lời đúng ngay sau đó.
# Chỉ tính là lỗi khi câu hỏi ĐÓ có dữ liệu trong tài liệu (`co_du_lieu=True`).
CAU_CHEP = [
    r"xin phép kiểm tra lại và báo",
    r"xin phép gọi lại lúc khác",
    r"sẽ ghi nhận và có chuyên viên liên hệ",
    r"xin lỗi đã làm phiền",
]

# Biến hạn mức/lãi suất của SẢN PHẨM thành của riêng khách. Sai sự thật, và trong
# bán hàng tài chính thì đây là loại sai nặng nhất.
SAI_QUYEN_LOI = [
    r"hạn mức\s+(vay\s+)?(tín chấp\s+)?của\s+(anh|chị)\s+(là|lên)",
    r"(anh|chị)\s+(được|đã được)\s+duyệt",
    r"khoản vay của\s+(anh|chị)\s+là\s+\d",
]


def C(hoi, *, phai=None, cam=(), co_du_lieu=True, ghi=""):
    return dict(hoi=hoi, phai=phai, cam=list(cam), co_du_lieu=co_du_lieu, ghi=ghi)


# Nguyên văn STT từ các cuộc gọi thật 05-08 tới 07-08.
BO_CAU = [
    # --- có dữ liệu trong tài liệu, phải trả lời thẳng ---
    C("lãi suất vay tín chấp bên em bao nhiêu một năm",
      phai=r"7[.,]9", ghi="lãi suất tín chấp = 7.9%"),
    C("thuế vay tối đa được bao nhiêu tiền",
      phai=r"500|năm trăm", ghi="hạn mức 500 triệu (câu STT méo: 'thuế' = 'thế')"),
    C("vay tín chấp thì cần giấy tờ gì",
      phai=r"CMND|CCCD|căn cước", ghi="giấy tờ"),
    C("bao lâu thì được giải ngân",
      phai=r"24|hai mươi tư|hai tư", ghi="24 giờ"),
    C("anh muốn vay năm mươi triệu",
      phai=r"50|năm mươi|được|có thể|7[.,]9", ghi="nêu số cụ thể, phải bám theo"),

    # --- câu HỎI ĐƯỢC/KHÔNG: phải có lời khẳng định ---
    # Nhận cả "có thể vay": lúc đầu chỉ bắt `\bđược\b` và bộ chấm báo hỏng câu
    # "anh có thể vay đến 400 triệu đồng ạ" - vốn là câu trả lời đúng và thẳng.
    # Bộ chấm quá chặt thì nó tự tạo ra lỗi giả và che mất lỗi thật.
    C("ờ thế em anh muốn may tầm bốn trăm được không",
      phai=r"\bđược\b|có thể vay", ghi="400 < 500 nên phải khẳng định, không đọc lại hạn mức"),
    C("anh vay ba trăm triệu có được không",
      phai=r"\bđược\b|có thể vay", ghi="300 < 500 nên phải khẳng định"),

    # --- hỏi số tiền chứ không hỏi tỉ lệ ---
    C("cho anh số lãi phải chi trả bao nhiêu",
      phai=r"7[.,]9",
      cam=[r"anh có thể hỏi", r"anh cứ hỏi"],
      ghi="phải nêu lãi suất, KHÔNG bảo khách hỏi lại thứ vừa hỏi"),

    # --- câu méo / cụt: phải đoán ý hoặc hỏi lại, KHÔNG bịa ---
    C("em tư vấn giúp anh vẫn giúp anh còn vay bên mình",
      cam=[r"của anh là \d", r"của chị là \d"],
      ghi="câu méo - không được biến hạn mức sản phẩm thành của khách"),
    C("tìm ra chưa", co_du_lieu=False,
      ghi="câu cụt - nên hỏi lại cho rõ"),
    C("nghe thì anh nói không", co_du_lieu=False,
      ghi="câu méo nặng - nên hỏi lại"),
    C("ờ vay trong tháng sau",
      ghi="khách nêu thời điểm - phải bám tiếp"),
    C("lâu", co_du_lieu=False,
      ghi="một từ - nên hỏi lại"),

    # --- mở đầu cuộc gọi ---
    C("ơ sao em biết cả anh",
      ghi="khách ngạc nhiên - phải giải thích ngắn rồi vào việc"),
    C("em tư vấn cho anh về khoản vay bên mình này",
      phai=r"tín chấp|hạn mức|lãi suất", ghi="mời tư vấn - phải vào nội dung"),

    # --- ngoài phạm vi / kết thúc ---
    C("được rồi mai anh gọi lại cho em nhé", co_du_lieu=False,
      ghi="khách chốt - phải cảm ơn và kết, không hỏi thêm"),
    C("anh bận lắm", co_du_lieu=False,
      ghi="từ chối - xin lỗi và hẹn lại"),
    C("bên em có cho vay mua ô tô không", co_du_lieu=False,
      ghi="ngoài sản phẩm - ghi nhận, không bịa"),
]


def cham_mot(cau: dict, tra_loi: str) -> list[str]:
    """Trả về danh sách lỗi. Rỗng = đạt."""
    loi = []
    t = tra_loi.strip()
    if not t:
        return ["rỗng"]

    if cau["phai"] and not re.search(cau["phai"], t, re.I):
        loi.append("không trả lời thẳng")
    for c in cau["cam"]:
        if re.search(c, t, re.I):
            loi.append("nói điều bị cấm")
            break
    if cau["co_du_lieu"]:
        for c in CAU_CHEP:
            if re.search(c, t, re.I):
                loi.append("chép câu mẫu")
                break
    for c in SAI_QUYEN_LOI:
        if re.search(c, t, re.I):
            loi.append("sai quyền lợi")
            break
    return loi


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=2, help="chạy mỗi câu mấy lần")
    ap.add_argument("--model", default=None, help="ép model khác model trong .env")
    ap.add_argument("--chi-tiet", action="store_true", help="in cả câu trả lời")
    ap.add_argument("--tho", action="store_true",
                    help="chấm văn bản THÔ từ LLM, bỏ qua các lớp dọn của pipeline")
    ap.add_argument("--prompt-cu", action="store_true",
                    help="dựng lại prompt TRƯỚC bản sửa 07-08, để A/B trong cùng phiên")
    a = ap.parse_args()

    from backend.pipeline.text_normalizer import (bo_cau_lui_thua, chan_so_sai,
                                                  sua_xung_ho)
    from backend.services import llm_service as L
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    if a.prompt_cu:
        # Dựng lại ĐÚNG hai chỗ đã sửa 07-08. Cần A/B trong CÙNG một phiên vì
        # temperature 0.7 cho nhiễu lớn: hai lần chạy liên tiếp cùng cấu hình đã
        # ra 92% rồi 86%, tức so hai lần chạy khác nhau là vô nghĩa.
        L.CORE_RULES = (L.CORE_RULES
            .replace(
                "2. CÂU ĐẦU TIÊN phải TRẢ LỜI THẲNG thứ khách vừa hỏi, rồi mới nói thêm.",
                "2. Mỗi lượt trả lời TỐI ĐA 2 câu, TỐI ĐA 25 từ.")
            .replace(
                "   Sau đó TỐI ĐA 3 câu, TỐI ĐA 45 từ cả lượt. Đây là cuộc gọi thoại, không phải chat.",
                ""))
        L.CORE_REMINDER = ('NHẮC LẠI TRƯỚC KHI TRẢ LỜI: tối đa 2 câu, tối đa 25 từ, '
                           'mở đầu bằng "Dạ", xưng "em" gọi khách "anh/chị".')
        L._FALLBACK_EXAMPLES = L._FALLBACK_EXAMPLES[1:]   # bỏ ví dụ trả lời thẳng
        print("(đang dùng PROMPT CŨ để đối chứng)")

    def don(t: str, tai_lieu: str) -> str:
        """Đúng chuỗi dọn mà `_don_loi` của pipeline chạy trước khi đưa sang TTS.

        Không có bước này thì bộ chấm đo văn bản THÔ chứ không phải thứ khách
        nghe, và mọi lớp chặn bằng code trông như vô tác dụng. Đã mắc: thêm
        `bo_cau_lui_thua` xong chấm vẫn báo "chép câu mẫu" y nguyên.
        `BotLichSu` bỏ qua vì nó mang trạng thái xuyên lượt, không tái lập được ở đây.
        """
        if a.tho:
            return t
        # `chan_so_sai` trả về (văn bản, ghi chú) chứ không phải chuỗi.
        return chan_so_sai(bo_cau_lui_thua(sua_xung_ho(t)), tai_lieu)[0]

    rag_s = RAGService()
    rag_s.load()
    llm = LLMService()
    if a.model:
        llm.model = a.model
    print(f"model: {llm.model} | {a.lan} lần/câu | {len(BO_CAU)} câu\n")

    tong, dat = 0, 0
    dem_loi: dict[str, int] = {}
    for cau in BO_CAU:
        ngu_canh = await rag_s.retrieve(f"{SP} {cau['hoi']}", top_k=2, san_pham=SP)
        sysp = llm.build_system_prompt(
            customer_name="anh Hải", product=SP, rag_context=ngu_canh,
            gioi_tinh="male", gioi_tinh_do_tin=0.75)
        ket = []
        for _ in range(a.lan):
            t = ""
            try:
                async for tok in llm.stream_response(
                        [{"role": "user", "content": cau["hoi"]}], sysp):
                    t += tok
            except Exception as e:
                t = f"[LỖI {e}]"
            t = don(t, ngu_canh)
            loi = cham_mot(cau, t)
            ket.append((t.strip(), loi))
            tong += 1
            if not loi:
                dat += 1
            for x in loi:
                dem_loi[x] = dem_loi.get(x, 0) + 1

        so_dat = sum(1 for _, l in ket if not l)
        dau = "OK  " if so_dat == a.lan else ("....." if so_dat else "HỎNG")
        print(f"{dau} {so_dat}/{a.lan}  {cau['hoi'][:52]:<54} {cau['ghi']}")
        for t, l in ket:
            if l or a.chi_tiet:
                print(f"        [{', '.join(l) if l else 'đạt'}] {t[:150]}")

    print(f"\n{'='*80}")
    print(f"ĐẠT {dat}/{tong} = {dat*100//max(tong,1)}%")
    if dem_loi:
        print("Lỗi theo loại: " + ", ".join(f"{k} {v}" for k, v in
                                            sorted(dem_loi.items(), key=lambda x: -x[1])))
    return 0


raise SystemExit(asyncio.run(main()))
