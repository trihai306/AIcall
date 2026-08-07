"""Lấy bản ghi TIẾNG THẬT của khách trong cuộc gọi, cho chạy hết đường xử lý.

Khác `dung_hoi_thoai_mau.py` ở chỗ quyết định: câu khách KHÔNG do F5 đọc ra mà là
tiếng người thật, đã đi qua micro điện thoại, mạng GSM và bộ mã AMR-NB. Nhờ vậy
thấy được đúng thứ máy phải đối mặt: nhiễu kênh, méo, chữ bị nuốt.

Chạy đúng chuỗi của cuộc gọi thật:

    bản ghi 8kHz -> cắt lượt bằng VAD -> nâng 16kHz -> STT
                 -> RAG (neo theo sản phẩm) -> LLM -> chặn số -> bớt "ạ" -> F5

Ghép lại thành một file: tiếng khách THẬT xen với tiếng AI trả lời.

    python scripts/xu_ly_tieng_that.py
    python scripts/xu_ly_tieng_that.py --file logs/tieng_khach/khach.wav
"""

import argparse
import asyncio
import io
import re
import sys
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

RA = PROJECT / "logs" / "tieng_that"
SR = 24000          # tần số của file ghép ra


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
    ap.add_argument("--file", default=str(PROJECT / "logs/tieng_khach/khach_nói.wav"))
    ap.add_argument("--san-pham", default="vay tín chấp")
    a = ap.parse_args()

    from soi_tung_luot import cat_luot          # đúng logic VAD của `_read_loop`

    from backend.config import settings
    from backend.pipeline.luot_thuong_gap import tra_loi_san
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.text_chunker import nhip_nghi_sau, should_flush
    from backend.pipeline.text_normalizer import BotLichSu, chan_so_sai
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import (chen_lang_dau_wav, resample_audio,
                                              resample_lien_tuc)
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    f = Path(a.file)
    if not f.exists():
        alt = sorted(f.parent.glob("*.wav"))
        if not alt:
            print(f"  không thấy file: {f}")
            return 1
        f = alt[-1]
    with wave.open(str(f)) as w:
        sr_goc = w.getframerate()
        goc = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
               .astype(np.float32) / 32768.0)

    luot, nen, nguong = cat_luot(goc, sr_goc, PS)
    print(f"\n  {f.name}: {len(goc)/sr_goc:.1f}s @ {sr_goc}Hz")
    print(f"  nền kênh {nen:.0f} -> ngưỡng VAD {nguong:.0f} | cắt được {len(luot)} lượt")

    tts = F5TTSService(); tts.load()
    stt, llm, rag = STTService(), LLMService(), RAGService()
    rag.load()
    giong_ai = await tts.ensure_voice(Path(settings.f5tts_ref_audio).stem)
    print(f"  model {settings.ollama_model} | giọng {giong_ai} | sản phẩm {a.san_pham}\n")

    session = CallSession(customer_name="Anh Nam", product=a.san_pham)
    manh: list[np.ndarray] = []
    ban_chu: list[tuple[str, str]] = []

    def them_wav(wav: bytes):
        x, s = doc_wav_bytes(wav)
        manh.append(x if s == SR else resample_lien_tuc(x, s, SR))

    for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
        seg = goc[bd:kt]
        # Tiếng khách THẬT, đưa nguyên vào bản ghép (chỉ nâng tần cho khớp file).
        manh.append(resample_lien_tuc(seg, sr_goc, SR))
        manh.append(np.zeros(int(0.30 * SR), dtype=np.float32))

        if not du_dai:
            print(f"  [{i}] BỎ - lượt ngắn hơn MIN_TURN_MS ({talk}ms)")
            ban_chu.append(("BỎ", f"lượt {i}: ngắn {talk}ms"))
            continue

        pcm16 = resample_lien_tuc(seg, sr_goc, 16000)
        pcm = (np.clip(pcm16, -1, 1) * 32767).astype("<i2").tobytes()
        nghe = (await stt.transcribe(pcm)).strip()
        if not nghe:
            print(f"  [{i}] BỎ - STT không nhận ra ({talk}ms)")
            ban_chu.append(("BỎ", f"lượt {i}: STT không nhận ra"))
            continue

        print(f"  KHÁCH | {nghe}   ({talk}ms tiếng thật)")
        ban_chu.append(("KHÁCH", nghe))

        # Lượt thường gặp trả lời bằng bảng có sẵn, không qua mô hình.
        dap_san = tra_loi_san(nghe, bank=settings.bank_name,
                              agent=settings.agent_name, product=a.san_pham,
                              luot_thu=len([1 for k, _ in ban_chu if k == "AI"]))
        ctx = ""
        if not dap_san:
            try:
                ctx = await rag.retrieve(f"{a.san_pham} {nghe}", top_k=2,
                                         san_pham=a.san_pham)
            except Exception as e:
                print(f"        (RAG lỗi: {e})")
        system = llm.build_system_prompt(customer_name=session.customer_name,
                                         product=session.product, rag_context=ctx)
        session.history.append({"role": "user", "content": nghe})

        buf, cac_manh, nghi_no = "", [], 0.0
        bot_lich_su = BotLichSu(bo_da=(i % 2 == 0))

        async def phat(doan: str):
            nonlocal nghi_no
            sach, sua = chan_so_sai(doan, ctx)
            if sua:
                print(f"        [chặn số sai: {sua}]")
            sach = bot_lich_su(sach)
            nghi_no += bot_lich_su.nghi_truoc_ms
            if not sach:
                return
            w = await tts.synthesize(sach, fast=not cac_manh, voice=giong_ai,
                                     use_cache=False)
            if cac_manh and nghi_no > 0:
                w = chen_lang_dau_wav(w, nghi_no)
                if cac_manh[-1][-1] not in ".,!?;:":
                    cac_manh[-1] += "."
            cac_manh.append(sach)
            nghi_no = nhip_nghi_sau(sach)
            them_wav(w)

        if dap_san:
            print(f"        [lượt thường gặp: {dap_san[0]} - trả lời sẵn, "
                  f"không qua mô hình]")

            async def nguon():
                for k, tu in enumerate(dap_san[1].split(" ")):
                    yield (" " + tu) if k else tu
        else:
            nguon = lambda: llm.stream_response(session.history, system)  # noqa: E731

        async for token in nguon():
            buf += token
            if should_flush(buf, first_chunk=not cac_manh):
                doan, buf = buf.strip(), ""
                if doan:
                    await phat(doan)
        if buf.strip():
            await phat(buf.strip())

        dap = re.sub(r"([.,!?;:])\1+", r"\1",
                     re.sub(r"\s+([.,!?;:])", r"\1", " ".join(cac_manh)))
        session.history.append({"role": "assistant", "content": dap})
        ban_chu.append(("AI", dap))
        print(f"  AI    | {dap}\n")
        manh.append(np.zeros(int(0.45 * SR), dtype=np.float32))

    day = np.concatenate(manh)
    RA.mkdir(parents=True, exist_ok=True)
    for x in RA.glob("*"):
        x.unlink()
    ghi_wav(RA / "1_hoi_thoai_that.wav", day, SR)

    a8 = resample_audio(PS.chuan_muc_thoai(day), SR, 8000)
    if settings.phone_tang_tuan_hoan:
        a8 = PS.tang_tuan_hoan(a8, 8000)
    qua_amr, _ = lay_bo_ma_amr()
    ghi_wav(RA / "2_qua_dien_thoai.wav", qua_amr(a8), 8000)

    (RA / "ban_chu.txt").write_text(
        "\n".join(f"{ai:<6}| {t}" for ai, t in ban_chu), encoding="utf-8")

    n_khach = sum(1 for k, _ in ban_chu if k == "KHÁCH")
    print(f"  Dài {len(day)/SR:.1f}s | {n_khach}/{len(luot)} lượt khách được trả lời")
    print(f"  {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
