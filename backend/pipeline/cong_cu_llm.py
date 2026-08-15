"""Bộ công cụ (function calling) cho LLM tra dữ liệu thật thay vì đoán.

Vì sao cần, dù đã có RAG và đã tra hồ sơ lúc mở phiên:

  RAG luôn nhét ngữ cảnh vào prompt dù khách có hỏi hay không, và mô hình phải
  TỰ QUYẾT phần nào liên quan. Đo được trong cuộc gọi thật: nó lấy số của sản
  phẩm bên cạnh, hoặc tự pha ra con số không có ở đâu cả.

  Tra hồ sơ lúc mở phiên chỉ chạy MỘT LẦN theo số đang gọi. Khách đọc số khác,
  hỏi sang sản phẩm khác, hay hỏi thứ không nằm trong bản tra đầu tiên - đều
  không có đường lấy thêm.

Gọi hàm đổi hẳn thế cờ: mô hình phải NÓI RA nó cần gì, ta trả đúng thứ đó, và
khi không có dữ liệu thì kết quả là một câu tiếng Việt nói rõ "không có" chứ
không phải khoảng trống để nó lấp bằng số bịa.

ĐO TRƯỚC KHI LÀM (2026-08-06, qwen2.5:3b trên máy thật):
  - gắn tools vào lượt thường: TTFT 107ms -> 108ms, và 0/5 lần gọi hàm thừa
    với "Alo ai đấy", "anh đang bận", "nghe rõ không em"
  - lượt CÓ tra: trọn vòng 419-599ms, nấp được dưới câu đệm đầu lượt
  - `stream=True` dùng chung với `tools` được, không mất streaming
  - khách không đọc số -> 4/4 lần mô hình KHÔNG bịa số, nó hỏi lại
  - tra ra rỗng -> 3/3 lần KHÔNG bịa lãi suất

MỘT LỖI ĐÃ BẮT ĐƯỢC: trả `{"ket_qua": null}` thì mô hình đáp lại đúng chữ
`null`, và khách nghe TTS đọc "null". Nên mọi hàm dưới đây trả VĂN BẢN TIẾNG
VIỆT, không bao giờ trả None/null/JSON rỗng.
"""

import json
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Mô tả cho mô hình đọc. Viết như nói với người mới: mô hình chọn hàm bằng chính
# đoạn `description` này, mô tả mơ hồ là nó gọi nhầm hoặc không gọi.
DINH_NGHIA = [
    {
        "type": "function",
        "function": {
            "name": "tra_ho_so_khach",
            "description": (
                "Tra hồ sơ của CHÍNH khách đang nghe máy: dư nợ, hợp đồng, "
                "sản phẩm đang dùng, ngày đến hạn. Dùng khi khách hỏi về thông "
                "tin RIÊNG của họ, ví dụ 'dư nợ của tôi', 'hợp đồng của anh', "
                "'tôi còn nợ bao nhiêu'. KHÔNG dùng cho câu hỏi chung về sản phẩm."
            ),
            # Cố ý KHÔNG khai tham số nào. Số điện thoại lấy từ PHIÊN GỌI, không
            # để mô hình tự điền: nó không biết số thật, và một tham số nó tự
            # nghĩ ra là một cách khác để bịa. Bỏ tham số đi thì không còn chỗ bịa.
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tra_thong_tin_san_pham",
            "description": (
                "Tra lãi suất, hạn mức, phí, điều kiện, thời hạn của một sản "
                "phẩm ngân hàng. Dùng khi khách hỏi con số của sản phẩm, ví dụ "
                "'lãi suất bao nhiêu', 'vay tối đa được mấy trăm triệu', "
                "'phí thường niên thẻ'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "san_pham": {
                        "type": "string",
                        "description": "Tên sản phẩm, ví dụ: vay tín chấp, vay mua nhà, thẻ tín dụng",
                    },
                    "can_biet": {
                        "type": "string",
                        "description": "Thứ khách muốn biết: lãi suất, hạn mức, phí, điều kiện…",
                    },
                },
                "required": ["san_pham"],
            },
        },
    },
]

# Câu trả về khi không tra được. Phải là câu HOÀN CHỈNH bằng tiếng Việt: mô hình
# hay chép nguyên kết quả công cụ vào câu nói, nên đây cũng là thứ khách nghe.
_KHONG_CO = "Không có dữ liệu cho mục này. Hãy nói với khách là sẽ kiểm tra lại và báo sau, TUYỆT ĐỐI không đoán số."


