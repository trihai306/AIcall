"""Dựng nguyên một cuộc hội thoại thành file tiếng, để vừa nghe vừa đọc.

Khác `goi_doc_kich_ban.py` ở chỗ quan trọng nhất: câu trả lời KHÔNG viết sẵn mà
do CHÍNH pipeline sinh ra - tra tài liệu bằng RAG rồi để LLM soạn, cắt mảnh và
chặn số y như trong cuộc gọi thật. Nhờ vậy nghe được AI thực sự trả lời thế nào
chứ không phải nghe một kịch bản đã dàn dựng sẵn.

Hai giọng để phân biệt người nói: khách một giọng, AI giọng đang chạy thật.

Ba file ra:
  1_hoi_thoai_24kHz.wav   - bản gốc, nghe rõ từng chữ
  2_qua_dien_thoai.wav    - đúng thứ khách nghe (8kHz + AMR-NB của nhà mạng)
  ban_chu.txt             - bản chữ

    python scripts/dung_hoi_thoai_mau.py
    python scripts/dung_hoi_thoai_mau.py --san-pham "vay mua nhà"

Đặt CUDA_VISIBLE_DEVICES= (rỗng) để chạy CPU khi GPU đang bận việc khác.
"""

import argparse
import asyncio
import io
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RA = PROJECT / "logs" / "hoi_thoai"

# Câu khách nói - viết như người thật nói qua điện thoại: cụt, có từ đệm, không
# phải câu hỏi sách vở. Đây là phần DUY NHẤT được viết sẵn.
KHACH = [
    "Alo ai đấy",
    "Ừ em nói đi",
    "Lãi suất bao nhiêu em",
    "Thế vay được nhiều nhất là bao nhiêu",
    "Cần giấy tờ gì không",
    "Bao lâu thì có tiền",
    "Ừ để anh xem đã nhé",
]

# Câu mở đầu cố định của tổng đài, giống hệt lúc gọi thật.
LOI_CHAO = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng ABC, "
            "em gọi để giới thiệu chương trình vay ưu đãi ạ.")


