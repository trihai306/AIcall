"""Chuyển tiếp cuộc gọi sang người thật (Điều 6: "Có thể chuyển tiếp đến số điện
thoại đã cài đặt sẵn nếu yêu cầu vượt giới hạn đã training").

BỐN ĐIỀU KIỆN, khai trong kịch bản (`scenarios.transfer_on`):

  khach_yeu_cau    khách nói thẳng "cho tôi gặp người thật"
  ngoai_pham_vi    bot phải trả lời câu "ngoài phạm vi" 2 lượt LIÊN TIẾP
  khong_tim_thay   RAG không có mảnh nào liên quan 2 lượt LIÊN TIẾP
  het_luot         vượt `scenarios.max_turns`

LIÊN TIẾP chứ không phải cộng dồn: khách hỏi một câu lạc đề rồi quay lại chủ đề
là chuyện bình thường trong mọi cuộc gọi. Cộng dồn thì cuộc nào đủ dài cũng bị
chuyển tiếp, và chuyên viên thật sẽ ngập trong các cuộc lẽ ra bot xử lý được.

LUÔN BÁO TRƯỚC KHI NỐI MÁY. Im lặng rồi đổi người là cách chắc chắn nhất để
khách tưởng rớt cuộc gọi và cúp máy.
"""

import asyncio
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Câu bot nói khi gặp câu hỏi ngoài phạm vi — phải khớp quy tắc 4 trong
# CORE_RULES của services/llm_service.py. Đổi một bên mà quên bên kia thì bộ đếm
# này không bao giờ tăng và điều kiện "ngoai_pham_vi" chết âm thầm.
CAU_NGOAI_PHAM_VI = "ghi nhận và có chuyên viên liên hệ lại"

# Khách đòi gặp người thật.
Y_DOI_GAP_NGUOI = (
    "gap nguoi that", "gap nguoi", "noi chuyen voi nguoi",
    "gap nhan vien", "gap chuyen vien", "gap tu van vien",
    "cho toi gap", "chuyen may cho", "noi voi nguoi that",
    "khong muon noi voi may", "day la may hay nguoi", "co phai nguoi khong",
    "gap quan ly", "gap sep",
)

_LY_DO_MO_TA = {
    "khach_yeu_cau": "Khách yêu cầu gặp người thật",
    "ngoai_pham_vi": "Bot không trả lời được 2 lượt liên tiếp",
    "khong_tim_thay": "Không tìm thấy tài liệu liên quan 2 lượt liên tiếp",
    "het_luot": "Vượt số lượt tối đa của kịch bản",
}

_NGUONG_LIEN_TIEP = 2


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", s).strip()


def khach_doi_gap_nguoi(text: str) -> bool:
    sach = _bo_dau(text)
    return any(y in sach for y in Y_DOI_GAP_NGUOI)


def cap_nhat_dem(session, cau_khach: str, cau_bot: str, rag_rong: bool):
    """Cập nhật các bộ đếm sau mỗi lượt. Gọi từ pipeline.

    Đặt ở một chỗ để logic "liên tiếp" không bị rải khắp nơi rồi lệch nhau.
    """
    if khach_doi_gap_nguoi(cau_khach):
        session.khach_doi_gap_nguoi = True

    # Bỏ dấu CẢ HAI VẾ. So chuỗi có dấu với chuỗi đã bỏ dấu thì không bao giờ
    # khớp, và điều kiện "ngoai_pham_vi" chết âm thầm — đã mắc đúng lỗi này.
    if _bo_dau(CAU_NGOAI_PHAM_VI) in _bo_dau(cau_bot):
        session.so_lan_ngoai_pham_vi += 1
    else:
        session.so_lan_ngoai_pham_vi = 0

    if rag_rong:
        session.so_lan_rag_trong += 1
    else:
        session.so_lan_rag_trong = 0


