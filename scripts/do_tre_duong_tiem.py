"""Đo: sau khi máy bên kia NHẤC MÁY, bao lâu thì tiếng AI mới tới tai họ - và lúc đó
trên máy AI cái gì thay đổi (luồng PCM nào đang chạy, control mixer, trạng thái cuộc gọi).

CÓ CƯỚC: máy AI (Viettel) gọi sang máy khách của phone farm (Vinaphone), mỗi lần
chạy là một cuộc gọi ngoại mạng dài NOI_S giây. Hỏi người dùng trước khi chạy.

Máy AI gọi qua ĐÚNG đường sản phẩm, script không đụng gì tới máy AI trước khi nối
máy. Sau khi máy khách nhấc máy:
  - máy khách mở cầu tiếng để THU cái nó nghe được (đây là sự thật ở tai khách;
    tiếng AI lọt lại vào kênh thu của máy AI KHÔNG chứng minh được điều đó)
  - từ +NOI_TU giây, AI được cho nói liên tục (voice/say) để thấy rõ lúc tiếng thông
Tự cúp sau NOI_S giây nối máy; chốt chặn cứng 70 giây kể từ lúc chạy.

    .venv\\python.exe scripts\\do_tre_duong_tiem.py [NOI_S=24] [NOI_TU=2.0] [THU=co] [CHO_NHAC=1.5] [CAN_THIEP=co]

CHO_NHAC=0 là nhấc máy ngay khi đổ chuông - ca khó nhất: tiếng hồi chuông của
chính máy AI còn giữ luồng phát mở. Kết quả vào logs/do_tiem_<giờ>/: bản thu ở
máy khách, logcat máy AI (xem các dòng `primary_out-proxy_open_playback_stream`,
`primary_out-out_standby`, `VoiceBridge`, `restartIfDisabled`), bản soi mixer/PCM.

ĐỪNG cho AI nói (voice/say) lúc còn đổ chuông: luồng phát mở trước đường tiêm
không mang được tiếng vào cuộc gọi, máy kia sẽ im suốt cuộc - đó là lỗi của phép
đo chứ không phải của sản phẩm (đã mắc 09-10-2026, tốn hai cuộc gọi).
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from backend.services import adb_service as ad  # noqa: E402
from scripts.hai_may_tu_goi import CauKhach, api, RATE  # noqa: E402

AI, KH = "21f10e44220c7ece", "228b1b68920b7ece"
DEV, CID, PORT = "dev_643aeac5", "ct_a1a87cbc", 8124
NOI_S = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
NOI_TU = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
THU = (sys.argv[3] if len(sys.argv) > 3 else "co") == "co"
CHO_NHAC = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5   # doi bao lau sau khi do chuong roi moi nhac may
CAN_THIEP = (sys.argv[5] if len(sys.argv) > 5 else "co") == "co"
RA = Path("logs/do_tiem_" + time.strftime("%H%M%S"))
RA.mkdir(parents=True, exist_ok=True)


def cup():
    for s in (AI, KH):
        subprocess.run(["adb", "-s", s, "shell", "input", "keyevent", "6"], capture_output=True)


def chot():
    cup()
    print("CHOT CHAN 70s: da cup ca hai may", flush=True)
    os._exit(4)


_t = threading.Timer(70, chot)
_t.daemon = True
_t.start()

CTL = [f"ABOX SPUS OUT{i}" for i in (0, 1, 2, 3, 4, 6, 7)] + [
    "ABOX UAIF0 SPK", "ABOX NSRC1", "AIF1TX1 Input 1", "AIF1TX1 Input 2", "AIF1TX2 Input 2"]
DONG = ["i=0", "while [ $i -lt 400 ]; do", ' echo "=== $(date +%s.%N)"',
        " dumpsys telephony.registry | grep -m3 -E 'Foreground call state|mCallState'",
        ' for f in /proc/asound/card*/pcm*/sub0/status; do s=$(head -1 $f); '
        'if [ "$s" != closed ]; then echo "PCM $f $s"; fi; done']
DONG += [f' {ad.MIXCTL} get "{c}"' for c in CTL]
DONG += [" i=$((i+1))", " sleep 0.15", "done", ""]
(RA / "soi.sh").write_bytes("\n".join(DONG).encode())
subprocess.run(["adb", "-s", AI, "push", str(RA / "soi.sh"), "/data/local/tmp/soi.sh"],
               capture_output=True)
subprocess.run(["adb", "-s", AI, "logcat", "-c"], capture_output=True)
soi = subprocess.Popen(["adb", "-s", AI, "shell", "su", "-c", "sh /data/local/tmp/soi.sh"],
                       stdout=open(RA / "soi_may_ai.txt", "wb"), stderr=subprocess.STDOUT)

DEM = ("Một, hai, ba, bốn, năm, sáu, bảy, tám, chín, mười.",
       "Mười một, mười hai, mười ba, mười bốn, mười lăm.",
       "Hai mươi, ba mươi, bốn mươi, năm mươi, sáu mươi.")
dang_noi = True


def noi_lien_tuc():
    i = 0
    while dang_noi:
        try:
            api(f"/api/devices/{DEV}/voice/say", {"text": DEM[i % 3]}, cho=20)
        except Exception:
            pass
        i += 1
        time.sleep(0.2)


async def main() -> int:
    global dang_noi
    moc: dict = {}
    cau = None
    print("ket qua luu o", RA)
    print("1. may AI quay so (duong san pham) ...")
    ra = api(f"/api/phones/contacts/{CID}/call", {"voice_name": "default"})
    if ra.get("error"):
        print("   LOI:", ra["error"])
        return 1
    sid = ra.get("session_id") or (ra.get("session") or {}).get("session_id", "")
    moc["quay"], moc["phien"] = time.time(), sid
    print("   phien", sid)
    try:
        t0 = time.time()
        while time.time() - t0 < 40:
            if (await ad.call_state(KH))[0] == "ringing":
                break
            await asyncio.sleep(0.3)
        else:
            print("   may khach KHONG do chuong")
            return 2
        moc["do_chuong"] = time.time()
        print(f"   do chuong sau {moc['do_chuong'] - moc['quay']:.1f}s")
        await asyncio.sleep(CHO_NHAC)
        t_bam = time.time()
        for lan in range(6):
            await ad.answer(KH)
            t_bam = time.time()
            await asyncio.sleep(0.4)
            if (await ad.precise_call_state(KH))[0] == 1:
                break
        moc["nhac_may"] = t_bam
        print(f"   may khach nhac may (bam lan {lan + 1})")
        if THU:
            print("   cau tieng may KHACH:", (await ad.start_bridge(KH, port=PORT))[0])
            for _ in range(30):
                try:
                    cau = CauKhach(PORT)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            moc["thu_tu"] = time.time()
            print(f"   may khach bat dau thu {moc['thu_tu'] - t_bam:.2f}s sau khi nhac may")
        await asyncio.sleep(max(0.0, NOI_TU - (time.time() - t_bam)))
        moc["noi_tu"] = time.time()
        threading.Thread(target=noi_lien_tuc, daemon=True).start()

        def da_nghe() -> bool:
            """May khach da nghe thay tieng AI chua: 2 o 0,5s lien nhau deu to."""
            if cau is None:
                return False
            x = np.frombuffer(bytes(cau.thu[-RATE * 2:]), dtype=np.int16).astype(np.float32)
            if len(x) < RATE:
                return False
            a1, b1 = x[-RATE:-RATE // 2], x[-RATE // 2:]
            return float(np.sqrt((a1 * a1).mean())) > 300 and float(np.sqrt((b1 * b1).mean())) > 300

        # CAN THIEP ngay trong cuoc: neu toi moc ma may khach van chua nghe thi
        # thu mot thao tac, de biet thao tac nao lam tieng thong.
        can_thiep = [(9.0, "A_dat_lai_duong_tiem"), (15.0, "B_don_moi_SPUS_sang_SIFS1")] if CAN_THIEP else []
        while time.time() - t_bam < NOI_S:
            await asyncio.sleep(0.1)
            if da_nghe() and "nghe_tu" not in moc:
                moc["nghe_tu"] = time.time()
                print(f"   >>> may khach BAT DAU NGHE tieng AI o +{moc['nghe_tu'] - t_bam:.1f}s")
            if can_thiep and time.time() - t_bam >= can_thiep[0][0]:
                _, ten = can_thiep.pop(0)
                if "nghe_tu" in moc:
                    continue
                moc[ten] = time.time()
                if ten.startswith("A"):
                    kq = await ad.set_uplink_injection(AI, True)
                else:
                    lenh = "; ".join(f'{ad.MIXCTL} set "ABOX SPUS OUT{i}" SIFS1' for i in range(8))
                    (RA / "b.sh").write_bytes((lenh + "\n").encode())
                    subprocess.run(["adb", "-s", AI, "push", str(RA / "b.sh"), "/data/local/tmp/b.sh"],
                                   capture_output=True)
                    kq = subprocess.run(["adb", "-s", AI, "shell", "su", "-c", "sh /data/local/tmp/b.sh"],
                                        capture_output=True, text=True).stdout.strip()[-120:]
                print(f"   can thiep {ten} o +{moc[ten] - t_bam:.1f}s (xong +{time.time() - t_bam:.1f}s): {kq}")
    finally:
        dang_noi = False
        moc["cup"] = time.time()
        cup()
        try:
            await ad.hangup(AI)
            await ad.hangup(KH)
            if THU:
                await ad.stop_bridge(KH, port=PORT)
            api(f"/api/phones/contacts/{CID}/result", {"status": "done"})
        except Exception as e:
            print("   don loi:", e)
        soi.terminate()
        r = subprocess.run(["adb", "-s", AI, "logcat", "-d", "-v", "epoch"], capture_output=True)
        (RA / "logcat_may_ai.txt").write_bytes(r.stdout)
        (RA / "moc.json").write_text(json.dumps(moc, ensure_ascii=False, indent=1), encoding="utf-8")
    if cau is None:
        return 0
    cau.dong()
    pcm = bytes(cau.thu)
    with wave.open(str(RA / "may_khach_nghe.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n = RATE // 2
    k = len(x) // n
    muc = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) if k else np.zeros(0)
    tre = moc["thu_tu"] - moc["nhac_may"]
    print(f"\nMAY KHACH NGHE (RMS moi 0,5s). Ban thu bat dau {tre:.2f}s sau khi nhac may; "
          f"AI noi lien tuc tu +{moc['noi_tu'] - moc['nhac_may']:.1f}s; cup o +{moc['cup'] - moc['nhac_may']:.1f}s")
    for j in range(0, k, 10):
        print(f"  +{tre + j * 0.5:5.1f}s:", " ".join(f"{v:5.0f}" for v in muc[j:j + 10]))
    return 0


raise SystemExit(asyncio.run(main()))
