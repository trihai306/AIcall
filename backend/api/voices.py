import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voices", tags=["voices"])

VOICES_DIR = Path("models/tts/ref_voices")


@router.get("")
async def list_voices():
    """Danh sách giọng, kèm giọng nào là MẶC ĐỊNH.

    Phải khai `mac_dinh` ra ngoài, không thì giao diện chọn đại phần tử đầu danh
    sách. Đó là lỗi thật đã đo được (07-08): `.env` để giọng mặc định là
    `giong_heu` nhưng ô chọn giọng lại đứng ở `fosd_1` (đầu bảng chữ cái), mà câu
    đệm chỉ được dựng sẵn cho giọng mặc định. Hậu quả: mở app bấm Gọi là khách
    nghe IM LẶNG trọn 1.0-1.8 giây mỗi lượt, log ghi
    `KHÔNG có filler cho giọng 'fosd_1' -> khách chờ im lặng đủ 1741ms`.
    """
    from backend.main import app_state

    mac_dinh = app_state.tts.default_voice_name()
    ds = app_state.tts.list_voices()
    for v in ds:
        v["mac_dinh"] = (v.get("name") == mac_dinh)
    return {"voices": ds, "mac_dinh": mac_dinh}


@router.post("/upload")
async def upload_voice(
    file: UploadFile = File(...),
    name: str = Form(...),
    ref_text: str = Form(""),
):
    """Upload a new reference voice WAV file."""
    VOICES_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return {"error": "Tên không hợp lệ"}

    wav_path = VOICES_DIR / f"{safe_name}.wav"
    txt_path = VOICES_DIR / f"{safe_name}.txt"

    with open(wav_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # F5-TTS nhân bản chính file này, nên file câm => mọi câu đọc ra đều im lặng
    # mà không có lỗi nào. Chặn ngay lúc upload thay vì để phát hiện khi gọi khách.
    from backend.main import app_state

    probe = app_state.tts.probe_ref(wav_path)
    if not probe["readable"]:
        wav_path.unlink(missing_ok=True)
        return {"error": "Không đọc được file audio (định dạng không hỗ trợ hoặc file hỏng)"}
    if probe["silent"]:
        wav_path.unlink(missing_ok=True)
        return {"error": (
            f"File dài {probe['duration']}s nhưng hoàn toàn không có tiếng. "
            "Kiểm tra lại micro khi thu rồi upload lại."
        )}

    if ref_text.strip():
        txt_path.write_text(ref_text.strip(), encoding="utf-8")

    # Re-uploading over an existing name must invalidate the cached reference
    # and every clip synthesized from it.
    from backend.main import app_state
    app_state.tts.drop_voice(safe_name)

    logger.info(f"Voice uploaded: {safe_name} ({len(content)} bytes)")
    return {"name": safe_name, "path": str(wav_path), "size_kb": round(len(content) / 1024, 1)}


def _cat_manh_nhu_pipeline(text: str) -> list[str]:
    """Cắt chữ y hệt vòng stream của `streaming_pipeline`.

    Uỷ quyền cho `text_chunker.chia_ca_luot` - NGUỒN DUY NHẤT của luật cắt
    cả lượt. Trước 16-08-2026 chỗ này giữ một bản CHÉP RIÊNG, tức hai bộ luật
    song song cho cùng một việc; đúng kiểu hỏng đã xảy ra thật ở dự án này
    (trang nghe thử cắt khác cuộc gọi, không gì báo lỗi). Giữ lại tên hàm vì
    nó nói rõ ý ĐỊNH tại chỗ gọi: "cắt y như pipeline".
    """
    from backend.pipeline.text_chunker import chia_ca_luot

    return chia_ca_luot(text)


async def _ghep_nhu_pipeline(tts, manh: list[str], voice_name: str,
                             toc: float, fast: bool) -> bytes:
    """Sinh từng mảnh rồi ghép, chèn lặng đúng lượng `nhip_nghi_sau` cho.

    Chèn vào ĐẦU mảnh sau chứ không nối vào cuối mảnh trước - giống hệt
    `streaming_pipeline`, nhờ vậy mảnh đầu không bị thêm gì và mảnh cuối không
    có đuôi lặng thừa.

    `fast` chỉ áp cho mảnh ĐẦU, vì `f5tts_nfe_step_first` trong đường thật cũng
    chỉ dùng cho mảnh đầu. Áp cho mọi mảnh là nghe ra một thứ không tồn tại.
    """
    import numpy as np

    from backend.pipeline.text_chunker import nhip_nghi_sau
    from backend.services.audio_utils import pcm_to_wav

    SR = 24000
    khuc: list[np.ndarray] = []
    nghi_ms = 0.0
    for i, m in enumerate(manh):
        b = await tts.synthesize(m, voice=voice_name, use_cache=False,
                                 speed=toc, fast=(fast and i == 0))
        pcm = np.frombuffer(b[44:], dtype=np.int16)
        if nghi_ms > 0:
            khuc.append(np.zeros(int(SR * nghi_ms / 1000), dtype=np.int16))
        khuc.append(pcm)
        nghi_ms = nhip_nghi_sau(m)
    return pcm_to_wav(np.concatenate(khuc).tobytes(), sample_rate=SR)


@router.post("/test-tts")
async def test_tts(
    text: str = Form(...),
    voice_name: str = Form("default"),
    fast: bool = Form(False),
    qua_dien_thoai: bool = Form(False),
):
    """Synthesize text with a specific voice and return audio + timing.

    fast=True uses the reduced diffusion steps the pipeline applies to the
    first chunk of a reply, so the quality/TTFA trade-off can be heard.
    """
    from backend.main import app_state

    if not app_state.tts._is_loaded:
        return {"error": "TTS chưa được tải. Cần cài F5-TTS trước."}

    import base64
    import time

    import numpy as np

    # Giọng mẫu câm thì kết quả cũng câm - báo trước thay vì trả về file im lặng.
    ref = next((v for v in app_state.tts.list_voices() if v["name"] == voice_name), None)
    if ref and ref.get("silent"):
        return {"error": (
            f"Giọng mẫu '{voice_name}' là file không có tiếng ({ref['duration']}s im lặng). "
            "F5-TTS nhân bản chính file này nên đọc ra cũng sẽ im lặng — "
            "thu lại 5-10 giây rồi upload đè lên giọng này."
        )}

    # Voice is passed per call - testing a voice here must not change the voice
    # any live phone line is currently speaking with.
    # Hệ số tốc của đường thoại: nghe thử phải giống hệt lúc gọi thật, không
    # thì chỉnh trên web xong ra cuộc gọi lại khác.
    #
    # Hệ số này NHÂN VÔ ĐIỀU KIỆN, không còn buộc vào `qua_dien_thoai`. Buộc vào
    # nhau là lỗi: một cờ điều khiển hai thứ độc lập (nhịp đọc và băng thông),
    # nên nghe ở 24kHz thì được nhịp 283 âm tiết/phút trong khi cuộc gọi đọc 347
    # - chậm hơn 28% so với thứ khách thật sự nghe. `qua_dien_thoai` giờ chỉ còn
    # một nghĩa duy nhất: hạ băng thông xuống 8kHz.
    toc = app_state.tts.toc_nghe_thu(voice_name)

    # ĐI ĐÚNG ĐƯỜNG CUỘC GỌI THẬT: cắt mảnh rồi ghép có chèn nhịp nghỉ.
    #
    # Trước 2026-08-12 chỗ này gọi thẳng `synthesize` cho CẢ đoạn, nên toàn bộ
    # phần chèn nhịp nghỉ của `streaming_pipeline` không áp dụng - trang nghe thử
    # cho ra tiếng TỆ HƠN thứ khách thật sự nghe. Đo trên đoạn 3 câu:
    #
    #     gọi thẳng cả đoạn : 2 quãng lặng, dài 20ms và 40ms   (tai không nghe ra)
    #     đúng đường thật   : 3 quãng lặng, 20ms + 210ms + 200ms
    #
    # Hậu quả thật: người dùng nghe trang này rồi báo "giọng bị nhảy chữ", trong
    # khi cuộc gọi thật không bị. Một trang thử không phản ánh đúng đầu ra thì
    # tệ hơn không có, vì nó dẫn tới quyết định sai.
    manh = _cat_manh_nhu_pipeline(text)
    t0 = time.perf_counter()
    try:
        # use_cache=False: đo thời gian tổng hợp thật. Nếu để cache, lần thứ hai
        # cùng câu + cùng giọng sẽ báo 0ms và bảng so sánh A/B thành vô nghĩa.
        wav_bytes = await _ghep_nhu_pipeline(
            app_state.tts, manh, voice_name, toc, fast
        )
    except Exception as e:
        logger.warning(f"test-tts failed for voice '{voice_name}': {e}")
        return {"error": f"Tổng hợp thất bại: {e}"}
    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    if qua_dien_thoai:
        wav_bytes = _mo_phong_kenh_thoai(wav_bytes)

    # 44-byte WAV header, 16-bit mono at 24kHz
    duration_ms = round(max(0, len(wav_bytes) - 44) / 2 / 24000 * 1000)

    # Lưới an toàn cuối: model vẫn có thể ra toàn số 0 (ref hỏng, NaN trên MPS).
    # Trả file im lặng về cho người dùng nghe là kiểu lỗi khó đoán nhất.
    samples = np.frombuffer(wav_bytes[44:], dtype=np.int16)
    peak = int(np.abs(samples).max()) if samples.size else 0
    if peak == 0:
        logger.warning(f"test-tts produced silence for voice '{voice_name}'")
        return {"error": (
            f"Tổng hợp xong {duration_ms}ms nhưng file không có tiếng. "
            f"Kiểm tra lại giọng mẫu '{voice_name}' (file wav phải nghe được) "
            "và checkpoint F5-TTS."
        )}

    return {
        "audio": base64.b64encode(wav_bytes).decode(),
        "text": text,
        "voice": voice_name,
        "fast": fast,
        "elapsed_ms": elapsed_ms,
        "duration_ms": duration_ms,
        "rtf": round(elapsed_ms / duration_ms, 3) if duration_ms else None,
        # Để nhìn ra chữ đã bị cắt thế nào. Chữ dán từ nơi khác hay thiếu khoảng
        # trắng sau dấu chấm ("nghìn ạ.Dạ lãi suất") làm cả đoạn thành MỘT mảnh,
        # và đó là lúc khách nghe chữ dính vào nhau.
        "so_manh": len(manh),
        "manh": manh,
    }


# ============================================================
# Bộ 200 câu hội thoại dài để test
# ============================================================
#
# PHẢI khai TRƯỚC các route `/{voice_name}` bên dưới. FastAPI khớp theo thứ tự
# đăng ký, nên `/bo-test` đặt sau `/{voice_name}` là bị nuốt thành tên giọng.
# Cùng họ với bẫy đã gặp: `calls.py` có `@router.get("/voices")` che mất
# `/api/voices` của chính file này.

BO_TEST_PATH = Path("data/bo_test_200_cau.json")

# Tiểu từ lễ phép. Mảnh NGẮN kết bằng chúng là chỗ khách nghe "ạ" tách rời -
# xem `TIEU_TU_CUOI_VE` bên text_chunker.
_TIEU_TU = {"ạ", "nhé", "nha", "nhá", "nhỉ", "à", "ấy"}
_TRAN_MANH_XAU = 6


def _doc_bo_test() -> dict:
    import json
    if not BO_TEST_PATH.exists():
        return {}
    return json.loads(BO_TEST_PATH.read_text(encoding="utf-8"))


def _manh_xau(manh: list[str]) -> list[str]:
    """Mảnh ngắn kết bằng tiểu từ - dấu hiệu 'ạ' bị tách thành phát ngôn riêng."""
    ra = []
    for m in manh:
        tu = m.rstrip(".,!?… ").split()
        if tu and tu[-1].lower() in _TIEU_TU and len(tu) <= _TRAN_MANH_XAU:
            ra.append(m)
    return ra


def _quang_lang(pcm, sr=24000, nguong_db=-42.0, toi_thieu_ms=120):
    """Quãng lặng NGHE RA ĐƯỢC (>=120ms), bỏ qua rìa đầu file."""
    import numpy as np

    x = pcm.astype("float32") / 32768.0
    win = int(sr * 0.01)
    n = len(x) // win
    if n == 0:
        return []
    e = np.sqrt(np.array([np.mean(x[i*win:(i+1)*win] ** 2) for i in range(n)]))
    db = 20 * np.log10(np.maximum(e, 1e-9))
    im = db < nguong_db
    ra, i = [], 0
    while i < n:
        if im[i]:
            j = i
            while j < n and im[j]:
                j += 1
            if (j - i) * 10 >= toi_thieu_ms and i > 3:
                ra.append({"tai_ms": i * 10, "dai_ms": (j - i) * 10})
            i = j
        else:
            i += 1
    return ra


@router.get("/bo-test")
async def xem_bo_test(nhom: str = ""):
    """Trả bộ câu test. `nhom` để lọc theo nhóm bẫy."""
    bo = _doc_bo_test()
    if not bo:
        return {"error": f"Không tìm thấy {BO_TEST_PATH}. Cần đẩy file bộ câu sang máy này."}
    cau = bo.get("cau", [])
    if nhom:
        cau = [c for c in cau if c.get("nhom") == nhom]
    return {"nhom": bo.get("nhom", {}), "so_cau": len(cau), "cau": cau}


@router.post("/bo-test/chay")
async def chay_bo_test(
    voice_name: str = Form("default"),
    nhom: str = Form(""),
    gioi_han: int = Form(20),
    qua_dien_thoai: bool = Form(False),
):
    """Chạy bộ câu qua ĐÚNG đường xuất voice rồi trả BÁO CÁO ĐO, không trả audio.

    Vì sao mặc định `gioi_han` 20 chứ không phải cả 200: mỗi câu tốn ~2 giây trên
    GPU, cả bộ là 6-8 phút - quá lâu cho một request HTTP, trình duyệt sẽ tự
    ngắt. Muốn chạy trọn bộ thì dùng `scripts/do_bo_test.py`, nó chạy ngoài
    request nên không bị giới hạn.

    Không trả audio: 200 câu base64 là hàng chục MB, đủ làm treo trang.
    """
    from backend.main import app_state

    if not app_state.tts._is_loaded:
        return {"error": "TTS chưa được tải."}

    import time

    import numpy as np

    bo = _doc_bo_test()
    if not bo:
        return {"error": f"Không tìm thấy {BO_TEST_PATH}."}
    cau = bo.get("cau", [])
    if nhom:
        cau = [c for c in cau if c.get("nhom") == nhom]
    if gioi_han > 0:
        cau = cau[:gioi_han]

    toc = app_state.tts.toc_do_cua(voice_name)
    if qua_dien_thoai:
        toc *= app_state.tts.he_so_thoai()

    chi_tiet = []
    t0 = time.perf_counter()
    for c in cau:
        manh = _cat_manh_nhu_pipeline(c["text"])
        try:
            wav = await _ghep_nhu_pipeline(app_state.tts, manh, voice_name, toc, False)
        except Exception as e:                       # một câu hỏng không được giết cả lô
            chi_tiet.append({"id": c["id"], "nhom": c.get("nhom"), "loi": str(e)})
            continue
        pcm = np.frombuffer(wav[44:], dtype=np.int16)
        chi_tiet.append({
            "id": c["id"],
            "nhom": c.get("nhom"),
            "text": c["text"],
            "manh": manh,
            "so_manh": len(manh),
            "tong_ms": round(len(pcm) / 24000 * 1000),
            "lang": _quang_lang(pcm),
            "manh_xau": _manh_xau(manh),
        })

    ok = [r for r in chi_tiet if "loi" not in r]
    return {
        "voice": voice_name,
        "nhom": nhom or "tất cả",
        "da_chay": len(chi_tiet),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000),
        "tong_ket": {
            "cau_co_manh_xau": sum(1 for r in ok if r["manh_xau"]),
            "so_manh_xau": sum(len(r["manh_xau"]) for r in ok),
            "tong_manh": sum(r["so_manh"] for r in ok),
            "tong_quang_lang": sum(len(r["lang"]) for r in ok),
            "loi": len(chi_tiet) - len(ok),
        },
        "chi_tiet": chi_tiet,
    }