def can_chuyen_tiep(session) -> str:
    """Lý do phải chuyển tiếp ngay bây giờ, hoặc chuỗi rỗng.

    Chỉ xét các điều kiện kịch bản này BẬT — kịch bản không khai số chuyên viên
    thì không bao giờ chuyển tiếp.
    """
    scenario = getattr(session, "scenario", None) or {}
    if not (scenario.get("transfer_number") or "").strip():
        return ""
    if getattr(session, "transferred_to", ""):
        return ""      # đã chuyển rồi

    bat = set(scenario.get("transfer_on") or [])
    if not bat:
        return ""

    if "khach_yeu_cau" in bat and getattr(session, "khach_doi_gap_nguoi", False):
        return "khach_yeu_cau"
    if "ngoai_pham_vi" in bat and session.so_lan_ngoai_pham_vi >= _NGUONG_LIEN_TIEP:
        return "ngoai_pham_vi"
    if "khong_tim_thay" in bat and session.so_lan_rag_trong >= _NGUONG_LIEN_TIEP:
        return "khong_tim_thay"
    if "het_luot" in bat:
        max_turns = int(scenario.get("max_turns") or 20)
        if session.turn_count > max_turns:
            return "het_luot"
    return ""


async def chuyen_tiep(session, device: dict, bridge=None, ly_do: str = "") -> tuple[bool, str]:
    """Nói câu xin phép rồi nối máy sang chuyên viên.

    Thất bại thì QUAY LẠI cuộc gọi và xin lỗi khách — không được để khách ở đầu
    dây im lặng chờ một người không bao giờ tới.
    """
    from backend.services import adb_service

    scenario = getattr(session, "scenario", None) or {}
    so = (scenario.get("transfer_number") or "").strip()
    if not so:
        return False, "Kịch bản chưa khai số chuyên viên"

    cau = (scenario.get("transfer_message") or "").strip() \
        or "Dạ em xin phép nối máy cho chuyên viên ạ"

    # 1. Báo cho khách TRƯỚC. Chờ nói xong mới thao tác: nối máy giữa câu thì
    #    khách chỉ nghe được nửa câu rồi đường dây đổi người.
    if bridge is not None:
        try:
            await _noi_cau(session, bridge, cau)
        except Exception as e:
            logger.warning(f"[chuyển tiếp] không nói được câu xin phép: {e}")

    if device.get("kind") != "adb" or not device.get("address"):
        return False, "Chỉ máy trong phone farm (ADB) mới chuyển tiếp tự động được"

    serial = device["address"]
    ok, chi_tiet = await adb_service.chuyen_cuoc_goi(serial, so)
    if ok:
        session.transferred_to = so
        session.transfer_reason = ly_do
        logger.info(f"[chuyển tiếp] {session.phone} -> {so} ({_LY_DO_MO_TA.get(ly_do, ly_do)})")
        return True, chi_tiet

    # 2. Nối máy hỏng: quay lại xin lỗi khách.
    logger.warning(f"[chuyển tiếp] thất bại: {chi_tiet}")
    if bridge is not None:
        try:
            await _noi_cau(
                session, bridge,
                "Dạ em xin lỗi, chuyên viên đang bận ạ. "
                "Em ghi nhận và sẽ có người gọi lại cho anh/chị ngay ạ.",
            )
        except Exception:
            pass
    session.transfer_reason = f"that_bai:{ly_do}"
    return False, chi_tiet


async def _noi_cau(session, bridge, cau: str):
    """Sinh tiếng cho một câu rồi chờ nó phát xong.

    Chờ hết hàng đợi phát chứ không chỉ chờ TTS: TTS sinh nhanh hơn thời gian
    thực nhiều lần, nên "sinh xong" không có nghĩa là "khách đã nghe xong".
    """
    from backend.main import app_state

    wav = await app_state.tts.synthesize(cau, voice=session.voice_name)
    if not wav:
        return
    await bridge.play(wav)

    # Đợi hàng đợi phát cạn, tối đa 15 giây để không treo mãi nếu ổ cắm chết.
    for _ in range(150):
        if bridge._out.empty():
            break
        await asyncio.sleep(0.1)
    # Cộng thêm đệm mồi đang nằm ở máy: hàng đợi cạn nhưng điện thoại vẫn còn
    # ngần đó giây tiếng chưa phát ra loa.
    await asyncio.sleep(bridge.dem_mo_s + 0.3)
