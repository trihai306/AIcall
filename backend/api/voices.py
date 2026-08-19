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

    # Bản ghi dài KHÔNG phải đoạn mẫu. F5 chép nguyên tệp mẫu, nên để một bản
    # ghi 20 phút vào đây là vừa vô nghĩa vừa chậm. Cho vào kho nguồn chờ tách,
    # và KHÔNG đăng ký làm giọng - giọng chỉ ra đời khi người dùng chọn xong
    # một đoạn ở trang Phân tích.
    if probe["duration"] > NGUON_TOI_THIEU_S:
        NGUON_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(wav_path), str(NGUON_DIR / f"{safe_name}.wav"))
        logger.info("Nhận bản ghi nguồn %s (%.0fs) - chờ tách đoạn mẫu",
                    safe_name, probe["duration"])
        return {
            "nguon": safe_name,
            "duration": probe["duration"],
            "size_kb": round(len(content) / 1024, 1),
            "thong_bao": (
                f"Bản ghi dài {probe['duration']:.0f}s đã vào kho nguồn. "
                "Bấm \u201cPhân tích\u201d để máy tìm đoạn mẫu tốt nhất."
            ),
        }

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


async def _sinh_co_bu_duoi(tts, chu: str, voice_name: str, toc: float,
                           fast: bool):
    """Sinh một mảnh, cho F5 ngân vào MẨU BÙ rồi cắt mẩu đó đi.

    Xem `backend/services/bu_duoi.py` để biết vì sao cần và vì sao phải cắt bằng
    mốc từng chữ. Tốn thêm một lượt STT mỗi mảnh nên CHỈ dùng ở đường xuất.

    Hỏng ở bất kỳ khâu nào (STT chết, không thấy mẩu bù, mốc vô lý) thì lùi về
    bản sinh THƯỜNG - đường xuất không được vì một tính năng làm đẹp mà trả về
    tiếng cụt.
    """
    import numpy as np

    from backend.main import app_state
    from backend.services import bu_duoi as B

    b = await tts.synthesize(chu + B.MAU_BU, voice=voice_name, use_cache=False,
                             speed=toc, fast=fast)
    pcm = np.frombuffer(b[44:], dtype=np.int16)
    try:
        doan = await app_state.stt.moc_tung_chu(b)
        moc = B.tim_moc_cat(doan)
    except Exception as e:
        logger.warning("bù đuôi: không lấy được mốc chữ (%s) — dùng bản thường", e)
        moc = None
    if moc is None:
        return np.frombuffer(
            (await tts.synthesize(chu, voice=voice_name, use_cache=False,
                                  speed=toc, fast=fast))[44:], dtype=np.int16)
    return B.cat_theo_moc(pcm, 24000, moc)


async def _ghep_nhu_pipeline(tts, manh: list[str], voice_name: str,
                             toc: float, fast: bool, bu_duoi: bool = False,
                             nen_duoi: bool = False,
                             gop_sau: bool = False,
                             gop_phay: bool = False,
                             he_so_bu: float | None = None) -> bytes:
    """Sinh từng mảnh rồi ghép, chèn lặng đúng lượng `nhip_nghi_sau` cho.

    Chèn vào ĐẦU mảnh sau chứ không nối vào cuối mảnh trước - giống hệt
    `streaming_pipeline`, nhờ vậy mảnh đầu không bị thêm gì và mảnh cuối không
    có đuôi lặng thừa.

    `fast` chỉ áp cho mảnh ĐẦU, vì `f5tts_nfe_step_first` trong đường thật cũng
    chỉ dùng cho mảnh đầu. Áp cho mọi mảnh là nghe ra một thứ không tồn tại.
    """
    import numpy as np

    from backend.pipeline.text_chunker import (nen_duoi_manh_nay,
                                                nhip_nghi_sau)
    from backend.services.audio_utils import pcm_to_wav
    from backend.services.nen_duoi_manh import nen_duoi as _nen

    SR = 24000
    # GỘP mọi mảnh SAU mảnh đầu thành một. Chỉ mảnh ĐẦU tính vào thời gian khách
    # chờ; mảnh sau sinh trong lúc mảnh trước đang phát, nên to lên gần như miễn
    # phí. Mỗi mảnh đẻ ~1 chữ ngân ở đuôi, nên ít mảnh là ít chỗ ngân.
    #
    # ĐÁNH ĐỔI: gộp rồi thì `nhip_nghi_sau` không còn chỗ để chèn quãng nghỉ,
    # phải trông vào quãng nghỉ F5 TỰ tạo - mà F5 gần như LỜ dấu phẩy (đo 0/6).
    if gop_sau and len(manh) > 2:
        manh = [manh[0], " ".join(manh[1:])]
    # GỘP CHỖ PHẨY. Nhắm đúng chỗ hỏng thay vì gộp mù:
    #
    #   - ranh giới ở dấu CHẤM  -> âm cuối dài ra là ĐÚNG, người thật cũng vậy.
    #     Giữ nguyên mảnh riêng để còn quãng nghỉ hết câu.
    #   - ranh giới ở dấu PHẨY  -> chỗ dài ra rơi vào GIỮA câu, nghe như "ngân".
    #     Gộp lại cho F5 đọc liền.
    #
    # KHÔNG đụng vào mảnh ĐẦU: chỉ nó tính vào thời gian khách chờ.
    elif gop_phay and len(manh) > 2:
        ra = [manh[0]]
        for m in manh[1:]:
            if len(ra) > 1 and ra[-1].rstrip().endswith(","):
                ra[-1] = ra[-1].rstrip() + " " + m
            else:
                ra.append(m)
        manh = ra
    khuc: list[np.ndarray] = []
    nghi_ms = 0.0
    for i, m in enumerate(manh):
        if bu_duoi:
            pcm = await _sinh_co_bu_duoi(tts, m, voice_name, toc, fast and i == 0)
        else:
            b = await tts.synthesize(m, voice=voice_name, use_cache=False,
                                     speed=toc, fast=(fast and i == 0),
                                     he_so_bu=he_so_bu)
            pcm = np.frombuffer(b[44:], dtype=np.int16)
        # Nén phần ngân ở đuôi - CHỈ cho mảnh không phải mảnh cuối. Mảnh cuối
        # kéo dài là kết câu THẬT, nghe tự nhiên; đụng vào là làm hỏng.
        # Nén đuôi CHỈ khi mảnh kết bằng tiểu từ - xem `nen_duoi_manh_nay`.
        # Nén mọi đuôi thì WER 0,94% -> 1,79% mà chỗ ngân chỉ giảm 17 -> 15.
        if nen_duoi and i < len(manh) - 1 and nen_duoi_manh_nay(m):
            pcm = _nen(pcm, SR)
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
    bu_duoi: bool = Form(False),
    nen_duoi: bool = Form(False),
    gop_sau: bool = Form(False),
    gop_phay: bool = Form(False),
    he_so_bu: float | None = Form(None),
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
            app_state.tts, manh, voice_name, toc, fast, bu_duoi=bu_duoi,
            nen_duoi=nen_duoi, gop_sau=gop_sau, gop_phay=gop_phay,
            he_so_bu=he_so_bu,
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


