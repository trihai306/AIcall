"""F5 co doc dau / va - thanh QUANG NGHI DAI khong?

Nghi van tu ban ghi hoi thoai that: 20/29 quang lang khong giai thich duoc bang
nhip nghi co y cua code (305ms sau phay, 360ms sau cham). Cho chung roi vao rat
dang ngo:

    "chung minh nhan dan."  -> im 920ms -> "canh cuoc."     chu goc: CMND/CCCD
    "cong dan viet nam tu hai muoi hai"  ...  "sau muoi tuoi"  chu goc: 22 - 60

Neu dung thi day KHONG phai loi cua F5 ma la loi CHUAN HOA CHU: LLM viet tat
kieu "CMND/CCCD", "5 trieu dong/thang", "7.9%/nam", "22 - 60", va nhung ky tu
do phai duoc doi sang loi noi TRUOC khi dua vao TTS.

Moi cap duoi day chi khac nhau dung mot thu: co dau gach hay khong.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_dau_gach.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

RA = Path("C:/tmp/daugach")
NGUONG_IM, KHUNG = 0.015, 0.02

CAP = [
    ("gạch chéo /",
     "Anh chuẩn bị chứng minh nhân dân/căn cước công dân và hộ khẩu nhé",
     "Anh chuẩn bị chứng minh nhân dân hoặc căn cước công dân và hộ khẩu nhé"),
    ("gạch ngang khoảng",
     "Khách hàng từ 22 - 60 tuổi đều vay được ạ",
     "Khách hàng từ hai mươi hai đến sáu mươi tuổi đều vay được ạ"),
    ("phần trăm trên năm",
     "Lãi suất chỉ 7.9%/năm thôi ạ",
     "Lãi suất chỉ bảy phẩy chín phần trăm một năm thôi ạ"),
    ("đơn vị trên tháng",
     "Thu nhập từ 5 triệu đồng/tháng trở lên ạ",
     "Thu nhập từ năm triệu đồng một tháng trở lên ạ"),
    ("viết tắt KT3",
     "Anh nộp hộ khẩu hoặc KT3 giúp em ạ",
     "Anh nộp hộ khẩu hoặc ca tê ba giúp em ạ"),
]


def lang_giua(x, sr, toi_thieu_ms=250):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    im = to < NGUONG_IM
    ra, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            if i > 0 and j < k and (j - i) * 20 >= toi_thieu_ms:
                ra.append((j - i) * 20)
            i = j
        else:
            i += 1
    return ra


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)
    LAN = 6

    print(f"\n  giong {ten}   speed {sp:.2f}   nfe {nfe}   {LAN} lượt mỗi bản\n")
    print(f"  {'trường hợp':<22} {'bản':<9} {'lượt có nghỉ':>13} {'nghỉ dài nhất':>14} {'nghỉ TB':>9}")
    print("  " + "-" * 74)

    for nhan, co, khong in CAP:
        for ten_ban, cau in (("CÓ dấu", co), ("đã đổi", khong)):
            ban, laus, tongs = 0, [], []
            for k in range(LAN):
                with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                    y, sr, _ = next(infer_batch_process(
                        (rw, rs), rt, [cau], svc._model, svc._vocoder,
                        mel_spec_type="vocos", progress=None, nfe_step=nfe,
                        speed=sp, device=svc._model.device))
                y = trim_silence(np.asarray(y), sr)
                lg = lang_giua(y, sr)
                ban += bool(lg)
                laus.append(max(lg) if lg else 0)
                tongs.append(sum(lg))
                if k == 0:
                    t = "co" if ten_ban == "CÓ dấu" else "doi"
                    sf.write(RA / f"{nhan.split()[0]}_{t}.wav",
                             y / max(1.0, float(np.abs(y).max())), sr)
            print(f"  {nhan if ten_ban=='CÓ dấu' else '':<22} {ten_ban:<9}"
                  f" {ban:>10}/{LAN} {max(laus):>12.0f}ms {np.mean(tongs):>7.0f}ms")
        print()

    print("  " + "-" * 74)
    print("\n  Nếu cột 'CÓ dấu' nghỉ nhiều/dài hơn hẳn 'đã đổi' thì lỗi nằm ở khâu")
    print("  chuẩn hoá chữ, KHÔNG phải ở F5 - phải đổi ký tự sang lời nói trước khi")
    print(f"  đưa vào TTS.\n\n  wav ở {RA}")


if __name__ == "__main__":
    main()
