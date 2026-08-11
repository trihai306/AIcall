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


@router.post("/test-tts")
async def test_tts(
    text: str = Form(...),
    voice_name: str = Form("default"),
    fast: bool = Form(False),
    qua_dien_thoai: bool = Form(False),
    cat_manh: bool = Form(False),
):
    """Synthesize text with a specific voice and return audio + timing.

    fast=True uses the reduced diffusion steps the pipeline applies to the
    first chunk of a reply, so the quality/TTFA trade-off can be heard.

    cat_manh=True đọc y như CUỘC GỌI: cắt mảnh tăng dần 5→10→20 từ, mảnh đầu
    dùng nfe thấp, chèn nhịp nghỉ ở ranh giới mảnh, rồi ghép lại. Mặc định tắt để
    giữ bản một-phát làm mốc đối chứng - xem khối chú thích ở nhánh xử lý dưới.
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
    toc = app_state.tts.toc_do_cua(voice_name)
    if qua_dien_thoai:
        toc *= app_state.tts.he_so_thoai()

    t0 = time.perf_counter()
    try:
        # use_cache=False: đo thời gian tổng hợp thật. Nếu để cache, lần thứ hai
        # cùng câu + cùng giọng sẽ báo 0ms và bảng so sánh A/B thành vô nghĩa.
        if cat_manh:
            wav_bytes, so_manh = await _doc_nhu_cuoc_goi(
                app_state.tts, text, voice_name, toc)
        else:
            so_manh = 1
            wav_bytes = await app_state.tts.synthesize(
                text, fast=fast, voice=voice_name, use_cache=False, speed=toc
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
        "cat_manh": cat_manh,
        "so_manh": so_manh,
        "elapsed_ms": elapsed_ms,
        "duration_ms": duration_ms,
        "rtf": round(elapsed_ms / duration_ms, 3) if duration_ms else None,
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


async def _doc_nhu_cuoc_goi(tts, text: str, voice_name: str,
                            toc: float) -> tuple[bytes, int]:
    """Đọc `text` theo ĐÚNG cách đường gọi đọc nó, rồi ghép thành một wav.

    Trả `(wav, số mảnh)`.

    Vì sao trang nghe thử cần chế độ này: `synthesize()` một phát đưa NGUYÊN cả
    câu cho F5, còn cuộc gọi cắt mảnh rồi nối. Hai thứ ra khác nhau thật - đo ở
    cấu hình cắt-tăng-dần, câu demo 13 từ (giọng heu_a, cùng tốc): một phát 3110ms
    tiếng, cắt như cuộc gọi 1149+2294 = 3443ms, lệch 10,7%. Và khác cả ngữ điệu:
    F5 sinh MỖI mảnh như một phát ngôn trọn vẹn nên mỗi ranh giới mảnh là một chỗ
    nó hạ giọng kết câu giữa chừng. Chỉnh tốc/chọn giọng trên bản một phát rồi suy
    ra cuộc gọi là đúng cái bẫy đã mắc với tốc 0.64/1.20.

    Ba thứ lấy nguyên từ đường gọi, KHÔNG đặt lại số ở đây - nhờ vậy đổi luật cắt
    thì chế độ này đi theo, không phải sửa:
      - `chia_ca_luot`  : ranh giới mảnh, theo luật đang bật (cắt theo số từ hay
                          theo nguyên câu là do `text_chunker` quyết, không phải
                          do đây)
      - `nhip_nghi_sau` : nhịp nghỉ sau mỗi mảnh, cũng theo luật đang bật
      - `fast` cho mảnh ĐẦU: y như `fast=(idx == 0)` ở streaming_pipeline

    Khác đường gọi ĐÚNG một chỗ, và là chỗ cố ý: sinh lần lượt chứ không song
    song. Cuộc gọi vừa sinh vừa phát nên mảnh sau chạy trong lúc mảnh trước đang
    phát; ở đây phải có đủ cả bài mới ghép được. Nên `elapsed_ms` của chế độ này
    là TỔNG thời gian sinh, không phải thời gian khách chờ - muốn xem thời gian
    chờ tiếng đầu thì đọc `tts_first_ms` trên bảng số của cuộc gọi thật.
    """
    from backend.pipeline.text_chunker import chia_ca_luot, nhip_nghi_sau
    from backend.services.audio_utils import chen_lang_dau_wav, noi_wav

    manh = chia_ca_luot(text)
    if not manh:
        return b"", 0

    cac_wav: list[bytes] = []
    nghi_ms = 0.0
    for i, m in enumerate(manh):
        w = await tts.synthesize(m, fast=(i == 0), voice=voice_name,
                                 use_cache=False, speed=toc)
        # Chèn nhịp nghỉ vào ĐẦU mảnh này (nợ từ mảnh trước), không nối vào cuối
        # mảnh trước - y hệt vòng phát của streaming_pipeline, nhờ vậy mảnh đầu
        # không bao giờ bị chèn và mảnh cuối không có đuôi lặng thừa.
        if w and nghi_ms > 0:
            w = chen_lang_dau_wav(w, nghi_ms)
        nghi_ms = nhip_nghi_sau(m)
        cac_wav.append(w)

    return noi_wav(cac_wav), len(manh)


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