# =========================================================================
# NGUỒN GHI ÂM DÀI -> gợi ý đoạn mẫu
# =========================================================================
#
# F5 chép giọng từ một đoạn mẫu ngắn, nên chọn đoạn nào quyết định chất lượng
# ngang với model. Chọn tay mất ~2 giờ mỗi giọng và rất dễ sai theo kiểu khó
# truy: 17-08-2026 bên A báo chữ "ạ" nghe không tự nhiên, gốc là đoạn mẫu đang
# dùng không có lấy một chữ "ạ" nào trong suốt 20 phút bản ghi.
#
# Luồng: tải bản ghi dài -> bấm Phân tích -> nghe danh sách ứng viên -> chọn.
# KHÔNG tự lắp: con số chỉ để loại bớt, tai người quyết.

NGUON_DIR = Path("models/tts/nguon")
PHAN_TICH_DIR = NGUON_DIR / ".phan_tich"

# Dài hơn thế thì coi là bản ghi nguồn cần tách, không phải đoạn mẫu đã cắt sẵn.
NGUON_TOI_THIEU_S = 30.0

# Chấm âm học thì rẻ, cho STT nghe lại thì đắt. Nên xếp hạng bằng số đo rẻ
# trước, rồi chỉ kiểm lời cho tốp đầu.
KIEM_LOI_N = 24
TRA_VE_N = 8

# Nhịp muốn AI nói, âm tiết/phút. Lấy từ `scripts/chon_doan_mau.py`: giọng
# telesales tự nhiên ~190, còn giọng gốc trong bản ghi thường nhanh hơn nhiều.
NHIP_MUON = 190.0

_VIEC: dict[str, dict] = {}