def doc_wav_bytes(b: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(b)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return x.astype(np.float32) / 32768.0, w.getframerate()


def ghi_wav(p: Path, x: np.ndarray, sr: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--san-pham", default="vay tín chấp")
    ap.add_argument("--giong-khach", default="giong_ngan")
    a = ap.parse_args()

    from backend.config import settings
    from backend.core.device import DEVICE
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.text_chunker import nhip_nghi_sau, should_flush
    from backend.pipeline.text_normalizer import BotLichSu, chan_so_sai
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import chen_lang_dau_wav, resample_audio
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    print(f"\n  máy chạy: {DEVICE} | model: {settings.ollama_model}")
    tts = F5TTSService()
    tts.load()
    llm, rag = LLMService(), RAGService()
    rag.load()

    giong_ai = await tts.ensure_voice(Path(settings.f5tts_ref_audio).stem)
    giong_khach = await tts.ensure_voice(a.giong_khach)
    print(f"  giọng AI: {giong_ai} | giọng khách: {giong_khach}")
    print(f"  sản phẩm: {a.san_pham}\n")

    session = CallSession(customer_name="Anh Nam", product=a.san_pham)
    manh: list[np.ndarray] = []
    ban_chu: list[tuple[str, str]] = []
    SR = 24000

    def them(wav: bytes):
        x, sr = doc_wav_bytes(wav)
        assert sr == SR, f"tần số lạ: {sr}"
        manh.append(x)

    def nghi(giay: float):
        manh.append(np.zeros(int(giay * SR), dtype=np.float32))

    # ---- lời chào mở đầu ----------------------------------------------------
    print(f"  AI    | {LOI_CHAO}")
    them(await tts.synthesize(LOI_CHAO, voice=giong_ai, use_cache=False))
    nghi(0.5)
    ban_chu.append(("AI", LOI_CHAO))
    session.history.append({"role": "assistant", "content": LOI_CHAO})

    for cau in KHACH:
        print(f"  KHÁCH | {cau}")
        them(await tts.synthesize(cau, voice=giong_khach, use_cache=False))
        nghi(0.35)
        ban_chu.append(("KHÁCH", cau))

        # ---- ĐÚNG đường của cuộc gọi thật -----------------------------------
        # RAG neo theo sản phẩm (không neo thì "lãi suất bao nhiêu" kéo về tài
        # liệu sản phẩm khác), rồi LLM, rồi cắt mảnh, rồi chặn số.
        ctx = ""
        try:
            ctx = await rag.retrieve(f"{a.san_pham} {cau}", top_k=2,
                                     san_pham=a.san_pham)
        except Exception as e:
            print(f"        (RAG lỗi: {e})")
        system = llm.build_system_prompt(customer_name=session.customer_name,
                                         product=session.product, rag_context=ctx)
        session.history.append({"role": "user", "content": cau})

        buf, dap, cac_manh, nghi_no = "", "", [], 0.0
        t0 = time.perf_counter()
        # Xen kẽ bỏ "Dạ" mở đầu, như pipeline. Ở đây không có filler nên chỉ dựa
        # vào số thứ tự lượt.
        bot_lich_su = BotLichSu(bo_da=(len(ban_chu) // 2) % 2 == 0)

        async def phat(doan: str):
            """Cắt mảnh -> chặn số -> bớt "ạ" -> tổng hợp, giống `tts_consumer`."""
            nonlocal nghi_no
            sach, sua = chan_so_sai(doan, ctx)
            if sua:
                print(f"        [chặn số sai: {sua}]")
            sach = bot_lich_su(sach)
            # Quãng nghỉ đi kèm mảnh: chỗ ngắt câu có thể nằm ở chữ "ạ" đầu mảnh
            # vừa bị bỏ, lúc đó mảnh trước không còn dấu câu để nhìn ra.
            nghi_no += bot_lich_su.nghi_truoc_ms
            if not sach:
                return
            dau = len(cac_manh) == 0
            w = await tts.synthesize(sach, fast=dau, voice=giong_ai, use_cache=False)
            # Trả lại nhịp nghỉ mà trim_silence cắt mất ở ranh giới mảnh. Chèn
            # vào ĐẦU mảnh này nên mảnh đầu không bị chèn, mảnh cuối không thừa.
            if cac_manh and nghi_no > 0:
                w = chen_lang_dau_wav(w, nghi_no)
            # Bản chữ: chỉ thêm dấu chấm ở chỗ NGẮT THẬT (nơi "ạ." vừa bị bỏ),
            # đừng thêm ở mọi ranh giới mảnh - bộ cắt mảnh cắt giữa câu, thêm
            # bừa thì bản chữ hiện "giờ sau. khi phê duyệt", sai với tiếng phát.
            if cac_manh and nghi_no > 0 and cac_manh[-1][-1] not in ".,!?;:":
                cac_manh[-1] += "."
            cac_manh.append(sach)
            nghi_no = nhip_nghi_sau(sach)
            them(w)

        async for token in llm.stream_response(session.history, system):
            buf += token
            dap += token
            if should_flush(buf, first_chunk=not cac_manh):
                doan, buf = buf.strip(), ""
                if doan:
                    await phat(doan)
        if buf.strip():
            await phat(buf.strip())

        # Ghép lại từ CÁC MẢNH ĐÃ ĐỌC (không phải chuỗi token thô) để bản chữ
        # đúng bằng thứ phát ra tiếng, kể cả khi chặn số đã sửa. Bỏ khoảng trắng
        # thừa trước dấu câu do ghép mảnh sinh ra.
        dap = re.sub(r"([.,!?;:])\1+", r"\1",
                     re.sub(r"\s+([.,!?;:])", r"\1", " ".join(cac_manh)))
        session.history.append({"role": "assistant", "content": dap})
        nghi(0.5)
        ban_chu.append(("AI", dap))
        print(f"  AI    | {dap}")
        print(f"        ({len(cac_manh)} mảnh, {time.perf_counter()-t0:.1f}s)\n")

    # ---- ghi ra --------------------------------------------------------------
    day = np.concatenate(manh)
    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*"):
        f.unlink()
    ghi_wav(RA / "1_hoi_thoai_24kHz.wav", day, SR)

    # Đúng thứ khách nghe: chuẩn mức -> hạ 8kHz -> tăng tuần hoàn -> bộ mã mạng.
    a8 = resample_audio(PS.chuan_muc_thoai(day), SR, 8000)
    if settings.phone_tang_tuan_hoan:
        a8 = PS.tang_tuan_hoan(a8, 8000)
    qua_amr, duong = lay_bo_ma_amr()
    ghi_wav(RA / "2_qua_dien_thoai.wav", qua_amr(a8), 8000)

    (RA / "ban_chu.txt").write_text(
        "\n".join(f"{ai:<6}| {t}" for ai, t in ban_chu), encoding="utf-8")

    print(f"  Dài {len(day)/SR:.1f}s, {len(ban_chu)} lượt | AMR qua {duong}")
    print(f"  {RA}")
    return 0


if __name__ == "__main__":
    if os.environ.get("CUDA_VISIBLE_DEVICES") == "":
        print("  (ép chạy CPU)")
    raise SystemExit(asyncio.run(main()))
