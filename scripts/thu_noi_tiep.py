"""THỬ NGHIỆM (bản nháp, chưa vào pipeline): sinh mảnh k+1 NỐI TIẾP mảnh k.

F5 là mô hình điền vào chỗ trống: nó nhận một đoạn tiếng kèm lời rồi sinh phần
còn thiếu. Hiện pipeline sinh mỗi mảnh như MỘT PHÁT NGÔN RIÊNG, nên chỗ nối có
hai lỗi đã đo: chữ cuối mảnh k bị ngân (447ms) và tông mảnh k+1 lệch 6-15%.

Ba cách sinh cùng một câu, cắt mảnh y hệt pipeline:
  A. rời     - mỗi mảnh một phát ngôn, nối kèm nhịp nghỉ (đang chạy)
  B. nối     - đoạn mẫu = giọng mẫu + TOÀN BỘ tiếng mảnh k, lời = lời mẫu +
               chữ mảnh k + chữ mảnh k+1 -> mảnh k+1 là phần tiếp của k
  C. nối+đè  - như B nhưng CẮT BỎ 250ms cuối tiếng mảnh k trước khi làm đoạn
               mẫu; F5 phải điền lại đuôi đó cùng mảnh k+1, rồi vuốt chéo
               ở chỗ nối -> đuôi ngân của k bị thay bằng bản có ngữ cảnh

Đo ở MỖI chỗ nối: lệch tông (nửa cung) giữa 400ms trước và 400ms sau chỗ nối,
và độ dài đoạn có tiếng liền cuối cùng trước chỗ nối (chữ ngân). Xuất wav để
nghe: logs/thu_noi_tiep/{A,B,C}_{i}.wav

    .venv\\python.exe scripts\\thu_noi_tiep.py [--cat-ms 250] [--so 10]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from backend.core.device import DEVICE  # noqa: E402
from backend.pipeline.text_chunker import nhip_nghi_sau, should_flush  # noqa: E402
from backend.services.tts_service import (F5TTSService, bo_dau_cau_cho_f5,  # noqa: E402
                                          trim_silence)

SR = 24000
CAU = [
    "Dạ, lãi suất vay tín chấp bên em hiện tại là sáu phẩy năm phần trăm một năm, áp dụng cho khoản vay từ năm mươi triệu trở lên, và anh chị cần chứng minh thu nhập ba tháng gần nhất thôi ạ.",
    "Dạ vâng, với khoản vay năm trăm triệu thì thời hạn tối đa là hai mươi lăm năm, còn số tiền trả hàng tháng thì tuỳ vào thời hạn anh chị chọn, em có thể tính cụ thể cho mình ngay ạ.",
    "Dạ, hồ sơ chỉ cần căn cước công dân, sổ hộ khẩu và bảng lương ba tháng gần nhất, sau khi nhận đủ giấy tờ thì bên em duyệt trong vòng ba ngày làm việc ạ.",
    "Dạ, thẻ tín dụng bên em miễn phí thường niên năm đầu, hạn mức tối đa gấp ba lần lương, và anh chị được miễn lãi tới bốn mươi lăm ngày nếu thanh toán đủ ạ.",
    "Dạ, gói tiết kiệm sáu tháng hiện có lãi suất năm phẩy ba phần trăm, còn gói mười hai tháng là năm phẩy chín phần trăm, anh chị gửi trực tuyến trên ứng dụng cũng được hưởng đúng mức đó ạ.",
    "Dạ em hiểu ạ, nếu anh chị đang có khoản vay ở ngân hàng khác thì bên em vẫn xét được, chỉ cần tổng số tiền trả nợ hàng tháng không vượt quá một nửa thu nhập là ổn ạ.",
    "Dạ, anh chị có thể đến chi nhánh gần nhất hoặc đăng ký trực tuyến trên ứng dụng của ngân hàng, cả hai cách đều mất khoảng mười phút, và em sẽ gửi lại hướng dẫn qua tin nhắn ạ.",
    "Dạ, khoản vay mua nhà bên em cho vay tới bảy mươi phần trăm giá trị căn nhà, lãi suất cố định hai năm đầu là bảy phẩy hai phần trăm, sau đó thả nổi theo thị trường ạ.",
    "Dạ vâng, phí trả nợ trước hạn là hai phần trăm trên số tiền trả trước trong ba năm đầu, từ năm thứ tư trở đi thì không mất phí gì nữa ạ.",
    "Dạ, em xin phép ghi nhận số điện thoại của anh chị, nhân viên tín dụng sẽ liên hệ lại trong hôm nay để hẹn lịch, anh chị cứ chuẩn bị sẵn giấy tờ giúp em ạ.",
]


def cat_manh(cau: str) -> list[str]:
    """Cắt y hệt vòng stream của pipeline: dồn từng từ rồi hỏi should_flush."""
    manh, dem = [], ""
    for tu in cau.split():
        dem = (dem + " " + tu).strip()
        if should_flush(dem, first_chunk=(len(manh) == 0)):
            manh.append(dem)
            dem = ""
    if dem.strip():
        manh.append(dem.strip())
    return manh


# ---------------------------------------------------------------- đo
def f0_khung(x: np.ndarray, sr: int, khung_ms=40, buoc_ms=10):
    n, h = int(sr * khung_ms / 1000), int(sr * buoc_ms / 1000)
    lo, hi = int(sr / 400), int(sr / 70)
    ra = []
    for i in range(0, max(0, len(x) - n), h):
        w = x[i:i + n] - x[i:i + n].mean()
        if float(np.sqrt((w ** 2).mean())) < 0.01:
            ra.append(np.nan); continue
        ac = np.correlate(w, w, "full")[n - 1:]
        if ac[0] <= 0:
            ra.append(np.nan); continue
        seg = ac[lo:hi]
        k = int(np.argmax(seg)) + lo
        ra.append(sr / k if ac[k] / ac[0] > 0.3 else np.nan)
    return np.array(ra)


def lech_tong_o_noi(x: np.ndarray, sr: int, vi_tri: int, ms=400) -> float:
    """Nửa cung giữa tông nền 400ms trước và 400ms sau chỗ nối (bỏ khung im)."""
    n = int(sr * ms / 1000)
    a = f0_khung(x[max(0, vi_tri - n):vi_tri], sr)
    b = f0_khung(x[vi_tri:vi_tri + n], sr)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 5 or len(b) < 5:
        return float("nan")
    return float(12 * np.log2(np.median(b) / np.median(a)))


def ngan_truoc_noi(x: np.ndarray, sr: int, vi_tri: int) -> float:
    """Độ dài (ms) đoạn CÓ TIẾNG liền mạch cuối cùng trước chỗ nối."""
    f = f0_khung(x[max(0, vi_tri - int(sr * 1.5)):vi_tri], sr)
    co = ~np.isnan(f)
    # bỏ đuôi im, rồi đếm ngược tới khung im gần nhất
    i = len(co) - 1
    while i >= 0 and not co[i]:
        i -= 1
    j = i
    while j >= 0 and co[j]:
        j -= 1
    return (i - j) * 10.0


# ---------------------------------------------------------------- sinh
class Sinh:
    def __init__(self, tts: F5TTSService):
        from f5_tts.infer.utils_infer import hop_length, target_rms, target_sample_rate
        import torchaudio
        self.tts, self.hop, self.rms_dich = tts, hop_length, target_rms
        ref_wave, ref_sr, ref_text = tts._voices[tts._default_voice]
        a = ref_wave
        if a.shape[0] > 1:
            a = a.mean(0, keepdim=True)
        if ref_sr != target_sample_rate:
            a = torchaudio.transforms.Resample(ref_sr, target_sample_rate)(a)
        self.ref = a.squeeze(0).cpu().numpy().astype(np.float32)
        self.ref_text = ref_text + (" " if len(ref_text[-1].encode("utf-8")) == 1 else "")

    def _sample(self, *a, **kw) -> np.ndarray:
        """Đi qua executor của service: CUDA graphs (và Triton trên Windows) gắn
        với LUỒNG đã biên dịch, gọi từ luồng khác là AssertionError/sập câm."""
        return self.tts._executor.submit(self._sample_sync, *a, **kw).result()

    def _sample_sync(self, prompt_wave: np.ndarray, prompt_text: str, gen_text: str,
                     them_khung: int = 0, nfe: int | None = None) -> np.ndarray:
        """Sinh phần tiếp theo `gen_text` sau đoạn mẫu (prompt_wave, prompt_text)."""
        from f5_tts.model.utils import convert_char_to_pinyin
        from backend.config import settings
        t = self.tts
        a = torch.from_numpy(prompt_wave)[None, :]
        rms = torch.sqrt(torch.mean(torch.square(a)))
        if rms < self.rms_dich:
            a = a * self.rms_dich / rms
        a = a.to(DEVICE)
        ref_len = a.shape[-1] // self.hop
        pt = prompt_text if len(prompt_text[-1].encode("utf-8")) > 1 else prompt_text + " "
        pt = pt if pt.endswith(" ") else pt + " "
        dur = ref_len + int(ref_len / len(pt.encode("utf-8")) * len(gen_text.encode("utf-8"))) + them_khung
        torch.manual_seed(0)
        with torch.inference_mode(), t._autocast_ctx():
            gen, _ = t._model.sample(
                cond=a, text=convert_char_to_pinyin([pt + gen_text]), duration=dur,
                steps=nfe or settings.f5tts_nfe_step,
                cfg_strength=settings.f5tts_cfg_strength,
                sway_sampling_coef=settings.f5tts_sway_sampling_coef)
            gen = gen.to(torch.float32)[:, ref_len:, :].permute(0, 2, 1)
            song = t._vocoder.decode(gen)
            if rms < self.rms_dich:
                song = song * rms / self.rms_dich
        return song.squeeze().cpu().numpy().astype(np.float32)

    def roi(self, chu: str) -> np.ndarray:
        return trim_silence(self._sample(self.ref, self.ref_text, bo_dau_cau_cho_f5(chu)), SR)

    def noi(self, tieng_truoc: np.ndarray, chu_truoc: str, chu: str,
            cat_ms: float = 0.0) -> np.ndarray:
        """Sinh `chu` như phần tiếp của `tieng_truoc` (đã đọc `chu_truoc`)."""
        giu = tieng_truoc if cat_ms <= 0 else tieng_truoc[:-int(SR * cat_ms / 1000)]
        prompt = np.concatenate([self.ref, giu])
        ptext = self.ref_text + bo_dau_cau_cho_f5(chu_truoc) + " "
        them = int(cat_ms / 1000 * SR / self.hop) + 5 if cat_ms > 0 else 0
        return self._sample(prompt, ptext, bo_dau_cau_cho_f5(chu), them_khung=them)


def vuot_cheo(a: np.ndarray, b: np.ndarray, ms: float = 20.0) -> np.ndarray:
    n = min(int(SR * ms / 1000), len(a), len(b))
    if n <= 0:
        return np.concatenate([a, b])
    r = np.linspace(0, 1, n, dtype=np.float32)
    giua = a[-n:] * (1 - r) + b[:n] * r
    return np.concatenate([a[:-n], giua, b[n:]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat-ms", type=float, default=250.0)
    ap.add_argument("--so", type=int, default=len(CAU))
    a = ap.parse_args()
    ra = GOC / "logs" / "thu_noi_tiep"
    ra.mkdir(parents=True, exist_ok=True)

    tts = F5TTSService()
    tts.load()
    s = Sinh(tts)
    print(f"giọng {tts._default_voice}, đoạn mẫu {len(s.ref)/SR:.2f}s")

    kq = {"A": [], "B": [], "C": []}
    for i, cau in enumerate(CAU[:a.so]):
        manh = cat_manh(cau)
        if len(manh) < 2:
            continue
        # --- A: rời ---
        xa, noi_a = [], []
        for k, m in enumerate(manh):
            x = s.roi(m)
            if k > 0:
                xa.append(np.zeros(int(SR * nhip_nghi_sau(manh[k - 1]) / 1000), np.float32))
                noi_a.append(sum(len(p) for p in xa[:-1]))
            xa.append(x)
        A = np.concatenate(xa)
        # --- B: nối (không cắt) ---
        xb, noi_b = [s.roi(manh[0])], []
        for k in range(1, len(manh)):
            noi_b.append(sum(len(p) for p in xb))
            xb.append(trim_silence(s.noi(xb[-1], manh[k - 1], manh[k]), SR))
        B = np.concatenate(xb)
        # --- C: nối + cắt đuôi rồi điền lại ---
        C, noi_c, truoc, chu_truoc = s.roi(manh[0]), [], None, manh[0]
        for k in range(1, len(manh)):
            cat = int(SR * a.cat_ms / 1000)
            tiep = s.noi(C, chu_truoc, manh[k], cat_ms=a.cat_ms)
            noi_c.append(len(C) - cat)
            C = vuot_cheo(C[:-cat], tiep)
            chu_truoc = manh[k]
        for ten, X, noi in (("A", A, noi_a), ("B", B, noi_b), ("C", C, noi_c)):
            sf.write(str(ra / f"{ten}_{i}.wav"), X, SR)
            for v in noi:
                kq[ten].append({"cau": i, "lech_tong": lech_tong_o_noi(X, SR, v),
                                "ngan_ms": ngan_truoc_noi(X, SR, v)})
        print(f"câu {i}: {len(manh)} mảnh | dài A {len(A)/SR:.2f}s B {len(B)/SR:.2f}s C {len(C)/SR:.2f}s", flush=True)

    print("\n=== trung vị trên mọi chỗ nối ===")
    for ten in "ABC":
        lt = [abs(r["lech_tong"]) for r in kq[ten] if not np.isnan(r["lech_tong"])]
        ng = [r["ngan_ms"] for r in kq[ten]]
        print(f"  {ten}: |lệch tông| {statistics.median(lt):.2f} nửa cung (tệ nhất {max(lt):.2f})"
              f" | chữ ngân trước chỗ nối {statistics.median(ng):.0f}ms | n={len(kq[ten])}")
    (ra / "kq.json").write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nfile nghe: {ra}")


if __name__ == "__main__":
    main()
