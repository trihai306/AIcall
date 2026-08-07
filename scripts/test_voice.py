"""Chấm điểm một giọng TTS: đọc có đúng chữ không, nhanh chậm ra sao.

Cách chấm: sinh audio -> đưa ngược qua PhoWhisper -> so với câu gốc. Nếu người
nghe hiểu được thì máy nhận dạng cũng đọc ra được; sai chữ nào là TTS phát âm
lệch chữ đó. Không thay được tai người nhưng bắt được lỗi rõ ràng và lặp lại
được, khác với nghe thủ công vài câu rồi kết luận.

Mỗi câu chạy nhiều lượt vì F5-TTS là mô hình khuếch tán - cùng một câu mỗi lần
sinh một khác. Từng đo được một mẫu nghe rất chuẩn nhưng chạy 10 lượt thì hỏng 7.

    python scripts/test_voice.py
    python scripts/test_voice.py --runs 5 --ref models/tts/ref_voices/giong_moi.wav
    python scripts/test_voice.py --ckpt models/tts/finetuned/giong_moi/model_last.pt \
                                 --vocab models/tts/finetuned/giong_moi/vocab.txt

Audio sinh ra nằm ở logs/test_voice/ để nghe lại bằng tai.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent

# Câu test lấy từ nội dung tổng đài thật, không phải câu đẹp chọn lọc.
# Mỗi câu nhắm một điểm yếu đã đo được.
CAU_TEST = [
    ("da_mo_dau",   "Dạ em chào anh chị ạ."),
    ("da_giua_cau", "Dạ vâng em hiểu rồi ạ."),
    ("da_dai",      "Dạ anh cho em xin số điện thoại để em kiểm tra giúp anh ạ."),
    ("so_dien",     "Dạ số của mình là không chín tám bốn hai một ba năm sáu bảy ạ."),
    ("thuat_ngu",   "Dạ mình cần căn cước công dân và giấy phép lái xe ạ."),
    ("cau_dai",     "Dạ bên em có xe số và xe tay ga, anh muốn thuê loại nào để em báo giá ạ."),
    ("hoi_lai",     "Dạ anh cho em hỏi mình thuê trong bao nhiêu ngày ạ."),
    ("cam_on",      "Dạ em cảm ơn anh nhiều ạ, chúc anh một ngày tốt lành."),
]


def chuan_hoa(s: str) -> str:
    """Bỏ dấu câu, gộp khoảng trắng, về chữ thường - so nội dung chứ không so chính tả."""
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(goc: str, nhan: str) -> float:
    """Tỉ lệ ký tự sai (Levenshtein / độ dài gốc)."""
    a, b = chuan_hoa(goc), chuan_hoa(nhan)
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sau = [i]
        for j, cb in enumerate(b, 1):
            sau.append(min(truoc[j] + 1, sau[j - 1] + 1, truoc[j - 1] + (ca != cb)))
        truoc = sau
    return truoc[-1] / len(a)


def main() -> int:
    import requests


    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="Số lượt sinh cho mỗi câu")
    ap.add_argument("--ref", default=None, help="File giọng mẫu (mặc định lấy từ .env)")
    ap.add_argument("--ckpt", default=None, help="Checkpoint F5-TTS cần chấm")
    ap.add_argument("--vocab", default=None)
    ap.add_argument("--nfe", type=int, default=None, help="Số bước khuếch tán")
    ap.add_argument("--fast", action="store_true",
                    help="Chấm đường fast=True (mảnh ĐẦU của mỗi câu trả lời "
                         "đi đường này) - dùng f5tts_nfe_step_first")
    ap.add_argument("--stt", default="http://localhost:8178")
    ap.add_argument("--out", default=str(PROJECT / "logs" / "test_voice"))
    ap.add_argument("--nguong", type=float, default=0.10,
                    help="CER tối đa còn coi là đạt")
    args = ap.parse_args()

    sys.path.insert(0, str(PROJECT))
    from backend.config import settings

    if args.ckpt:
        settings.f5tts_ckpt_path = args.ckpt
    if args.vocab:
        settings.f5tts_vocab_path = args.vocab
    if args.ref:
        settings.f5tts_ref_audio = args.ref
    if args.nfe:
        settings.f5tts_nfe_step = args.nfe

    print("Giọng đang chấm:")
    print(f"  checkpoint : {settings.f5tts_ckpt_path}")
    print(f"  giọng mẫu  : {settings.f5tts_ref_audio}")
    nfe_dung = settings.f5tts_nfe_step_first if args.fast else settings.f5tts_nfe_step
    print(f"  đường      : {'fast (mảnh đầu)' if args.fast else 'thường'}")
    print(f"  nfe_step   : {nfe_dung}")
    print(f"  {len(CAU_TEST)} câu x {args.runs} lượt = {len(CAU_TEST)*args.runs} mẫu\n")

    import asyncio

    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    loop = asyncio.new_event_loop()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.wav"):
        f.unlink()

    # requests.Session: không dùng thì mỗi lượt phải bắt tay TCP lại, đo lệch
    # hơn 2 giây và tưởng nhầm là STT chậm.
    sess = requests.Session()

    ket_qua = []
    print(f"{'câu':<14} {'lượt':<5} {'ms':>6} {'CER':>7}  nhận dạng được")
    print("-" * 92)

    for ten, cau in CAU_TEST:
        for lan in range(1, args.runs + 1):
            # use_cache=False: lượt 2 và 3 mà lấy lại bản đã lưu thì đo được
            # 0ms và CER giống hệt lượt 1 - mất sạch ý nghĩa của việc chạy nhiều lượt.
            t0 = time.perf_counter()
            wav_bytes = loop.run_until_complete(
                tts.synthesize(cau, use_cache=False, fast=args.fast)
            )
            ms = (time.perf_counter() - t0) * 1000

            wav = out_dir / f"{ten}_{lan}.wav"
            wav.write_bytes(wav_bytes)

            try:
                r = sess.post(f"{args.stt}/inference",
                              files={"file": (wav.name, wav.read_bytes(), "audio/wav")},
                              data={"language": "vi", "response_format": "json",
                                    "temperature": "0"},
                              timeout=60)
                nhan = r.json().get("text", "").strip()
            except Exception as e:
                nhan = f"[STT lỗi: {e}]"

            e = cer(cau, nhan)
            dat = "OK " if e <= args.nguong else "SAI"
            ket_qua.append({"ten": ten, "cau": cau, "lan": lan, "ms": ms,
                            "cer": e, "nhan": nhan, "dat": e <= args.nguong})
            print(f"{ten:<14} {lan}/{args.runs:<3} {ms:6.0f} {e*100:6.1f}% {dat} {nhan[:52]}")

    print("-" * 92)

    tong = len(ket_qua)
    dat = sum(1 for k in ket_qua if k["dat"])
    cer_tb = sum(k["cer"] for k in ket_qua) / tong
    ms_tb = sum(k["ms"] for k in ket_qua) / tong

    print(f"\nĐạt {dat}/{tong} mẫu ({dat/tong*100:.0f}%) | "
          f"CER trung bình {cer_tb*100:.1f}% | {ms_tb:.0f} ms/câu")

    # Chữ "Dạ": mọi câu test đều mở đầu bằng nó, nên tách riêng để theo dõi.
    sai_da = [k for k in ket_qua
              if not chuan_hoa(k["nhan"]).startswith("dạ")]
    print(f"Chữ \"Dạ\" ở đầu câu: sai {len(sai_da)}/{tong} lượt "
          f"({len(sai_da)/tong*100:.0f}%)")
    if sai_da:
        thay = {}
        for k in sai_da:
            tu = chuan_hoa(k["nhan"]).split()
            thay[tu[0] if tu else "(trống)"] = thay.get(tu[0] if tu else "(trống)", 0) + 1
        print("  bị nghe thành:", ", ".join(f"{t} x{n}" for t, n in
                                            sorted(thay.items(), key=lambda x: -x[1])))

    xau = sorted(ket_qua, key=lambda k: -k["cer"])[:3]
    if xau and xau[0]["cer"] > args.nguong:
        print("\nSai nhiều nhất:")
        for k in xau:
            if k["cer"] <= args.nguong:
                continue
            print(f"  [{k['cer']*100:.0f}%] {k['cau']}")
            print(f"         nghe ra: {k['nhan']}")

    bao_cao = out_dir / "ket_qua.json"
    bao_cao.write_text(json.dumps({
        "checkpoint": str(settings.f5tts_ckpt_path),
        "ref_audio": str(settings.f5tts_ref_audio),
        "nfe_step": nfe_dung,
        "fast": args.fast,
        "runs": args.runs,
        "dat": dat, "tong": tong,
        "cer_tb": cer_tb, "ms_tb": ms_tb,
        "sai_da": len(sai_da),
        "chi_tiet": ket_qua,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nAudio để nghe lại: {out_dir}")
    print(f"Số liệu:           {bao_cao}")
    print("\nCER là thước đo máy, không thay tai người. Nghe vài file trong")
    print("thư mục trên để xét ngữ điệu - cái đó CER không đo được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
