"""Dựng lại bộ dữ liệu train theo lối CÓ TÀI LIỆU TRONG PROMPT.

VÌ SAO PHẢI LÀM LẠI. Bộ cũ (262 mẫu) có 0/262 mẫu kèm tài liệu - system prompt
chỉ vỏn vẹn một dòng "Bạn là nhân viên tư vấn...". Mô hình vì thế học được rằng
câu trả lời NẰM TRONG ĐẦU MÌNH, chưa bao giờ được dạy đọc tài liệu rồi mới nói.
Chạy thật ta đưa tài liệu vào thì nó bỏ qua, và vì trí nhớ chứa lãi suất của
NHIỀU sản phẩm (7.9 tín chấp, 6.5 mua nhà, 8-10 thả nổi...) nên nó trộn lẫn -
đo được nó nói ra cả "sáu phẩy chín", con số không hề có trong dữ liệu.

CÁCH LÀM. Mỗi mẫu gồm:
    system  = ĐÚNG prompt lúc chạy thật (gọi `llm.build_system_prompt`) kèm
              ngữ cảnh do CHÍNH RAG của hệ thống lấy về
    user    = câu khách hỏi
    assistant = câu trả lời TRÍCH TỪ tài liệu đó

Dùng lại chính hàm dựng prompt và chính RAG là điểm mấu chốt: train và chạy thật
phải nhìn thấy cùng một định dạng, lệch một chút là mô hình học sai chỗ.

BA LOẠI MẪU, thiếu loại nào cũng hỏng:
  1. TRÍCH SỐ      - hỏi lãi suất/hạn mức/thời hạn, đáp bằng số trong tài liệu
  2. ĐỐI CHIẾU     - CÙNG câu hỏi, KHÁC sản phẩm -> đáp phải khác. Đây mới là
                     thứ dạy mô hình rằng đáp án đến từ tài liệu chứ không phải
                     từ trí nhớ; thiếu nó thì nó vẫn học thuộc lòng.
  3. KHÔNG BIẾT    - tài liệu không có thông tin -> nói sẽ kiểm tra lại, KHÔNG bịa

    python scripts/dung_dataset_co_tai_lieu.py            # ghi ra data/training/
    python scripts/dung_dataset_co_tai_lieu.py --xem 3    # in thử 3 mẫu rồi thoát
"""

import argparse
import asyncio
import json
import random
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RA = PROJECT / "data" / "training"
CU = RA / "merged_dataset.jsonl"
MOI = RA / "dataset_co_tai_lieu.jsonl"

# ---------------------------------------------------------------- nội dung
# Số liệu lấy nguyên từ knowledge/. Viết SỐ bằng CHỮ SỐ - bộ đọc số ở
# text_normalizer lo phần đọc thành chữ, mô hình không phải tự chuyển (nó chuyển sai).

TIN_CHAP = "vay tín chấp"
MUA_NHA = "vay mua nhà"
THE = "thẻ tín dụng"
TIET_KIEM = "tiết kiệm"