def _ten_sach(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_").strip()


def _doc_nguon(ten: str):
    import numpy as np
    import soundfile as sf

    # KHÔNG dùng always_2d: với tệp mono nó trả (N,1) rồi `.mean` cấp thêm một
    # mảng (N,) nữa - trên bản ghi 20 phút là thừa ra hơn 200MB.
    x, sr = sf.read(str(NGUON_DIR / f"{ten}.wav"), dtype="float32")
    x = np.asarray(x)
    return (x.mean(axis=1) if x.ndim > 1 else x), sr


def _wav_bytes(x, sr: int) -> bytes:
    import io as _io

    import soundfile as sf

    b = _io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    return b.getvalue()


async def _nghe_lai(stt, x, sr: int) -> str:
    """Cho STT nghe lại chính clip đã cắt.

    Dùng `moc_tung_chu` chứ không `transcribe`: `transcribe` mồi từ vựng ngân
    hàng, mà bản ghi nguồn nằm ngoài miền đó - mồi vào là nghe chệch đúng chỗ
    ta đang cần kiểm.
    """
    try:
        doan = await stt.moc_tung_chu(_wav_bytes(x, sr))
    except Exception as e:
        logger.warning("nghe lại ứng viên hỏng: %s", e)
        return ""
    return " ".join((d.get("text") or "").strip() for d in doan).strip()


async def _khao_sat(ten: str, nghe_lai: bool = False):
    """Chạy nền: nghe hết bản ghi, tách, đo, xếp hạng, ghi wav xem trước.

    Kết quả NGHE được cất lại. Nghe hết bản ghi 20 phút mất ~4 phút, mà khâu hay
    phải chỉnh lại là tách/chấm chứ không phải nghe - giữ bản nghe thì mỗi lần
    chỉnh chỉ mất vài giây. `nghe_lai=True` để nghe lại từ đầu.
    """
    import json

    import numpy as np

    from backend.main import app_state
    from backend.services.chon_doan_mau import (cer, cham_diem, cua_so_ngat,
                                                dep_de_len, nan_moc,
                                                tach_don_vi, xep_hang)

    viec = _VIEC[ten]
    try:
        x, sr = _doc_nguon(ten)
        PHAN_TICH_DIR.mkdir(parents=True, exist_ok=True)
        kho = PHAN_TICH_DIR / f"{ten}.stt.json"

        if kho.exists() and not nghe_lai:
            doan = json.loads(kho.read_text(encoding="utf-8"))
            viec.update(tong=0, xong=0, tien=90, dung_ban_nghe_cu=True)
        else:
            cs = cua_so_ngat(x, sr)
            viec["tong"] = len(cs)
            doan = []
            for n, (a, b) in enumerate(cs):
                segs = await app_state.stt.moc_tung_chu(_wav_bytes(x[a:b], sr))
                lech = a / sr
                for s in segs:                   # mốc trong cửa sổ -> mốc cả tệp
                    for w in s.get("words") or []:
                        w["start"] = float(w.get("start", 0.0)) + lech
                        w["end"] = float(w.get("end", 0.0)) + lech
                doan.extend(segs)
                viec["xong"] = n + 1
                viec["tien"] = round((n + 1) / len(cs) * 90)
            kho.write_text(json.dumps(doan, ensure_ascii=False), encoding="utf-8")

        uv = tach_don_vi(doan)
        viec["tach_duoc"] = len(uv)
        # Nắn mốc cắt về chỗ lặng thật trong SÓNG ÂM. Mốc chữ của Whisper là kết
        # quả căn chữ chứ không phải ranh giới âm - cắt đúng vào đó là cắt giữa
        # một phụ âm, clip mở đầu bằng âm cụt, STT nghe lại ra khác, và ứng viên
        # trượt khâu kiểm lời dù nội dung tốt. Đúng là cách đoạn hay nhất của
        # bản ghi ("em thấy tự ti...") bị loại ở lần chạy 18-08.
        for d in uv:
            d["m_a"] = nan_moc(x, sr, int(d["a"] * sr))
            d["m_b"] = nan_moc(x, sr, int(d["b"] * sr))
            clip = x[d["m_a"]:d["m_b"]]
            d.update(cham_diem(clip, sr, d["loi"], d["loi"]))   # lệch lời tính sau

        # Dẹp trùng TRƯỚC khi kiểm lời: cho phép bắt đầu ở nhiều chỗ thì cùng
        # một câu đẻ ra chục biến thể lệch vài từ, và chúng chiếm hết suất của
        # khâu đắt nhất. Đo được: 1520 ứng viên mà hai cái đứng đầu là cùng một
        # câu, nên đoạn hay nhất của bản ghi không tới lượt kiểm.
        tot = dep_de_len(xep_hang(uv))[:KIEM_LOI_N]
        for d in tot:
            d["nghe_lai"] = await _nghe_lai(app_state.stt, x[d["m_a"]:d["m_b"]], sr)
            d["lech_loi"] = round(cer(d["loi"], d["nghe_lai"]), 4)
        viec["tien"] = 95

        cuoi = xep_hang(tot)[:TRA_VE_N]
        ra = PHAN_TICH_DIR / ten
        ra.mkdir(parents=True, exist_ok=True)
        for i, d in enumerate(cuoi):
            (ra / f"{i}.wav").write_bytes(_wav_bytes(x[d["m_a"]:d["m_b"]], sr))
            d["i"] = i
            # Lời ghi vào .txt là thứ STT nghe được TRÊN CHÍNH CLIP ĐÃ CẮT, không
            # phải lời suy ra từ lượt nghe cả tệp - như vậy lệch lời bằng 0 theo
            # cấu tạo. Đây đúng là chỗ đã hỏng: clip lệch lời 12,5% cho WER 160%.
            d["loi_ghi"] = d.get("nghe_lai") or d["loi"]
            d["am_tiet"] = len([t for t in d["loi_ghi"].split() if t.strip()])
            nhip = d["am_tiet"] / d["dai"] * 60 if d["dai"] else 0.0
            d["nhip_goc"] = round(nhip)
            d["toc_de_xuat"] = round(min(1.0, NHIP_MUON / nhip), 2) if nhip else 1.0

        viec.update(trang_thai="xong", tien=100, ung_vien=cuoi,
                    loai_bo=len(uv) - len(cuoi))
        (PHAN_TICH_DIR / f"{ten}.json").write_text(
            json.dumps({"ung_vien": cuoi, "tach_duoc": len(uv)},
                       ensure_ascii=False), encoding="utf-8")
        logger.info("Khảo sát %s: tách %d, giữ %d", ten, len(uv), len(cuoi))
    except Exception as e:
        logger.exception("Khảo sát nguồn %s hỏng", ten)
        viec.update(trang_thai="hong", loi=str(e))


@router.get("/nguon")
async def ds_nguon():
    """Bản ghi dài đang chờ tách."""
    import json

    NGUON_DIR.mkdir(parents=True, exist_ok=True)
    ra = []
    for w in sorted(NGUON_DIR.glob("*.wav")):
        ten = w.stem
        j = PHAN_TICH_DIR / f"{ten}.json"
        viec = _VIEC.get(ten) or {}
        ra.append({
            "ten": ten,
            "mb": round(w.stat().st_size / 1024 / 1024, 1),
            "trang_thai": viec.get("trang_thai") or ("xong" if j.exists() else "chua"),
            "tien": viec.get("tien", 100 if j.exists() else 0),
            "so_ung_vien": len(json.loads(j.read_text(encoding="utf-8"))["ung_vien"])
            if j.exists() else 0,
        })
    return {"nguon": ra}


@router.post("/nguon/{ten}/phan-tich")
async def phan_tich_nguon(ten: str, nghe_lai: bool = False):
    """Bắt đầu khảo sát. Trả ngay, hỏi tiến độ bằng GET cùng đường dẫn.

    Bản ghi 20 phút mất khoảng 2 phút để nghe hết - giữ nguyên một request HTTP
    suốt thời gian đó là mời đứt kết nối.
    """
    import asyncio

    ten = _ten_sach(ten)
    if not (NGUON_DIR / f"{ten}.wav").exists():
        return {"error": f"Không thấy bản ghi nguồn '{ten}'"}
    if (_VIEC.get(ten) or {}).get("trang_thai") == "dang_chay":
        return {"trang_thai": "dang_chay", "tien": _VIEC[ten].get("tien", 0)}

    _VIEC[ten] = {"trang_thai": "dang_chay", "tien": 0}
    asyncio.create_task(_khao_sat(ten, nghe_lai))
    return {"trang_thai": "dang_chay", "tien": 0}


@router.get("/nguon/{ten}/phan-tich")
async def xem_phan_tich(ten: str):
    """Tiến độ, hoặc kết quả nếu đã xong."""
    import json

    ten = _ten_sach(ten)
    viec = _VIEC.get(ten)
    if viec and viec.get("trang_thai") == "dang_chay":
        return {"trang_thai": "dang_chay", "tien": viec.get("tien", 0),
                "xong": viec.get("xong", 0), "tong": viec.get("tong", 0)}
    if viec and viec.get("trang_thai") == "hong":
        return {"trang_thai": "hong", "error": viec.get("loi", "")}

    j = PHAN_TICH_DIR / f"{ten}.json"
    if not j.exists():
        return {"trang_thai": "chua"}
    d = json.loads(j.read_text(encoding="utf-8"))
    return {"trang_thai": "xong", "tien": 100, **d}


@router.get("/nguon/{ten}/ung-vien/{i}.wav")
async def nghe_ung_vien(ten: str, i: int):
    p = PHAN_TICH_DIR / _ten_sach(ten) / f"{int(i)}.wav"
    if not p.exists():
        return {"error": "Chưa có ứng viên này - chạy Phân tích trước"}
    return FileResponse(str(p), media_type="audio/wav")


class ChonUngVien(BaseModel):
    i: int
    ten_giong: str
    dat_toc: bool = True


@router.post("/nguon/{ten}/chon")
async def chon_ung_vien(ten: str, body: ChonUngVien):
    """Lắp ứng viên đã chọn thành một giọng dùng được."""
    import json
    import shutil

    from backend.main import app_state

    ten = _ten_sach(ten)
    giong = _ten_sach(body.ten_giong)
    if not giong:
        return {"error": "Tên giọng không hợp lệ"}

    j = PHAN_TICH_DIR / f"{ten}.json"
    wav = PHAN_TICH_DIR / ten / f"{int(body.i)}.wav"
    if not (j.exists() and wav.exists()):
        return {"error": "Chưa có kết quả phân tích cho bản ghi này"}

    ds = json.loads(j.read_text(encoding="utf-8"))["ung_vien"]
    u = next((z for z in ds if z.get("i") == int(body.i)), None)
    if u is None:
        return {"error": f"Không có ứng viên số {body.i}"}

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(wav), str(VOICES_DIR / f"{giong}.wav"))
    (VOICES_DIR / f"{giong}.txt").write_text(u["loi_ghi"].strip() + "\n",
                                             encoding="utf-8")

    # Sổ giọng chốt lời đoạn mẫu MỘT LẦN lúc khởi động. Ghi .txt xong mà không
    # dọn thì giọng vẫn giữ lời cũ -> lệch lời -> F5 đọc ra rác. Đã gặp thật:
    # mảnh "Dạ vâng," ra "dự báo tổng thống chuẩn bị thành phố đà nẵng...",
    # 8/8 lần, tất định. `upload_voice` cũng dọn đúng kiểu này (xem trên).
    app_state.tts.drop_voice(giong)
    if body.dat_toc and u.get("toc_de_xuat"):
        app_state.tts.dat_toc_do(giong, float(u["toc_de_xuat"]))
    await app_state.tts.ensure_voice(giong)

    logger.info("Lắp giọng %s từ %s ứng viên #%s (%.2fs, tốc %.2f)",
                giong, ten, body.i, u.get("dai", 0.0), u.get("toc_de_xuat", 1.0))
    return {"ten": giong, "dai": u.get("dai"), "loi": u["loi_ghi"],
            "toc": u.get("toc_de_xuat")}


