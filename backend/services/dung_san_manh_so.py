"""Dựng SẴN tiếng cho các câu của luật khoản vay có con số hay gặp.

Câu của luật mang số tiền / kỳ hạn của khách nên không soạn sẵn trong kho câu
trả lời được - "có nhiều con số khoảng thời gian lắm" (người dùng, 09-10-2026).
Nhưng luật đã viết mỗi câu ngắn chỉ mang MỘT con số (xem `_dap_ky_han`), nên số
câu ngắn khác nhau là HỮU HẠN và nhỏ: vài chục kỳ hạn, vài chục mức tiền. Dựng
tiếng cho chúng một lần vào kho mảnh (`tieng_san.KhoTiengSan`) là mọi tổ hợp
ghép ra tiếng ngay.

Danh sách câu KHÔNG chép tay ở đây: chạy chính luật `tra_loi_khoan_vay.tra_loi`
trên một lưới lời khách giả, lấy câu nó trả ra. Đổi chữ trong luật thì lần chạy
sau tự dựng theo chữ mới, không có hai nơi phải sửa cho khớp.

Con số ngoài lưới (313 triệu, 7 tháng rưỡi...) vẫn chạy: câu mở đầu của lượt có
sẵn nên phát ngay, câu mang con số lạ được dựng trong lúc khách nghe câu đầu
rồi tự vào kho cho lần sau.
"""
from __future__ import annotations

import asyncio
import logging
import time

from backend.config import settings

logger = logging.getLogger(__name__)

# Lời khách đã nói + câu AI đề nghị, để lấy các câu chỉ xuất hiện ở lượt SAU
# (khách gật, khách nhắc lại kỳ hạn vừa bị từ chối).
_CAU_DEM_MAU = "Dạ,"


def _muc_tien(tran: float) -> list[str]:
    """Các mức tiền khách hay nói, tới trần sản phẩm (và vài mức vượt trần)."""
    trieu = [10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 120, 150, 180,
             200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900]
    ty = [1, 1.2, 1.5, 1.8, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 12, 15]
    if tran <= 1_000_000_000:
        trieu = sorted(set(trieu) | set(range(10, int(tran / 1e6) + 1, 10)))
    ra = [f"{x} triệu" for x in trieu if x * 1e6 <= tran * 1.4]
    ra += [f"{str(x).replace('.', ',')} tỷ" for x in ty if x * 1e9 <= tran * 1.4]
    return ra