async def _tra_ho_so_khach(session, **_) -> str:
    so = (getattr(session, "phone", "") or "").strip()
    if not so:
        return ("Cuộc gọi này chưa gắn số điện thoại nên không tra được hồ sơ. "
                + _KHONG_CO)

    # Đã tra sẵn lúc mở phiên thì dùng lại, đừng đọc file lần nữa giữa đường
    # găng của độ trễ.
    san = (getattr(session, "ngu_canh_khach", "") or "").strip()
    if san:
        return san

    from backend.services import data_source_service as ds
    try:
        ket = await ds.tra_cuu_tat_ca(so)
    except Exception as e:
        logger.warning("tra_ho_so_khach lỗi: %s", e)
        return _KHONG_CO
    van = ds.dung_ngu_canh(ket)
    return van or _KHONG_CO


async def _tra_thong_tin_san_pham(session, rag=None, san_pham: str = "",
                                  can_biet: str = "", **_) -> str:
    san_pham = (san_pham or getattr(session, "product", "") or "").strip()
    if rag is None:
        return _KHONG_CO
    truy_van = f"{san_pham} {can_biet}".strip() or san_pham
    try:
        # Neo theo sản phẩm ĐANG TƯ VẤN chứ không theo tham số mô hình đưa: mô
        # hình nghe nhầm "tín chấp" thành "tín dụng" là RAG lạc sang tài liệu
        # khác, và đó đúng là lỗi đã phải chữa bằng `_mat_na_loc`.
        van = await rag.retrieve(truy_van, top_k=3,
                                 san_pham=getattr(session, "product", "") or san_pham)
    except Exception as e:
        logger.warning("tra_thong_tin_san_pham lỗi: %s", e)
        return _KHONG_CO
    return (van or "").strip() or _KHONG_CO


_BANG = {
    "tra_ho_so_khach": _tra_ho_so_khach,
    "tra_thong_tin_san_pham": _tra_thong_tin_san_pham,
}


# Prompt cho LƯỢT QUYẾT ĐỊNH. Cố ý CỰC NGẮN - đây không phải chỗ tiết kiệm chữ
# cho vui, nó là điều kiện để việc gọi hàm chạy được.
#
# Bổ đôi prompt thật (2064 ký tự) trên qwen2.5:3b, cùng câu "dư nợ của tôi còn
# bao nhiêu", 3 lần mỗi biến thể:
#
#   prompt trống / chỉ câu mở đầu / kèm VÍ DỤ ....... gọi hàm 3/3
#   + CORE_RULES ................................... gọi hàm 0/3
#   + CORE_REMINDER (chỉ 218 ký tự!) ............... gọi hàm 0/3
#
# Cả hai khối đều RA LỆNH TRẢ LỜI, và `CORE_REMINDER` ("NHẮC LẠI TRƯỚC KHI TRẢ
# LỜI: tối đa 2 câu…") nằm ở CUỐI prompt, ngay sát lúc sinh chữ. Gọi hàm không
# phải là "trả lời", nên mô hình nghe lệnh gần nhất và bỏ qua công cụ. Thêm một
# khối "hãy gọi hàm" vào prompt đầy đủ KHÔNG cứu được (đã thử, vẫn 0/5), kể cả
# khi đặt lên đầu.
#
# Nên tách hẳn: lượt này CHỈ quyết định có cần tra không, prompt sạch không có
# lệnh trả lời nào. Lượt sinh chữ vẫn dùng prompt đầy đủ như cũ, và dữ liệu tra
# được đi vào qua THÔNG TIN THAM KHẢO - đúng đường quy tắc 3 đã dạy nó tin.
PROMPT_QUYET_DINH = (
    "Bạn là bộ định tuyến của tổng đài ngân hàng. Đọc câu khách vừa nói và quyết "
    "định có cần tra dữ liệu không.\n"
    "- Hỏi về hồ sơ RIÊNG của khách (dư nợ, hợp đồng, kỳ hạn còn lại, ngày đến "
    "hạn, khoản vay của tôi) -> gọi tra_ho_so_khach.\n"
    "- Hỏi con số của sản phẩm (lãi suất, hạn mức, phí, điều kiện) -> gọi "
    "tra_thong_tin_san_pham.\n"
    "- Chào hỏi, từ chối, hỏi thăm, nói chuyện phiếm -> KHÔNG gọi hàm nào.\n"
    "Chỉ gọi hàm hoặc không. Đừng viết câu trả lời cho khách."
)


# --- Lưới từ khoá: đường nhanh, không tốn lượt LLM nào ------------------------
#
# Đo 2026-08-06 trên 9 câu (4 hồ sơ, 3 sản phẩm, 2 không cần tra):
#
#   lưới từ khoá ......... ĐÚNG 9/9,  0ms
#   qwen2.5:3b (LLM) ..... ĐÚNG 6/7,  419ms trên đường găng
#   qwen3:1.7b ........... ĐÚNG 2/9,  281ms
#   qwen3:0.6b ........... ĐÚNG 2/9,  229ms
#
# Hạ xuống model nhỏ hơn KHÔNG cứu được: 0.6B và 1.7B đều gọi hàm bừa. Còn lưới
# từ khoá thì vừa đúng hơn vừa miễn phí - cùng bài học với `luot_thuong_gap`:
# việc gì có quy tắc xác định thì viết code, đừng giao cho mô hình đoán.
#
# LLM vẫn giữ làm ĐƯỜNG LÙI cho cách nói lạ và cho bản phiên âm méo của kênh
# 8kHz - chỗ mà so khớp chữ dễ trượt. Lưới chỉ được phép làm NHANH HƠN, không
# được phép làm hẹp đi.