@router.delete("/nguon/{ten}")
async def xoa_nguon(ten: str):
    import shutil

    ten = _ten_sach(ten)
    (NGUON_DIR / f"{ten}.wav").unlink(missing_ok=True)
    (PHAN_TICH_DIR / f"{ten}.json").unlink(missing_ok=True)
    shutil.rmtree(PHAN_TICH_DIR / ten, ignore_errors=True)
    _VIEC.pop(ten, None)
    return {"ok": True}


# =========================================================================
# TEST HỘI THOẠI — nghe giọng chạy trọn một cuộc tư vấn
# =========================================================================
#
# Nghe một câu rời không nói lên được điều gì về thứ khách thật sự nghe. Mọi lỗi
# bên A báo suốt tháng 8 đều là lỗi GIỮA CÁC LƯỢT chứ không nằm trong một câu:
# tông lạc quẻ giữa các mảnh, "ạ" chưa ngắt xong đã đọc từ sau, tiếng lúc to lúc
# bé. Muốn bắt được thì phải nghe liền mạch nhiều lượt.
#
# Và với đoạn mẫu thì càng đúng: nghe mẩu gốc do NGƯỜI nói không cho biết F5 sẽ
# đọc ra sao. Muốn so hai ứng viên thì phải nghe chính chúng đọc cùng một cuộc
# thoại.