@router.delete("/{voice_name}")
async def delete_voice(voice_name: str):
    from backend.main import app_state

    wav = VOICES_DIR / f"{voice_name}.wav"
    txt = VOICES_DIR / f"{voice_name}.txt"
    if wav.exists():
        wav.unlink()
    if txt.exists():
        txt.unlink()
    # Drop the in-memory reference too, otherwise the deleted voice keeps
    # speaking from the registry until the next restart.
    app_state.tts.drop_voice(voice_name)
    return {"deleted": voice_name}


@router.get("/{voice_name}/audio")
async def get_voice_audio(voice_name: str):
    wav = VOICES_DIR / f"{voice_name}.wav"
    if not wav.exists():
        return {"error": "File not found"}
    return FileResponse(wav, media_type="audio/wav")


class DatToc(BaseModel):
    speed: float


@router.post("/{voice_name}/speed")
async def dat_toc_giong(voice_name: str, req: DatToc):
    """Đặt tốc độ đọc RIÊNG cho một giọng.

    Vì sao cần tốc riêng chứ không một số chung: F5 sao chép cả nhịp nói của
    đoạn mẫu. Đo trên chính các đoạn đang có - giong_heu 3.44 âm tiết/giây,
    nam_moi2 chỉ 2.30, chênh 1.5 lần. Đặt tốc chung 0.64 cho vừa giọng nữ thì
    giọng nam thành lê thê.

    ĐẶT BAO NHIÊU: giữ càng SÁT 1.0 càng tốt. Tốc không chỉ là nhanh chậm - nó
    quyết định giọng có NGHE RA đúng người hay không. F5 chép âm sắc rất chuẩn
    (MFCC 0.992 với chính đoạn mẫu, 0.73 với người khác), nhưng tai người nhận
    ra một người chủ yếu qua NHỊP. Ép tốc là bóp thẳng vào nhịp: clip cũ của
    giong_heu bị ép xuống 61% nhịp thật thì đúng chất giọng mà nghe ra người
    khác. Phải hạ dưới ~0.8 nghĩa là clip mẫu nói quá nhanh so với nhu cầu -
    tìm đoạn khác trong bản thu, đừng bóp tiếp. Xem docs/doan-mau-va-nhip-noi.md
    """
    from backend.main import app_state
    tts = app_state.tts
    if tts is None:
        return {"error": "TTS chưa sẵn sàng"}
    if not (VOICES_DIR / f"{voice_name}.wav").exists():
        return {"error": f"Không có giọng '{voice_name}'"}
    toc = tts.dat_toc_do(voice_name, req.speed)
    return {"ok": True, "voice": voice_name, "speed": toc}