# (sản phẩm, câu hỏi, câu trả lời)
MAU_TRICH_SO = [
    # --- vay tín chấp ---
    (TIN_CHAP, "lãi suất vay tín chấp bao nhiêu",
     "Dạ lãi suất vay tín chấp bên em từ 7.9% một năm ạ. Anh chị định vay khoảng bao nhiêu ạ?"),
    (TIN_CHAP, "cho hỏi lãi suất bên mình",
     "Dạ vay tín chấp lãi suất từ 7.9% một năm ạ. Anh chị cần vay bao nhiêu để em tư vấn ạ?"),
    (TIN_CHAP, "vay tín chấp được tối đa bao nhiêu",
     "Dạ hạn mức vay tín chấp lên đến 500 triệu đồng ạ. Anh chị cần khoảng bao nhiêu ạ?"),
    (TIN_CHAP, "vay được bao nhiêu tiền",
     "Dạ vay tín chấp tối đa 500 triệu đồng ạ. Còn tuỳ thu nhập của anh chị nữa ạ."),
    (TIN_CHAP, "vay trong bao lâu",
     "Dạ thời hạn vay tín chấp từ 12 đến 60 tháng ạ. Anh chị muốn trả trong bao lâu ạ?"),
    (TIN_CHAP, "bao lâu thì nhận được tiền",
     "Dạ bên em giải ngân trong vòng 24 giờ sau khi phê duyệt ạ."),
    (TIN_CHAP, "cần giấy tờ gì",
     "Dạ anh chị chuẩn bị căn cước và sao kê lương 3 tháng gần nhất ạ. Anh chị đang làm ở đâu ạ?"),
    (TIN_CHAP, "điều kiện vay thế nào",
     "Dạ anh chị từ 22 đến 60 tuổi và thu nhập từ 5 triệu một tháng là được ạ."),
    (TIN_CHAP, "thu nhập bao nhiêu thì vay được",
     "Dạ thu nhập ổn định từ 5 triệu đồng một tháng trở lên là vay được ạ."),
    (TIN_CHAP, "vay 100 triệu thì trả bao nhiêu một tháng",
     "Dạ vay 100 triệu trong 36 tháng thì trả khoảng 3.4 triệu một tháng ạ."),
    (TIN_CHAP, "vay 200 triệu trả góp thế nào",
     "Dạ vay 200 triệu trong 36 tháng thì khoảng 6.8 triệu một tháng ạ."),
    (TIN_CHAP, "có ưu đãi gì không",
     "Dạ bên em miễn phí tư vấn thẩm định, và giảm 0.5% lãi suất nếu anh chị nhận lương qua ngân hàng ạ."),
    (TIN_CHAP, "trả trước hạn có mất phí không",
     "Dạ vay tín chấp trả trước hạn được miễn phí ạ."),
    (TIN_CHAP, "bao lâu thì duyệt hồ sơ",
     "Dạ hồ sơ vay tín chấp duyệt trong 24 đến 48 giờ ạ."),

    # --- vay mua nhà ---
    (MUA_NHA, "lãi suất vay mua nhà bao nhiêu",
     "Dạ vay mua nhà ưu đãi từ 6.5% một năm trong 2 năm đầu ạ. Anh chị định vay bao nhiêu ạ?"),
    (MUA_NHA, "cho hỏi lãi suất bên mình",
     "Dạ vay mua nhà lãi suất ưu đãi 6.5% một năm trong 2 năm đầu ạ."),
    (MUA_NHA, "sau ưu đãi thì lãi bao nhiêu",
     "Dạ sau 2 năm đầu thì thả nổi theo thị trường, khoảng 8 đến 10% một năm ạ."),
    (MUA_NHA, "vay mua nhà được tối đa bao nhiêu",
     "Dạ bên em cho vay đến 80% giá trị bất động sản, tối đa 10 tỷ đồng ạ."),
    (MUA_NHA, "vay được bao nhiêu tiền",
     "Dạ vay mua nhà tối đa 80% giá trị căn nhà ạ. Anh chị định mua căn khoảng bao nhiêu ạ?"),
    (MUA_NHA, "vay trong bao lâu",
     "Dạ thời hạn vay mua nhà tối đa 25 năm ạ. Anh chị muốn trả trong bao lâu ạ?"),
    (MUA_NHA, "cần giấy tờ gì",
     "Dạ anh chị chuẩn bị căn cước và sao kê lương 6 tháng ạ. Cùng hợp đồng mua bán nữa ạ."),
    (MUA_NHA, "điều kiện vay thế nào",
     "Dạ anh chị từ 22 đến 65 tuổi, thu nhập từ 10 triệu một tháng và có tài sản đảm bảo ạ."),
    (MUA_NHA, "thu nhập bao nhiêu thì vay được",
     "Dạ vay mua nhà cần thu nhập ổn định từ 10 triệu đồng một tháng trở lên ạ."),
    (MUA_NHA, "vay 1 tỷ thì trả bao nhiêu một tháng",
     "Dạ vay 1 tỷ trong 20 năm thì trả khoảng 9.5 triệu một tháng ạ."),
    (MUA_NHA, "vay 2 tỷ trả góp thế nào",
     "Dạ vay 2 tỷ trong 25 năm thì khoảng 16.5 triệu một tháng ạ."),
    (MUA_NHA, "trả trước hạn có mất phí không",
     "Dạ sau 3 năm thì miễn phí ạ, trước 3 năm thì phí 1 đến 2% số tiền trả trước ạ."),
    (MUA_NHA, "có ưu đãi gì không",
     "Dạ bên em miễn phí thẩm định tài sản và cố định lãi 6.5% trong 2 năm đầu ạ."),
    (MUA_NHA, "bao lâu thì duyệt hồ sơ",
     "Dạ vay mua nhà duyệt trong 3 đến 5 ngày làm việc sau khi đủ hồ sơ ạ."),

    # --- thẻ tín dụng ---
    (THE, "hạn mức thẻ tín dụng bao nhiêu",
     "Dạ hạn mức thẻ từ 10 triệu đến 500 triệu đồng ạ. Anh chị thu nhập khoảng bao nhiêu ạ?"),
    (THE, "phí thường niên bao nhiêu",
     "Dạ năm đầu bên em miễn phí thường niên cho tất cả loại thẻ ạ."),
    (THE, "thẻ gold phí bao nhiêu",
     "Dạ thẻ Gold hạn mức 30 đến 200 triệu, phí thường niên 400 nghìn đồng một năm ạ."),
    (THE, "thẻ platinum thế nào",
     "Dạ thẻ Platinum hạn mức 100 đến 500 triệu, phí thường niên 800 nghìn một năm ạ."),
    (THE, "được miễn lãi bao lâu",
     "Dạ thời gian miễn lãi lên đến 55 ngày ạ."),
    (THE, "có hoàn tiền không",
     "Dạ có ạ, hoàn tiền 1 đến 3% cho mọi giao dịch, riêng ăn uống là 3% ạ."),
    (THE, "điều kiện mở thẻ thế nào",
     "Dạ anh chị từ 18 tuổi và thu nhập từ 5 triệu một tháng là mở được ạ."),
    (THE, "cần giấy tờ gì",
     "Dạ anh chị chuẩn bị căn cước còn hiệu lực và giấy tờ chứng minh thu nhập ạ."),
    (THE, "làm sao tăng hạn mức",
     "Dạ anh chị dùng thẻ đều và thanh toán đúng hạn 6 tháng rồi yêu cầu tăng ạ."),
]