HOI_THOAI_LUOT = 4
KHE_LUOT_MS = 900          # chỗ trống cho lượt của khách


# Lượt của KHÁCH viết sẵn, không nhờ LLM sinh. Hai lý do:
#
#  1. Mô hình đã tinh chỉnh (LoRA) để trả lời MỘT lượt với tư cách nhân viên.
#     Bảo nó viết cả kịch bản là đi ngược huấn luyện - thử thật thì nó trả về
#     đúng 1 dòng rồi dừng, dù prompt xin 4 lượt.
#  2. Lượt khách cố định thì hai giọng nghe thử trên CÙNG một cuộc thoại, mới so
#     được với nhau. Sinh ngẫu nhiên là mỗi lần một nội dung, không so nổi.
#
# Nội dung bám sát thứ khách thật hay nói: hỏi lãi, đắn đo, hỏi thủ tục, chốt.
LUOT_KHACH = [
    "Ừ em nói đi.",
    "Lãi suất bên em bao nhiêu vậy?",
    "Anh đang bận, để anh suy nghĩ thêm đã.",
    "Thế thủ tục cần giấy tờ gì em?",
    "Ừ vậy em gửi thông tin cho anh nhé.",
    "Được rồi em, cảm ơn em.",
]


def _tach_luot_ai(van: str, so_luot: int) -> list[str]:
    """Giữ lại để tương thích; đường chính không dùng nữa."""
    ra = []
    for dong in (van or "").splitlines():
        d = dong.strip().lstrip("*-\u2022 ").strip()
        for dau in ("AI:", "AI :", "NHANVIEN:", "NHÂN VIÊN:"):
            if d.upper().startswith(dau.upper()):
                cau = d[len(dau):].strip().strip("*").strip()
                if cau:
                    ra.append(cau)
                break
    return ra[:so_luot]


async def _sinh_cuoc_thoai(llm, kb: dict, so_luot: int) -> list[str]:
    """Chạy ĐÚNG vòng thoại của cuộc gọi thật: khách nói -> AI đáp -> lặp.

    Không dùng `generate_simple`: nó chặn cứng ở 100 token và chuỗi dừng cắt
    ngay khi gặp nhãn lượt khách, nên chỉ ra được một dòng.

    Lượt đầu là câu mở đầu của kịch bản - y như cuộc gọi thật, câu đó do code
    đọc chứ không do mô hình sinh.
    """
    ra = [(kb.get("opening_line") or "Dạ em chào anh chị ạ.").strip()]
    lich_su: list[dict] = [{"role": "assistant", "content": ra[0]}]
    mo_ta = llm.build_system_prompt(scenario=kb)

    for n in range(so_luot - 1):
        lich_su.append({"role": "user", "content": LUOT_KHACH[n % len(LUOT_KHACH)]})
        chu = []
        try:
            async for t in llm.stream_response(lich_su, mo_ta):
                chu.append(t)
        except Exception as e:
            logger.warning("lượt %d của AI hỏng: %s", n + 2, e)
            break
        cau = "".join(chu).strip()
        if not cau:
            break
        ra.append(cau)
        lich_su.append({"role": "assistant", "content": cau})
    return ra