def _ky_han(khung: tuple[int | None, int]) -> list[str]:
    ngan, dai = khung
    thang = list(range(1, min(dai, 72) + 13)) if dai <= 72 else [3, 6, 9, 12, 18, 24, 36, 48, 60]
    nam = list(range(1, dai // 12 + 6))
    return [f"{t} tháng" for t in thang] + [f"{n} năm" for n in nam]


def cac_cau_cua_san_pham(tai_lieu: str) -> list[str]:
    """Mọi câu luật khoản vay sẽ nói cho lưới con số hay gặp của MỘT tài liệu sản phẩm."""
    from backend.pipeline import tra_loi_khoan_vay as luat
    from backend.pipeline.noi_cau_dem import loi_sau_dem

    sp_doc = luat._phan_san_pham(tai_lieu)
    tran = luat._tran_san_pham(sp_doc)
    ky = luat._thoi_han(sp_doc)
    toi_da = None if ky else luat._thoi_han_toi_da(sp_doc)
    khung = ky or ((None, toi_da) if toi_da else None)
    if not tran or not khung:
        return []
    cau: dict[str, None] = {}

    def hoi(loi: str, lich_su: list[dict] | None = None) -> str:
        try:
            got = luat.tra_loi(loi, tai_lieu, history=list(lich_su or []))
        except Exception as e:  # noqa: BLE001
            logger.debug("dựng sẵn: luật trượt với %r: %s", loi, e)
            return ""
        if not got:
            return ""
        cau.setdefault(got[1])
        # Bản nói SAU câu đệm (bỏ lời mở đầu trùng) là một câu mở đầu khác.
        sau_dem = loi_sau_dem(_CAU_DEM_MAU, got[1])
        if sau_dem != got[1]:
            cau.setdefault(sau_dem)
        return got[1]

    tien, han = _muc_tien(tran), _ky_han(khung)
    trong = next((h for h in han if hoi(f"anh vay {h} được không").find("thì được") > 0), han[0])
    ngoai = [h for h in han if "chưa được" in hoi(f"anh vay {h} được không")]
    # Khoảng kỳ hạn nói gần đúng: "4-5 tháng", "vài tháng".
    for a in range(1, 12):
        hoi(f"anh vay {a}-{a + 1} tháng được không")
    hoi("anh vay vài tháng được không")
    hoi("anh vay 12 đến 24 tháng được không")
    for x in tien:
        hoi(f"anh muốn vay {x}")
        hoi(f"anh muốn vay {x} trong {trong} được không")
        if ngoai:
            hoi(f"anh muốn vay {x} trong {ngoai[0]} được không")
    # Khách gật với thời hạn AI đề nghị, hoặc nhắc lại kỳ hạn vừa bị từ chối.
    for h in ([ngoai[0], ngoai[-1]] if ngoai else []):
        de_nghi = hoi(f"anh vay {h} được không")
        ls = [{"role": "user", "content": f"anh vay {h} được không"},
              {"role": "assistant", "content": de_nghi}]
        hoi("ừ được", ls)
        hoi(f"anh vay {h} thôi", ls)
    hoi("thế ngắn nhất là bao lâu")
    hoi("thế dài nhất thì bao lâu")
    # Tính trả góp: chỉ cần câu DẪN và câu chốt (cố định theo sản phẩm). Câu mang
    # số tiền x kỳ hạn x kết quả không dựng sẵn: nó luôn đứng SAU câu dẫn dài ~4
    # giây nên dựng tại chỗ vẫn kịp, và dựng cả lưới là thêm ~850 câu.
    hoi(f"vay {tien[len(tien) // 3]} trong {trong} thì mỗi tháng trả bao nhiêu")
    for k in list(range(5, 31)) + [35, 40, 45, 50, 60, 70, 80, 100]:
        hoi(f"lương anh {k} triệu một tháng")
    return list(cau)


def cac_manh_can_dung() -> list[str]:
    """Mọi mảnh (câu ngắn) cần có tiếng: câu của luật cho từng sản phẩm + câu hỏi dẫn dắt."""
    from backend.pipeline.dan_dat import THEO_SAN_PHAM
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.services.tieng_san import cat_manh

    manh: dict[str, None] = {}
    for ma, buoc in THEO_SAN_PHAM.items():
        for _, cau_hoi in buoc:
            manh.setdefault(cau_hoi)
        tai_lieu = toan_van(ma)
        if not tai_lieu:
            continue
        for cau in cac_cau_cua_san_pham(tai_lieu):
            for m in cat_manh(cau):
                manh.setdefault(m)
    return list(manh)


async def dung_san(state, nghi_s: float = 0.05) -> dict:
    """Dựng các mảnh còn thiếu, từng mảnh một, nhường khi backend đang bận nói.

    F5 không chạy song song được: một mảnh đang dựng ở đây thì lượt nói thật phải
    chờ nó xong (dưới ~1 giây). Nên đang có cuộc gọi thì nghỉ hẳn.
    """
    from backend.core.service_priority import background_ai_busy_reason, background_gpu_lock
    from backend.services.tieng_san import kho_tieng_san

    tts = getattr(state, "tts", None)
    kq = {"can": 0, "da_co": 0, "dung": 0, "hong": 0, "ms": 0}
    if tts is None or not getattr(tts, "_is_loaded", False):
        return kq
    giong = tts._giong_thuc(None)
    manh = await asyncio.to_thread(cac_manh_can_dung)
    kq["can"] = len(manh)
    t0 = time.perf_counter()
    for m in manh:
        if kho_tieng_san.lay_manh(tts, m, giong) is not None:
            kq["da_co"] += 1
            continue
        while True:
            try:
                from backend.services.phone_call_service import phone_calls
                co_cuoc_goi = bool(phone_calls.status())
            except Exception:  # noqa: BLE001
                co_cuoc_goi = False
            if co_cuoc_goi or background_ai_busy_reason():
                await asyncio.sleep(5.0)
                continue

            # Kiểm tra lại SAU khi giữ cổng GPU: lượt khách có thể được đặt chỗ
            # đúng giữa lần kiểm tra trên và lúc tác vụ nền lấy được khoá.
            # Native F5 không ngắt an toàn giữa một lần sinh, nên giữ khoá tới
            # khi đúng một mảnh hoàn tất rồi mới nhường.
            async with background_gpu_lock():
                try:
                    co_cuoc_goi = bool(phone_calls.status())
                except Exception:  # noqa: BLE001
                    co_cuoc_goi = False
                if co_cuoc_goi or background_ai_busy_reason():
                    continue
                wav = await kho_tieng_san.dung_manh(tts, m, giong)
            break
        kq["dung" if wav else "hong"] += 1
        if kq["dung"] % 100 == 0 and kq["dung"]:
            logger.info("Dựng sẵn mảnh số: %d/%d (đã có %d)", kq["dung"] + kq["da_co"],
                        kq["can"], kq["da_co"])
        await asyncio.sleep(nghi_s)
    kq["ms"] = round((time.perf_counter() - t0) * 1000)
    logger.info("Dựng sẵn mảnh số cho giọng %s: cần %d, đã có %d, dựng mới %d, hỏng %d, %.0fs",
                giong, kq["can"], kq["da_co"], kq["dung"], kq["hong"], kq["ms"] / 1000)
    return kq


async def chay_nen(state) -> None:
    """Gọi lúc khởi động: đợi backend lên hẳn rồi mới dựng."""
    if not (settings.tieng_san_bat and settings.tieng_san_theo_manh
            and settings.tieng_san_dung_san_so):
        return
    await asyncio.sleep(20.0)
    try:
        await dung_san(state)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Dựng sẵn mảnh số hỏng (cuộc gọi vẫn chạy, chỉ là lần đầu phải sinh tại chỗ)")
