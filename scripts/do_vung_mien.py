#!/usr/bin/env python3
"""Đo độ chính xác nhận dạng theo VÙNG MIỀN (Điều 6: "nhận diện giọng vùng miền").

Chạy mẫu thu qua ĐÚNG đường xử lý thật (`STTService.transcribe`, có mồi từ vựng,
có bộ lọc câu đáng ngờ) chứ không gọi thẳng Whisper. Đo ở đường tắt thì con số
đẹp hơn thực tế và không nói lên điều gì về cuộc gọi thật.

CHUẨN BỊ MẪU
    data/test_vung_mien/
        bac/    001.wav  001.txt   (001.txt là lời NÓI ĐÚNG của 001.wav)
                002.wav  002.txt
        trung/  ...
        nam/    ...

    Mỗi vùng nên có ít nhất 20 câu. Quan trọng: mẫu phải là tiếng ĐI QUA ĐƯỜNG
    ĐIỆN THOẠI (8kHz, đã qua bộ mã của mạng), không phải file thu phòng sạch —
    đo trên tiếng sạch thì WER thấp giả tạo, mà hệ thống này chỉ nghe tiếng
    điện thoại.

    Không có sẵn mẫu điện thoại thì dùng --gia-lap-thoai để ép file thu sạch
    xuống 8kHz trước khi đo. Vẫn không thay được mẫu thật (thiếu nhiễu nền và
    méo của bộ mã) nhưng gần hơn nhiều so với đo trên file gốc.

CHẠY
    python scripts/do_vung_mien.py
    python scripts/do_vung_mien.py --vung nam --moi nam
    python scripts/do_vung_mien.py --so-sanh-moi     # đo cả có mồi lẫn không

TIÊU CHÍ NGHIỆM THU (theo tài liệu đặc tả)
    WER mỗi vùng <= 15%, chênh lệch giữa vùng tốt nhất và tệ nhất <= 5 điểm.
"""

import argparse
import asyncio
import re
import sys
import unicodedata
import wave
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from backend.services import stt_service as ss           # noqa: E402
from backend.services.audio_utils import (               # noqa: E402
    float32_to_int16, int16_to_float32, resample_lien_tuc,
)

THU_MUC = GOC / "data" / "test_vung_mien"
VUNG = ("bac", "trung", "nam")
TEN_VUNG = {"bac": "Miền Bắc", "trung": "Miền Trung", "nam": "Miền Nam"}