async def _giong_tam_tu_ung_vien(nguon: str, i: int) -> str | None:
    """Lắp tạm một ứng viên thành giọng để nghe thử, trả về tên giọng tạm."""
    import json
    import shutil

    from backend.main import app_state

    j = PHAN_TICH_DIR / f"{nguon}.json"
    wav = PHAN_TICH_DIR / nguon / f"{int(i)}.wav"
    if not (j.exists() and wav.exists()):
        return None
    ds = json.loads(j.read_text(encoding="utf-8"))["ung_vien"]
    u = next((z for z in ds if z.get("i") == int(i)), None)
    if u is None:
        return None

    ten = f"thu_{nguon}_{int(i)}"
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(wav), str(VOICES_DIR / f"{ten}.wav"))
    (VOICES_DIR / f"{ten}.txt").write_text(u["loi_ghi"].strip() + "\n", encoding="utf-8")
    app_state.tts.drop_voice(ten)                 # xem chú thích ở `chon_ung_vien`
    if u.get("toc_de_xuat"):
        app_state.tts.dat_toc_do(ten, float(u["toc_de_xuat"]))
    await app_state.tts.ensure_voice(ten)
    return ten


@router.post("/test-hoi-thoai")
async def test_hoi_thoai(
    voice_name: str = Form("default"),
    nguon: str = Form(""),
    i: int = Form(-1),
    so_luot: int = Form(HOI_THOAI_LUOT),
    qua_dien_thoai: bool = Form(False),
    kich_ban_id: str = Form(""),
):
    """Cho AI sinh một cuộc thoại rồi đọc trọn bằng giọng đang chọn.

    Đọc qua ĐÚNG đường của cuộc gọi thật (`_cat_manh_nhu_pipeline` +
    `_ghep_nhu_pipeline`) chứ không đưa cả đoạn cho F5 một phát - nếu không thì
    nghe ra một thứ không tồn tại, và đúng những lỗi cần bắt (tông lạc giữa
    mảnh, dính chữ sau tiểu từ) lại biến mất khỏi bản nghe.
    """
    import base64
    import time

    import numpy as np

    from backend.main import app_state
    from backend.models import scenarios_db
    from backend.services.audio_utils import pcm_to_wav

    if not app_state.tts._is_loaded:
        return {"error": "TTS chưa được tải."}

    so_luot = max(1, min(int(so_luot), 8))
    tam = None
    if nguon and i >= 0:
        tam = await _giong_tam_tu_ung_vien(_ten_sach(nguon), i)
        if not tam:
            return {"error": "Không thấy ứng viên này - chạy Phân tích trước"}
        voice_name = tam

    try:
        ds = await scenarios_db.list_scenarios()
        kb = next((k for k in ds if k.get("scenario_id") == kich_ban_id), None) \
            or (ds[0] if ds else {})

        t0 = time.perf_counter()
        try:
            luot = await _sinh_cuoc_thoai(app_state.llm, kb, so_luot)
        except Exception as e:
            return {"error": f"LLM không sinh được hội thoại: {e}"}
        lui = len(luot) < so_luot          # LLM tắt giữa chừng -> nói rõ, đừng im
        ms_llm = round((time.perf_counter() - t0) * 1000)

        toc = app_state.tts.toc_nghe_thu(voice_name)
        if qua_dien_thoai:
            toc *= app_state.tts.he_so_thoai()

        SR = 24000
        khe = np.zeros(int(SR * KHE_LUOT_MS / 1000), dtype=np.int16)
        cac_luot, pcm = [], []
        for n, cau in enumerate(luot):
            manh = _cat_manh_nhu_pipeline(cau)
            try:
                wav = await _ghep_nhu_pipeline(app_state.tts, manh, voice_name, toc, False)
            except Exception as e:
                cac_luot.append({"text": cau, "loi": str(e)})
                continue
            x = np.frombuffer(wav[44:], dtype=np.int16)
            if n:
                pcm.append(khe)
            pcm.append(x)
            cac_luot.append({"text": cau, "so_manh": len(manh), "manh": manh,
                             "ms": round(len(x) / SR * 1000)})

        if not pcm:
            return {"error": "Không đọc được lượt nào."}
        ca_bai = np.concatenate(pcm)
        return {
            "voice": voice_name,
            "tam": bool(tam),
            "kich_ban": kb.get("name", ""),
            "thieu_luot": lui,
            "ms_llm": ms_llm,
            "tong_ms": round(len(ca_bai) / SR * 1000),
            "luot": cac_luot,
            "khach": LUOT_KHACH[:max(0, len(luot) - 1)],
            "audio": base64.b64encode(pcm_to_wav(ca_bai.tobytes(), SR)).decode(),
        }
    finally:
        # Giọng tạm phải dọn ngay, không thì mỗi lần nghe thử lại đẻ một giọng
        # rác trong danh sách - mà danh sách giọng chính là chỗ người dùng chọn
        # giọng cho cuộc gọi thật.
        if tam:
            (VOICES_DIR / f"{tam}.wav").unlink(missing_ok=True)
            (VOICES_DIR / f"{tam}.txt").unlink(missing_ok=True)
            (VOICES_DIR / f"{tam}.speed").unlink(missing_ok=True)
            app_state.tts.drop_voice(tam)