# CÙNG câu hỏi, KHÁC sản phẩm. Đây là loại mẫu dạy mô hình đọc tài liệu.
MAU_DOI_CHIEU = [
    ("lãi suất bao nhiêu", {
        TIN_CHAP: "Dạ vay tín chấp lãi suất từ 7.9% một năm ạ.",
        MUA_NHA: "Dạ vay mua nhà ưu đãi 6.5% một năm trong 2 năm đầu ạ.",
    }),
    ("hạn mức tối đa bao nhiêu", {
        TIN_CHAP: "Dạ vay tín chấp tối đa 500 triệu đồng ạ.",
        MUA_NHA: "Dạ vay mua nhà đến 80% giá trị nhà, tối đa 10 tỷ đồng ạ.",
        THE: "Dạ hạn mức thẻ từ 10 triệu đến 500 triệu đồng ạ.",
    }),
    ("thu nhập tối thiểu bao nhiêu", {
        TIN_CHAP: "Dạ vay tín chấp cần thu nhập từ 5 triệu một tháng ạ.",
        MUA_NHA: "Dạ vay mua nhà cần thu nhập từ 10 triệu một tháng ạ.",
        THE: "Dạ mở thẻ cần thu nhập từ 5 triệu một tháng ạ.",
    }),
    ("thời hạn bao lâu", {
        TIN_CHAP: "Dạ vay tín chấp từ 12 đến 60 tháng ạ.",
        MUA_NHA: "Dạ vay mua nhà tối đa 25 năm ạ.",
    }),
    ("sao kê mấy tháng", {
        TIN_CHAP: "Dạ vay tín chấp cần sao kê lương 3 tháng gần nhất ạ.",
        MUA_NHA: "Dạ vay mua nhà cần sao kê lương 6 tháng ạ.",
    }),
    ("bao nhiêu tuổi thì vay được", {
        TIN_CHAP: "Dạ vay tín chấp nhận từ 22 đến 60 tuổi ạ.",
        MUA_NHA: "Dạ vay mua nhà nhận từ 22 đến 65 tuổi ạ.",
    }),
]

# Tài liệu KHÔNG có thông tin -> nói sẽ kiểm tra, TUYỆT ĐỐI không bịa.
# Gồm cả "tiết kiệm" - kho tài liệu chưa có sản phẩm này.
MAU_KHONG_BIET = [
    (TIET_KIEM, "lãi suất gửi tiết kiệm bao nhiêu",
     "Dạ em xin phép kiểm tra lại mức lãi suất mới nhất rồi báo anh chị ngay ạ."),
    (TIET_KIEM, "gửi tiết kiệm kỳ hạn nào lợi nhất",
     "Dạ em xin phép kiểm tra lại rồi tư vấn anh chị cụ thể ạ."),
    (TIET_KIEM, "tiết kiệm online có lãi cao hơn không",
     "Dạ em xin phép kiểm tra lại thông tin rồi báo anh chị ngay ạ."),
    (TIN_CHAP, "bên mình có cho vay mua xe không",
     "Dạ em xin ghi nhận và có chuyên viên liên hệ tư vấn anh chị ạ."),
    (TIN_CHAP, "phí phạt trả chậm bao nhiêu",
     "Dạ em xin phép kiểm tra lại mức phí rồi báo anh chị chính xác ạ."),
    (MUA_NHA, "có hỗ trợ vay mua đất nền không",
     "Dạ em xin ghi nhận và có chuyên viên liên hệ lại anh chị ạ."),
    (THE, "thẻ có dùng được ở nước ngoài không",
     "Dạ em xin phép kiểm tra lại rồi báo anh chị ngay ạ."),
]