@router.delete("/{voice_name}/speed")
async def bo_toc_rieng(voice_name: str):
    """Bỏ tốc riêng, quay về tốc chung trong .env."""
    p = VOICES_DIR / f"{voice_name}.speed"
    if p.exists():
        p.unlink()
    from backend.main import app_state
    if app_state.tts is not None:
        app_state.tts._xoa_cache_giong(voice_name)
    return {"ok": True, "voice": voice_name}


class HeSoThoai(BaseModel):
    he_so: float


@router.get("/phone-speed")
async def xem_toc_thoai():
    """Hệ số tốc riêng cho đường gọi điện.

    Kênh GSM 8kHz nén mạnh và mất gần hết dải cao - chính dải mang phụ âm
    (s, x, ch, tr). Cùng một tốc, nghe trên web thì rõ mà qua điện thoại thì
    dính chữ. Nên tốc thoại phải chỉnh riêng.
    """
    from backend.main import app_state
    tts = app_state.tts
    if tts is None:
        return {"error": "TTS chưa sẵn sàng"}
    return {
        "he_so": tts.he_so_thoai(),
        "tran": list(tts._TRAN_HE_SO),
        "giai_thich": ("Nhân vào tốc riêng của từng giọng. 1.0 = giữ nguyên, "
                       "nhỏ hơn 1 = đọc chậm lại cho dễ nghe qua điện thoại."),
    }