# =========================================================================
# NGHE HÀNG LOẠT — so các ứng viên đoạn mẫu trên cùng một bộ hội thoại
# =========================================================================
#
# Nghe từng ứng viên một câu thì không quyết được. Cách duy nhất chọn đúng là
# nghe CHÍNH chúng đọc nhiều cuộc thoại khác nhau, và các ứng viên phải đọc
# CÙNG một bộ nội dung - khác nội dung thì không so nổi.
#
# Sinh lại cùng một câu bằng cùng một giọng cho ra tệp Y HỆT (hạt giống suy từ
# chữ). Nên biến thiên phải nằm ở NỘI DUNG và ở ỨNG VIÊN, không phải ở số lần.

NGHE_LOAT_MAC_DINH = 100

# Mỗi bộ là một kiểu khách. Đủ khác nhau để lộ ra chỗ giọng đuối: khách xuôi
# theo, khách hỏi dồn, khách gắt, khách lơ đãng.
BO_KHACH = [
    ["Ừ em nói đi.", "Lãi suất bao nhiêu em?", "Ừ vậy em gửi thông tin nhé."],
    ["Alo ai đấy?", "Anh không có nhu cầu.", "Thôi em nhé, anh bận."],
    ["Vay được bao nhiêu em?", "Thủ tục cần gì?", "Bao lâu thì giải ngân?"],
    ["Em gọi có việc gì?", "Anh đang lái xe.", "Gọi lại anh sau nhé."],
    ["Bên em là ngân hàng nào?", "Có phí gì ẩn không em?", "Ừ để anh xem đã."],
    ["Chị nghe đây.", "Lãi thế cao quá em.", "Có giảm được không?"],
]


def _bo_khach_thu(k: int) -> list[str]:
    return BO_KHACH[k % len(BO_KHACH)]


async def _sinh_cuoc_thoai_voi(llm, kb: dict, khach: list[str]) -> list[str]:
    """Như `_sinh_cuoc_thoai` nhưng nhận sẵn bộ lượt khách."""
    ra = [(kb.get("opening_line") or "Dạ em chào anh chị ạ.").strip()]
    lich_su = [{"role": "assistant", "content": ra[0]}]
    mo_ta = llm.build_system_prompt(scenario=kb)
    for cau_khach in khach:
        lich_su.append({"role": "user", "content": cau_khach})
        chu = []
        try:
            async for t in llm.stream_response(lich_su, mo_ta):
                chu.append(t)
        except Exception as e:
            logger.warning("lượt AI hỏng: %s", e)
            break
        cau = "".join(chu).strip()
        if not cau:
            break
        ra.append(cau)
        lich_su.append({"role": "assistant", "content": cau})
    return ra