# Mẫu KHÔNG có số - dạy cách nói, cách xử lý từ chối. Vẫn kèm tài liệu để định
# dạng đồng nhất với lúc chạy thật.
MAU_PHONG_CACH = [
    (TIN_CHAP, "tôi đang bận", "Dạ em xin lỗi đã làm phiền ạ. Em xin phép gọi lại lúc khác ạ."),
    (TIN_CHAP, "không quan tâm", "Dạ em cảm ơn anh chị đã nghe máy ạ. Chúc anh chị một ngày tốt lành ạ."),
    (TIN_CHAP, "sao biết số tôi", "Dạ em lấy từ danh sách khách hàng quan tâm sản phẩm ạ. Em xin phép giới thiệu nhanh ạ?"),
    (TIN_CHAP, "lãi cao quá", "Dạ em hiểu ạ. Anh chị nhận lương qua ngân hàng thì được giảm thêm ạ."),
    (TIN_CHAP, "để tôi suy nghĩ thêm", "Dạ vâng ạ. Em xin phép gửi thông tin qua tin nhắn để anh chị tham khảo ạ?"),
    (TIN_CHAP, "gọi lại sau nhé", "Dạ vâng ạ. Anh chị tiện lúc nào để em gọi lại ạ?"),
    (MUA_NHA, "tôi chưa có nhu cầu", "Dạ em cảm ơn anh chị ạ. Khi nào cần anh chị gọi lại cho em nhé ạ."),
    (MUA_NHA, "để tôi bàn với vợ đã", "Dạ vâng ạ. Em xin phép gọi lại vào cuối tuần được không ạ?"),
    (THE, "tôi có thẻ rồi", "Dạ vâng ạ. Thẻ bên em miễn phí thường niên năm đầu, anh chị cân nhắc thêm ạ."),
    (THE, "phiền quá", "Dạ em xin lỗi ạ. Em xin phép không làm phiền anh chị nữa ạ."),
    (TIN_CHAP, "alo", "Dạ em chào anh chị ạ. Em là nhân viên tư vấn ngân hàng ABC ạ."),
    (TIN_CHAP, "ai đấy", "Dạ em là Lan, nhân viên tư vấn ngân hàng ABC ạ."),
    (TIN_CHAP, "vâng", "Dạ anh chị có đang quan tâm khoản vay nào không ạ?"),
    (TIN_CHAP, "ừ nói đi", "Dạ bên em đang có chương trình vay tín chấp ưu đãi ạ. Anh chị cần vay bao nhiêu ạ?"),
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xem", type=int, default=0, help="in thử N mẫu rồi thoát")
    ap.add_argument("--giu-cu", action="store_true",
                    help="giữ thêm các mẫu cũ KHÔNG chứa số (chỉ dạy phong cách)")
    a = ap.parse_args()

    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    llm = LLMService()
    rag = RAGService()
    rag.load()

    async def lam(product: str, hoi: str, dap: str) -> dict:
        # ĐÚNG cách `_truy_van_rag` ghép lúc chạy thật
        ctx = ""
        try:
            ctx = await rag.retrieve(f"{product} {hoi}".strip(), top_k=2)
        except Exception as e:
            print(f"    [!] RAG lỗi cho {hoi!r}: {e}")
        sysp = llm.build_system_prompt(customer_name="Anh/Chị",
                                       product=product, rag_context=ctx)
        return {"messages": [
            {"role": "system", "content": sysp},
            {"role": "user", "content": hoi},
            {"role": "assistant", "content": dap},
        ]}

    _SO = re.compile(r"\d+(?:[.,]\d+)?")

    def dap_co_can_cu(m: dict) -> bool:
        """Mọi con số trong câu đáp phải TRA ĐƯỢC trong tài liệu của chính mẫu đó.

        ĐÂY LÀ PHÉP KIỂM QUAN TRỌNG NHẤT. Nếu để lọt một mẫu mà câu đáp nêu con
        số không có trong ngữ cảnh, ta đang dạy mô hình đúng cái đang phải chữa:
        nói ra số không tra được. Thà ít mẫu mà sạch.

        So khớp nới ở phần nghìn: tài liệu ghi "800.000đ" còn lời nói tự nhiên là
        "800 nghìn" - cùng một số, khác cách viết.
        """
        tl = next(t["content"] for t in m["messages"] if t["role"] == "system")
        dap = next(t["content"] for t in m["messages"] if t["role"] == "assistant")
        co = set()
        for s in _SO.findall(tl):
            co.add(s)
            co.add(s.replace(".", "").replace(",", ""))    # 800.000 -> 800000
            co.add(s.split(".")[0].split(",")[0])          # 800.000 -> 800
        for s in _SO.findall(dap):
            if s in co:
                continue
            try:
                if float(s.replace(",", ".")) <= 3:        # "2 câu", "3 tháng"...
                    continue
            except ValueError:
                pass
            return False
        return True

    ra = []
    bo = []

    def them(m: dict, nhan: str):
        (ra if dap_co_can_cu(m) else bo).append((m, nhan))

    print("  Sinh mẫu trích số ...")
    for sp, hoi, dap in MAU_TRICH_SO:
        them(await lam(sp, hoi, dap), "trích số")

    print("  Sinh mẫu đối chiếu (cùng câu hỏi, khác sản phẩm) ...")
    for hoi, theo_sp in MAU_DOI_CHIEU:
        for sp, dap in theo_sp.items():
            them(await lam(sp, hoi, dap), "đối chiếu")

    print("  Sinh mẫu không biết thì nói không biết ...")
    for sp, hoi, dap in MAU_KHONG_BIET:
        them(await lam(sp, hoi, dap), "không biết")

    print("  Sinh mẫu phong cách ...")
    for sp, hoi, dap in MAU_PHONG_CACH:
        them(await lam(sp, hoi, dap), "phong cách")

    n_moi = len(ra)

    if a.giu_cu and CU.exists():
        cu = [json.loads(l) for l in CU.read_text(encoding="utf-8").splitlines() if l.strip()]
        co_so = re.compile(r"\d|phẩy|phần trăm|triệu|tỷ|nghìn")
        giu = 0
        for m in cu:
            dap = next((t["content"] for t in m["messages"] if t["role"] == "assistant"), "")
            hoi = next((t["content"] for t in m["messages"] if t["role"] == "user"), "")
            # CHỈ giữ mẫu KHÔNG chứa số: mẫu có số là thứ dạy mô hình nhớ thuộc
            # lòng, đúng cái đang phải chữa.
            if not co_so.search(dap):
                # Rải đều sản phẩm thay vì gán hết cho tín chấp: mẫu phong cách
                # không phụ thuộc sản phẩm, mà gán lệch thì bộ dữ liệu nghiêng hẳn
                # về một sản phẩm và mô hình quen tay trả lời theo nó.
                sp = (TIN_CHAP, MUA_NHA, THE)[giu % 3]
                them(await lam(sp, hoi, dap), "phong cách cũ")
                giu += 1
        print(f"  Giữ thêm {giu} mẫu cũ không chứa số")

    if bo:
        print(f"\n  [!] LOẠI {len(bo)} mẫu vì câu đáp nêu số KHÔNG có trong tài liệu:")
        for m, nhan in bo[:6]:
            hoi = next(t["content"] for t in m["messages"] if t["role"] == "user")
            dap = next(t["content"] for t in m["messages"] if t["role"] == "assistant")
            print(f"        [{nhan}] {hoi!r} -> {dap[:64]!r}")
        print("        (giữ lại thì thành dạy mô hình bịa số - đúng thứ đang phải chữa)")

    ra = [m for m, _ in ra]

    if a.xem:
        for m in ra[:a.xem]:
            print("\n" + "=" * 70)
            for t in m["messages"]:
                print(f"[{t['role']}]\n{t['content'][:700]}\n")
        return 0

    random.seed(20260804)
    random.shuffle(ra)
    RA.mkdir(parents=True, exist_ok=True)
    with MOI.open("w", encoding="utf-8") as f:
        for m in ra:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"\n  Đã ghi {len(ra)} mẫu -> {MOI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