def _bo_dau(s: str) -> str:
    # "đ" (U+0111) không tách được bằng NFD - phải thay tay, nếu không thì
    # "đến hạn" -> "?en h?n" và mọi mẫu có chữ đ đều trượt.
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Hồ sơ RIÊNG của khách. Cố ý KHÔNG đòi có "của tôi/của anh": qua điện thoại
# khách nói cụt ("dư nợ bao nhiêu em"), mà trong ngữ cảnh cuộc gọi thì hỏi dư nợ
# gần như luôn là hỏi về chính họ.
_RE_HO_SO = re.compile(
    r"(du no|con no|no bao nhieu|khoan vay|hop dong|den han|"
    r"ky han|tra xong|con may thang|so du)"
)
# Số liệu SẢN PHẨM.
_RE_SAN_PHAM = re.compile(
    r"(lai suat|han muc|bieu phi|phi thuong nien|phi tra no|dieu kien vay|"
    r"vay toi da|vay duoc bao nhieu|thoi han vay|ho so can|giay to)"
)


def loc_nhanh(cau: str) -> str | None:
    """Đoán công cụ cần dùng bằng so khớp chữ. None = không chắc, để LLM quyết.

    Hồ sơ xét TRƯỚC sản phẩm: "khoản vay của anh còn bao nhiêu" chứa cả "khoan
    vay" lẫn ý hỏi số, mà thứ khách muốn là hồ sơ của họ chứ không phải bảng giá.
    """
    t = _bo_dau(cau or "")
    if _RE_HO_SO.search(t):
        return "tra_ho_so_khach"
    if _RE_SAN_PHAM.search(t):
        return "tra_thong_tin_san_pham"
    return None



async def chay(ten: str, tham_so: dict, session, rag=None) -> str:
    """Chạy một công cụ. LUÔN trả về văn bản tiếng Việt, không bao giờ None."""
    ham = _BANG.get(ten)
    if ham is None:
        # Mô hình bịa ra tên hàm không tồn tại - hiếm nhưng có. Nói thẳng cho nó
        # biết thay vì im lặng, để nó trả lời bằng đường thường.
        logger.warning("LLM gọi hàm lạ: %r", ten)
        return f"Không có công cụ tên '{ten}'. " + _KHONG_CO
    if not isinstance(tham_so, dict):
        try:
            tham_so = json.loads(tham_so or "{}")
        except Exception:
            tham_so = {}
    try:
        ket = await ham(session, rag=rag, **tham_so)
    except TypeError:
        # Mô hình đưa tham số thừa/sai tên - bỏ hết, chạy bằng mặc định của phiên.
        ket = await ham(session, rag=rag)
    except Exception as e:
        logger.warning("Công cụ %s lỗi: %s", ten, e)
        return _KHONG_CO
    return (ket or "").strip() or _KHONG_CO


async def ham_luot_quyet_dinh(llm) -> None:
    """Chạy MỘT lượt quyết định công cụ bỏ đi, để lượt thật không phải trả giá.

    Vì sao cần riêng, trong khi đã có hâm nóng LLM thường: hai lệnh khác HÌNH
    DẠNG. Lệnh thường không kèm `tools`, lệnh này có `tools=DINH_NGHIA` và
    prompt riêng - hâm cái nọ không làm ấm cái kia.

    Đo trên máy thật 08-08, sau khi đã chữa xong chuyện model bị đẩy khỏi VRAM:
    lượt quyết định ĐẦU TIÊN của mỗi cuộc vẫn tốn ~2700ms, các lượt sau 115-600ms.
    Khoản đó rơi trọn vào lượt khách hỏi đầu tiên - đúng lúc ấn tượng đầu.

    Nuốt mọi lỗi: hâm không được thì cuộc gọi vẫn diễn ra bình thường, chỉ chậm
    lượt đầu như trước.
    """
    xin: list[dict] = []
    try:
        async for _ in llm.stream_response(
                [{"role": "user", "content": "a lô"}],
                PROMPT_QUYET_DINH,
                tools=DINH_NGHIA,
                on_tool_calls=xin.extend):
            pass
    except Exception as e:
        logger.debug("Hâm lượt quyết định công cụ bỏ qua: %s", e)