async def _nghe_hang_loat(ten: str, tong: int, so_luot: int):
    """Chạy nền: sinh hội thoại rồi cho TỪNG ứng viên đọc CÙNG bộ nội dung."""
    import json

    import numpy as np

    from backend.main import app_state
    from backend.models import scenarios_db
    from backend.services.audio_utils import pcm_to_wav

    viec = _VIEC[f"nghe:{ten}"]
    try:
        j = PHAN_TICH_DIR / f"{ten}.json"
        if not j.exists():
            raise RuntimeError("Chưa phân tích bản ghi này")
        uv = json.loads(j.read_text(encoding="utf-8"))["ung_vien"]
        if not uv:
            raise RuntimeError("Không có ứng viên nào")

        ds = await scenarios_db.list_scenarios()
        kb = ds[0] if ds else {}

        so_bien = max(1, -(-tong // len(uv)))          # làm tròn LÊN
        viec.update(tong=so_bien * len(uv), xong=0)

        # 1. Sinh nội dung TRƯỚC, dùng chung cho mọi ứng viên. Mỗi ứng viên tự
        #    sinh nội dung riêng là không so được với nhau.
        thoai = []
        for k in range(so_bien):
            luot = await _sinh_cuoc_thoai_voi(app_state.llm, kb,
                                              _bo_khach_thu(k)[:so_luot - 1])
            thoai.append(luot)
            viec["tien"] = round((k + 1) / so_bien * 30)
        viec["so_bien"] = len(thoai)

        # 2. Từng ứng viên đọc từng bộ nội dung.
        ra = PHAN_TICH_DIR / ten / "nghe"
        ra.mkdir(parents=True, exist_ok=True)
        for cu in ra.glob("*.wav"):
            cu.unlink()

        SR = 24000
        khe = np.zeros(int(SR * KHE_LUOT_MS / 1000), dtype=np.int16)
        muc = []
        xong = 0
        for u in uv:
            giong = await _giong_tam_tu_ung_vien(ten, u["i"])
            if not giong:
                continue
            try:
                toc = app_state.tts.toc_nghe_thu(giong)
                for k, luot in enumerate(thoai):
                    pcm = []
                    for n, cau in enumerate(luot):
                        try:
                            wav = await _ghep_nhu_pipeline(
                                app_state.tts, _cat_manh_nhu_pipeline(cau),
                                giong, toc, False)
                        except Exception as e:
                            logger.warning("ứng viên %s bộ %d lượt %d hỏng: %s",
                                           u["i"], k, n, e)
                            continue
                        if n:
                            pcm.append(khe)
                        pcm.append(np.frombuffer(wav[44:], dtype=np.int16))
                    xong += 1
                    viec.update(xong=xong,
                                tien=30 + round(xong / max(1, viec["tong"]) * 70))
                    if not pcm:
                        continue
                    ca = np.concatenate(pcm)
                    ten_tep = f"uv{u['i']}_bo{k}.wav"
                    (ra / ten_tep).write_bytes(pcm_to_wav(ca.tobytes(), SR))
                    muc.append({
                        "tep": ten_tep, "i": u["i"], "bo": k,
                        "ms": round(len(ca) / SR * 1000),
                        "dai_mau": u.get("dai"), "loi_mau": u.get("loi_ghi", ""),
                        "co_tieu_tu": u.get("co_tieu_tu", False),
                        "luot": luot,
                    })
            finally:
                for duoi in (".wav", ".txt", ".speed"):
                    (VOICES_DIR / f"{giong}{duoi}").unlink(missing_ok=True)
                app_state.tts.drop_voice(giong)

        (PHAN_TICH_DIR / f"{ten}.nghe.json").write_text(
            json.dumps({"muc": muc, "so_bien": len(thoai),
                        "so_ung_vien": len(uv)}, ensure_ascii=False),
            encoding="utf-8")
        viec.update(trang_thai="xong", tien=100, so_tep=len(muc))
        logger.info("Nghe hàng loạt %s: %d tệp (%d ứng viên x %d bộ)",
                    ten, len(muc), len(uv), len(thoai))
    except Exception as e:
        logger.exception("Nghe hàng loạt %s hỏng", ten)
        viec.update(trang_thai="hong", loi=str(e))


@router.post("/nguon/{ten}/nghe-loat")
async def bat_nghe_loat(ten: str, tong: int = NGHE_LOAT_MAC_DINH, so_luot: int = 3):
    import asyncio

    ten = _ten_sach(ten)
    if not (PHAN_TICH_DIR / f"{ten}.json").exists():
        return {"error": "Chạy Phân tích trước đã"}
    khoa = f"nghe:{ten}"
    if (_VIEC.get(khoa) or {}).get("trang_thai") == "dang_chay":
        return {"trang_thai": "dang_chay", "tien": _VIEC[khoa].get("tien", 0)}
    _VIEC[khoa] = {"trang_thai": "dang_chay", "tien": 0}
    asyncio.create_task(_nghe_hang_loat(ten, max(1, min(int(tong), 400)),
                                        max(2, min(int(so_luot), 6))))
    return {"trang_thai": "dang_chay", "tien": 0}


@router.get("/nguon/{ten}/nghe-loat")
async def xem_nghe_loat(ten: str):
    import json

    ten = _ten_sach(ten)
    viec = _VIEC.get(f"nghe:{ten}")
    if viec and viec.get("trang_thai") == "dang_chay":
        return {"trang_thai": "dang_chay", "tien": viec.get("tien", 0),
                "xong": viec.get("xong", 0), "tong": viec.get("tong", 0)}
    if viec and viec.get("trang_thai") == "hong":
        return {"trang_thai": "hong", "error": viec.get("loi", "")}
    j = PHAN_TICH_DIR / f"{ten}.nghe.json"
    if not j.exists():
        return {"trang_thai": "chua"}
    return {"trang_thai": "xong", "tien": 100,
            **json.loads(j.read_text(encoding="utf-8"))}


@router.get("/nguon/{ten}/nghe/{tep}")
async def nghe_tep_loat(ten: str, tep: str):
    p = PHAN_TICH_DIR / _ten_sach(ten) / "nghe" / _ten_sach(tep.replace(".wav", "")) 
    p = p.with_suffix(".wav")
    if not p.exists():
        return {"error": "Không có tệp này"}
    return FileResponse(str(p), media_type="audio/wav")