def chuan_hoa(s: str) -> str:
    """Bỏ dấu câu và khoảng trắng thừa. GIỮ NGUYÊN dấu thanh.

    Bỏ dấu thanh khi chấm là tự cho điểm cao: "hạn mức" và "hãng mực" sẽ thành
    ngang nhau, mà đó đúng là loại lỗi vùng miền cần đo.
    """
    s = unicodedata.normalize("NFC", (s or "").lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def wer(chuan: str, doc_ra: str) -> tuple[float, int, int]:
    """Word Error Rate bằng khoảng cách Levenshtein trên TỪ.

    Trả về (wer, số lỗi, số từ chuẩn).
    """
    a, b = chuan_hoa(chuan).split(), chuan_hoa(doc_ra).split()
    if not a:
        return (0.0, 0, 0) if not b else (1.0, len(b), 0)

    truoc = list(range(len(b) + 1))
    for i, ta in enumerate(a, 1):
        hien = [i]
        for j, tb in enumerate(b, 1):
            hien.append(min(
                truoc[j] + 1,                                # xoá
                hien[j - 1] + 1,                             # chèn
                truoc[j - 1] + (ta != tb),                   # thay
            ))
        truoc = hien
    return truoc[-1] / len(a), truoc[-1], len(a)


def doc_wav(p: Path, gia_lap_thoai: bool) -> tuple[bytes, int]:
    with wave.open(str(p), "rb") as w:
        sr = w.getframerate()
        n_kenh = w.getnchannels()
        pcm = w.readframes(w.getnframes())

    x = int16_to_float32(pcm)
    if n_kenh > 1:
        x = x.reshape(-1, n_kenh).mean(axis=1)

    if gia_lap_thoai and sr > 8000:
        # Xuống 8k rồi lên lại 16k: mô phỏng việc kênh thoại cắt mất mọi thứ
        # trên 4kHz. Đây là phần lớn cái làm nhận dạng khó hơn.
        x = resample_lien_tuc(x, sr, 8000)
        sr = 8000

    if sr != 16000:
        x = resample_lien_tuc(x, sr, 16000)
        sr = 16000
    return float32_to_int16(x), sr


async def do_mot_vung(stt, vung: str, gia_lap_thoai: bool) -> dict:
    thu_muc = THU_MUC / vung
    if not thu_muc.exists():
        return {"vung": vung, "so_mau": 0, "thieu": str(thu_muc)}

    tong_loi = tong_tu = 0
    mat_trang = 0
    chi_tiet = []
    for wav in sorted(thu_muc.glob("*.wav")):
        txt = wav.with_suffix(".txt")
        if not txt.exists():
            continue
        chuan = txt.read_text(encoding="utf-8").strip()
        pcm, sr = doc_wav(wav, gia_lap_thoai)
        doc_ra = await stt.transcribe(pcm, sample_rate=sr)

        w, loi, so_tu = wer(chuan, doc_ra)
        tong_loi += loi
        tong_tu += so_tu
        if not doc_ra.strip():
            # Lượt bị bộ lọc "câu đáng ngờ" vứt. Đếm riêng: mất trắng cả lượt
            # khó chịu hơn nhiều so với nghe sai vài từ, và hai lỗi này cần cách
            # chữa khác nhau.
            mat_trang += 1
        chi_tiet.append({"tep": wav.name, "wer": w, "chuan": chuan, "doc_ra": doc_ra})

    return {
        "vung": vung,
        "so_mau": len(chi_tiet),
        "wer": (tong_loi / tong_tu) if tong_tu else 0.0,
        "so_loi": tong_loi,
        "so_tu": tong_tu,
        "mat_trang": mat_trang,
        "chi_tiet": chi_tiet,
    }


def in_bang(ket_qua: list[dict], nhan: str = ""):
    print(f"\n{'=' * 66}")
    print(f"KẾT QUẢ{(' — ' + nhan) if nhan else ''}")
    print("=" * 66)
    print(f"{'Vùng':12s} {'Mẫu':>5s} {'WER':>8s} {'Lỗi/Từ':>12s} {'Mất trắng':>10s}")
    print("-" * 66)

    co_so = [r for r in ket_qua if r.get("so_mau")]
    for r in ket_qua:
        if not r.get("so_mau"):
            print(f"{TEN_VUNG.get(r['vung'], r['vung']):12s} {'—':>5s}   "
                  f"chưa có mẫu ({r.get('thieu', '')})")
            continue
        print(f"{TEN_VUNG.get(r['vung'], r['vung']):12s} {r['so_mau']:5d} "
              f"{r['wer'] * 100:7.1f}% {r['so_loi']:5d}/{r['so_tu']:<6d} "
              f"{r['mat_trang']:10d}")

    if not co_so:
        print("\nChưa có mẫu nào. Xem phần CHUẨN BỊ MẪU ở đầu file này.")
        return

    print("-" * 66)
    wers = [r["wer"] for r in co_so]
    chenh = (max(wers) - min(wers)) * 100
    print(f"Cao nhất {max(wers) * 100:.1f}%  ·  thấp nhất {min(wers) * 100:.1f}%  "
          f"·  chênh lệch {chenh:.1f} điểm")

    dat_wer = all(w <= 0.15 for w in wers)
    dat_chenh = chenh <= 5.0
    print(f"\nTiêu chí nghiệm thu:")
    print(f"  WER mỗi vùng <= 15%           : {'ĐẠT' if dat_wer else 'CHƯA ĐẠT'}")
    print(f"  Chênh lệch giữa các vùng <= 5 : {'ĐẠT' if dat_chenh else 'CHƯA ĐẠT'}")
    if len(co_so) < len(VUNG):
        print(f"  (mới đo {len(co_so)}/{len(VUNG)} vùng — chưa đủ để nghiệm thu)")


def in_cau_te(ket_qua: list[dict], so: int = 5):
    for r in ket_qua:
        if not r.get("chi_tiet"):
            continue
        te = sorted(r["chi_tiet"], key=lambda x: -x["wer"])[:so]
        if not te or te[0]["wer"] == 0:
            continue
        print(f"\n{TEN_VUNG.get(r['vung'], r['vung'])} — {so} câu sai nhiều nhất:")
        for c in te:
            print(f"  [{c['wer'] * 100:5.1f}%] {c['tep']}")
            print(f"      đúng : {c['chuan']}")
            print(f"      nghe : {c['doc_ra'] or '(BỊ VỨT — mất trắng lượt)'}")


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vung", choices=VUNG, help="chỉ đo một vùng")
    ap.add_argument("--moi", choices=["", *VUNG], default=None,
                    help="ép dùng mồi của vùng này (mặc định: theo .env)")
    ap.add_argument("--so-sanh-moi", action="store_true",
                    help="đo hai lần: không mồi vùng miền và có mồi, để biết mồi có ăn thua")
    ap.add_argument("--gia-lap-thoai", action="store_true",
                    help="ép mẫu xuống 8kHz trước khi đo (dùng khi chỉ có file thu sạch)")
    ap.add_argument("--chi-tiet", action="store_true", help="in các câu sai nhiều nhất")
    args = ap.parse_args()

    from backend.config import settings

    stt = ss.STTService()
    if not await stt.health_check():
        print(f"Máy chủ Whisper không chạy ở {settings.whisper_server_url}")
        print("Chạy trước: bash whisper_server/start.sh")
        return 1

    can_do = [args.vung] if args.vung else list(VUNG)

    async def chay(moi_vung: str, nhan: str):
        settings.stt_vung_mien = moi_vung
        ket_qua = [await do_mot_vung(stt, v, args.gia_lap_thoai) for v in can_do]
        in_bang(ket_qua, nhan)
        if args.chi_tiet:
            in_cau_te(ket_qua)
        return ket_qua

    if args.so_sanh_moi:
        await chay("", "KHÔNG mồi vùng miền")
        for v in can_do:
            settings.stt_vung_mien = v
            r = await do_mot_vung(stt, v, args.gia_lap_thoai)
            if r.get("so_mau"):
                print(f"\n{TEN_VUNG[v]} có mồi '{v}': WER {r['wer'] * 100:.1f}% "
                      f"(mất trắng {r['mat_trang']})")
    else:
        await chay(settings.stt_vung_mien if args.moi is None else args.moi,
                   f"mồi = '{args.moi if args.moi is not None else settings.stt_vung_mien}'")

    await stt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