@router.post("/phone-speed")
async def dat_toc_thoai(req: HeSoThoai):
    from backend.main import app_state
    tts = app_state.tts
    if tts is None:
        return {"error": "TTS chưa sẵn sàng"}
    return {"ok": True, "he_so": tts.dat_he_so_thoai(req.he_so)}


def _mo_phong_kenh_thoai(wav: bytes) -> bytes:
    """Hạ 24kHz -> 8kHz rồi nâng lại, để nghe đúng thứ khách nghe qua GSM.

    Không phải trang trí: kênh thoại cắt sạch trên 4kHz, mà đó là dải mang phụ
    âm (s, x, ch, tr). Chỉnh tốc trên bản 24kHz nghe rõ mồn một rồi ra cuộc gọi
    thật lại dính chữ - phải nghe qua đúng kênh mới chỉnh đúng.

    Chỉ mô phỏng băng thông, KHÔNG mô phỏng nén AMR. Nén còn làm tệ thêm nữa,
    nên đây là cận trên của chất lượng thật.
    """
    import io as _io
    import wave as _w

    import numpy as _np
    from scipy.signal import resample_poly

    with _w.open(_io.BytesIO(wav)) as f:
        sr = f.getframerate()
        pcm = _np.frombuffer(f.readframes(f.getnframes()), dtype=_np.int16)
    from math import gcd
    g = gcd(sr, 8000)
    tam = resample_poly(pcm.astype(_np.float64), 8000 // g, sr // g)
    lai = resample_poly(tam, sr // g, 8000 // g).astype(_np.int16)

    buf = _io.BytesIO()
    with _w.open(buf, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(lai.tobytes())
    return buf.getvalue()
