"""Xác nhận đường tiếng xuống điện thoại THẬT SỰ chạy qua bước tăng tuần hoàn.

Vì sao cần: cờ bật trong .env không đảm bảo code chạy. `toi_uu_cho_thoai` và
`tang_tuan_hoan` đều nằm sau điều kiện `RATE_XUONG <= NGUONG_HEP_BANG`, mà
RATE_XUONG đọc từ settings LÚC NẠP MODULE - sửa .env mà quên khởi động lại thì
cờ mới nằm trong file còn tiến trình vẫn chạy giá trị cũ, và ta sẽ nghe y hệt
như trước rồi kết luận nhầm là kỹ thuật không ăn thua.

Script này chạy đúng chuỗi biến đổi của `PhoneCallBridge.play()` rồi đo, nên
trả lời được câu "tiếng thật sự gửi xuống máy đã khác chưa".

    C:/duan/chat-ai/.venv/python.exe scripts/kiem_duong_tieng.py
"""

import asyncio
import io
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

CAU = "Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp lãi suất ưu đãi."


async def main() -> int:
    from backend.config import settings
    from backend.services import phone_call_service as P
    from backend.services.audio_utils import resample_audio
    from tang_tuan_hoan import do_hnr, do_phang_pho, ghi_wav, lay_bo_ma_amr

    print("\n  CẤU HÌNH ĐANG CHẠY TRONG TIẾN TRÌNH")
    print("  " + "=" * 62)
    print(f"    phone_rate_xuong        {settings.phone_rate_xuong}")
    print(f"    RATE_XUONG (đã nạp)     {P.RATE_XUONG}")
    print(f"    ngưỡng hẹp băng         {P.NGUONG_HEP_BANG}")
    print(f"    phone_toi_uu_am         {settings.phone_toi_uu_am}")
    print(f"    phone_tang_tuan_hoan    {settings.phone_tang_tuan_hoan}")
    print(f"    phone_luoc/du_alpha     {settings.phone_luoc_alpha} / "
          f"{settings.phone_du_alpha}")

    hep = P.RATE_XUONG <= P.NGUONG_HEP_BANG
    chay_toi_uu = settings.phone_toi_uu_am and hep
    chay_tuan_hoan = settings.phone_tang_tuan_hoan and hep
    print("\n    => bù phổ thoại      :", "CÓ chạy" if chay_toi_uu else "KHÔNG chạy")
    print("    => tăng tuần hoàn    :", "CÓ chạy" if chay_tuan_hoan else "KHÔNG chạy")
    if not chay_tuan_hoan:
        print("\n    [!] Chưa chạy. Kiểm PHONE_TANG_TUAN_HOAN và PHONE_RATE_XUONG"
              " trong .env, rồi khởi động lại dịch vụ.")
        return 1

    # --- chạy đúng chuỗi của play() -------------------------------------
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    wav = await tts.synthesize(CAU, use_cache=False)

    with wave.open(io.BytesIO(wav)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = x.astype(np.float32) / 32768

    # y hệt PhoneCallBridge.play()
    a = P.toi_uu_cho_thoai(x, sr) if chay_toi_uu else P.chuan_muc_thoai(x)
    if sr != P.RATE_XUONG:
        a = resample_audio(a, sr, P.RATE_XUONG)
    sau = P.tang_tuan_hoan(a, P.RATE_XUONG)

    # đối chứng: đúng chuỗi đó nhưng KHÔNG có bước tăng tuần hoàn
    truoc = a

    qua_amr, duong = lay_bo_ma_amr()
    print(f"\n  ĐO TRÊN ĐƯỜNG TIẾNG THẬT   (bộ mã: {duong})")
    print("  " + "=" * 62)
    print(f"    {'':<26}{'HNR sau AMR':>13}{'phẳng sau':>12}{'đỉnh':>9}")
    print("  " + "-" * 62)
    for ten, sig in (("không tăng tuần hoàn", truoc), ("CÓ tăng tuần hoàn", sau)):
        y = qua_amr(sig)
        print(f"    {ten:<26}{do_hnr(y, 8000):>13.2f}"
              f"{do_phang_pho(y, 8000):>12.4f}{np.abs(sig).max():>9.3f}")
    print("  " + "=" * 62)
    print(f"    trần đỉnh cho phép: {settings.phone_dinh_toi_da}")

    out = PROJECT / "logs" / "duong_tieng_that"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()
    ghi_wav(out / "a_khong_tang_tuan_hoan__qua_dien_thoai.wav",
            qua_amr(truoc), 8000)
    ghi_wav(out / "b_co_tang_tuan_hoan__qua_dien_thoai.wav", qua_amr(sau), 8000)
    print(f"\n    Mẫu nghe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
