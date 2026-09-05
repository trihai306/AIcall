"""Đo: gộp hai lượt CFG (cond + uncond) của F5 thành MỘT lượt forward batch=2.

Hiện tại `CFM.sample` gọi transformer 2 lần mỗi bước (pred rồi null_pred) ->
nfe 16 = 32 lần phóng DiT với batch=1. F5 upstream (>=1.1) gộp thành 1 lần
batch=2 (`cfg_infer`). GPU đang nghẽn ở phóng kernel (điện 46%, xung 94%) nên
gộp batch gần như miễn phí về thời gian mà tốn thêm VRAM - đúng thứ đang dư.

Cách làm KHÔNG đụng mã fork: bọc `model.transformer` bằng một lớp ngoài. Lượt
gọi cond (drop_*=False) -> chạy inner với cfg_infer=True, trả pred, cất null_pred.
Lượt gọi uncond ngay sau -> trả null_pred đã cất. `sample()` giữ nguyên.

Chạy:  .venv\\python.exe scripts\\do_gop_cfg.py --gop 0|1 [--nfe 16] [--luot 3]
So sánh hai lần chạy (mỗi lần một tiến trình vì compile khác nhau).
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import settings  # noqa: E402
from backend.core.device import DEVICE  # noqa: E402

CAU = [
    "Dạ vâng ạ.",
    "Dạ, em chào anh chị ạ.",
    "Dạ, lãi suất hiện tại của gói này là sáu phẩy năm phần trăm một năm ạ.",
    "Anh chị cần chuẩn bị căn cước công dân và sổ hộ khẩu ạ.",
    "Dạ, thời hạn vay tối đa là hai mươi lăm năm, còn số tiền thì tuỳ theo giá trị tài sản đảm bảo ạ.",
    "Em xin phép gửi lại thông tin qua tin nhắn để anh chị tiện theo dõi ạ.",
    "Dạ, hồ sơ được duyệt trong vòng ba ngày làm việc kể từ khi nhận đủ giấy tờ ạ.",
    "Anh chị có thể đến chi nhánh gần nhất hoặc đăng ký trực tuyến trên ứng dụng của ngân hàng ạ.",
]


class LoiDiT(torch.nn.Module):
    """Phần lõi DiT nhận text-embed ĐÃ tính sẵn. Đây là phần đem compile.

    Tách text-embed ra ngoài vì với CUDA graphs, tensor cache đặt trên module
    trong vùng compile là đầu ra của graph -> bị ghi đè ở lượt sau -> lỗi
    "accessing tensor output of CUDAGraphs that has been overwritten".
    """

    def __init__(self, raw, cfg: bool):
        super().__init__()
        self.raw = raw
        self.cfg = cfg

    def forward(self, x, cond, tc, tu, time, mask):
        r = self.raw
        batch, seq_len = x.shape[0], x.shape[1]
        if time.ndim == 0:
            time = time.repeat(batch)
        t = r.time_embed(time)
        if self.cfg:
            x = torch.cat((r.input_embed(x, cond, tc, drop_audio_cond=False),
                           r.input_embed(x, cond, tu, drop_audio_cond=True)), dim=0)
            t = torch.cat((t, t), dim=0)
            mask = torch.cat((mask, mask), dim=0) if mask is not None else None
        else:
            x = r.input_embed(x, cond, tc, drop_audio_cond=False)
        rope = r.rotary_embed.forward_from_seq_len(seq_len)
        residual = x if r.long_skip_connection is not None else None
        for block in r.transformer_blocks:
            x = block(x, t, mask=mask, rope=rope)
        if residual is not None:
            x = r.long_skip_connection(torch.cat((x, residual), dim=-1))
        return r.proj_out(r.norm_out(x, t))


class GopCFG(torch.nn.Module):
    """Bọc ngoài transformer: gộp cặp gọi cond/uncond của CFM.sample thành một."""

    def __init__(self, raw, compile_kw: dict | None, cfg_buoc: int = 0):
        super().__init__()
        self.raw = raw
        self.loi = LoiDiT(raw, cfg=True)
        self.loi_don = LoiDiT(raw, cfg=False)
        if compile_kw is not None:
            self.loi = torch.compile(self.loi, **compile_kw)
            self.loi_don = torch.compile(self.loi_don, **compile_kw)
        self._null = None
        self._tc = self._tu = None
        self.cfg_buoc = cfg_buoc  # >0: chỉ dẫn dắt (CFG) ở N bước đầu
        self._buoc = 0

    def clear_cache(self):
        self.raw.clear_cache()
        self._null = self._tc = self._tu = None
        self._buoc = 0

    def forward(self, x, cond, text, time, drop_audio_cond, drop_text, mask=None, cache=False):
        seq_len = x.shape[1]
        if not drop_audio_cond and not drop_text:
            if self._tc is None:  # text-embed tính MỘT lần mỗi sample, ngoài graph
                self._tc = self.raw.text_embed(text, seq_len, drop_text=False)
                self._tu = self.raw.text_embed(text, seq_len, drop_text=True)
            self._buoc += 1
            torch.compiler.cudagraph_mark_step_begin()
            if self.cfg_buoc and self._buoc > self.cfg_buoc:
                pred = self.loi_don(x, cond, self._tc, None, time, mask).clone()
                self._null = pred  # pred + (pred-null)*cfg = pred -> bỏ CFG bước này
                return pred
            out = self.loi(x, cond, self._tc, self._tu, time, mask).clone()
            pred, self._null = torch.chunk(out, 2, dim=0)
            return pred
        if drop_audio_cond and drop_text and self._null is not None:
            n, self._null = self._null, None
            return n
        raise RuntimeError("thứ tự gọi cond/uncond không như CFM.sample mong đợi")


# ---------------------------------------------------------------- nạp
def nap(gop: bool, compile_: bool, dynamic: bool = True, mode: str = "", cfg_buoc: int = 0):
    from f5_tts.infer.utils_infer import load_model, load_vocoder
    from f5_tts.model import DiT
    from f5_tts.model.backbones import dit as dit_mod

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_float32_matmul_precision("high")
    voc = load_vocoder(vocoder_name="vocos", device=DEVICE)
    model = load_model(
        model_cls=DiT,
        model_cfg=dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512,
                       text_mask_padding=False, conv_layers=4, pe_attn_head=1),
        ckpt_path=settings.f5tts_ckpt_path, vocab_file=settings.f5tts_vocab_path,
        device=DEVICE,
    )
    raw = model.transformer
    kw = dict(dynamic=dynamic, **({"mode": mode} if mode else {}))
    if gop:
        model.transformer = GopCFG(raw, kw if compile_ else None, cfg_buoc)
    else:
        model.transformer = torch.compile(raw, **kw) if compile_ else raw
    return model, voc


def nap_ref():
    import torchaudio
    from f5_tts.infer.utils_infer import hop_length, target_rms, target_sample_rate
    wav = Path(settings.f5tts_ref_audio)
    txt = wav.with_suffix(".txt")
    ref_text = txt.read_text(encoding="utf-8").strip() if txt.exists() else settings.f5tts_ref_text
    a, sr = torchaudio.load(str(wav))
    if a.shape[0] > 1:
        a = a.mean(0, keepdim=True)
    rms = torch.sqrt(torch.mean(torch.square(a)))
    if rms < target_rms:
        a = a * target_rms / rms
    if sr != target_sample_rate:
        a = torchaudio.transforms.Resample(sr, target_sample_rate)(a)
    a = a.to(DEVICE)
    if len(ref_text[-1].encode("utf-8")) == 1:
        ref_text += " "
    return a, ref_text, a.shape[-1] // hop_length, float(rms)


_SDPA = ""


def _sdpa_ctx():
    from contextlib import nullcontext
    if not _SDPA:
        return nullcontext()
    from torch.nn.attention import sdpa_kernel, SDPBackend
    be = {"cudnn": [SDPBackend.CUDNN_ATTENTION, SDPBackend.EFFICIENT_ATTENTION],
          "efficient": [SDPBackend.EFFICIENT_ATTENTION]}[_SDPA]
    return sdpa_kernel(be)


def sinh(model, voc, ref, text, nfe, speed=1.0):
    from f5_tts.infer.utils_infer import hop_length, target_rms
    from f5_tts.model.utils import convert_char_to_pinyin
    a, ref_text, ref_len, rms = ref
    dur = ref_len + int(ref_len / len(ref_text.encode("utf-8")) * len(text.encode("utf-8")) / speed)
    torch.manual_seed(0)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16), _sdpa_ctx():
        gen, _ = model.sample(cond=a, text=convert_char_to_pinyin([ref_text + text]),
                              duration=dur, steps=nfe,
                              cfg_strength=settings.f5tts_cfg_strength,
                              sway_sampling_coef=settings.f5tts_sway_sampling_coef)
        torch.cuda.synchronize()
        t1 = time.perf_counter()
        gen = gen.to(torch.float32)[:, ref_len:, :].permute(0, 2, 1)
        wav = voc.decode(gen)
        if rms < target_rms:
            wav = wav * rms / target_rms
        wav = wav.squeeze().cpu().numpy()
        torch.cuda.synchronize()
        t2 = time.perf_counter()
    return wav, (t1 - t0) * 1000, (t2 - t1) * 1000


def sinh_lo(model, voc, ref, texts, nfe, speed=1.0):
    """Đường lô như `_synthesize_lo_sync`: nhiều mảnh, một lần sample, có mask."""
    from f5_tts.infer.utils_infer import hop_length, target_rms
    from f5_tts.model.utils import convert_char_to_pinyin
    a, ref_text, ref_len, rms = ref
    khung = [ref_len + int(ref_len / len(ref_text.encode("utf-8")) * len(t.encode("utf-8")) / speed) for t in texts]
    torch.manual_seed(0)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        gen, _ = model.sample(cond=a.repeat(len(texts), 1),
                              text=convert_char_to_pinyin([ref_text + t for t in texts]),
                              duration=torch.tensor(khung, device=DEVICE, dtype=torch.long),
                              steps=nfe, cfg_strength=settings.f5tts_cfg_strength,
                              sway_sampling_coef=settings.f5tts_sway_sampling_coef)
        torch.cuda.synchronize(); t1 = time.perf_counter()
        gen = gen.to(torch.float32)[:, ref_len:, :].permute(0, 2, 1)
        wav = voc.decode(gen)
        torch.cuda.synchronize(); t2 = time.perf_counter()
    return (t1 - t0) * 1000, (t2 - t1) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gop", type=int, default=0)
    ap.add_argument("--compile", type=int, default=1)
    ap.add_argument("--nfe", type=int, default=None)
    ap.add_argument("--luot", type=int, default=3)
    ap.add_argument("--dynamic", type=int, default=1)
    ap.add_argument("--mode", default="")
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--sdpa", default="")
    ap.add_argument("--cfg_buoc", type=int, default=0)
    ap.add_argument("--ra", default="logs/do_gop_cfg")
    a = ap.parse_args()
    nfe = a.nfe or settings.f5tts_nfe_step
    global _SDPA
    _SDPA = a.sdpa
    ra = Path(a.ra) / f"gop{a.gop}_c{a.compile}_d{a.dynamic}_m{a.mode or 'x'}_s{a.sdpa or 'x'}_cb{a.cfg_buoc}_nfe{nfe}"
    ra.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    model, voc = nap(bool(a.gop), bool(a.compile), bool(a.dynamic), a.mode, a.cfg_buoc)
    ref = nap_ref()
    print(f"nap xong {time.perf_counter()-t0:.1f}s  gop={a.gop} compile={a.compile} dynamic={a.dynamic} mode={a.mode} nfe={nfe}", flush=True)

    # làm nóng (compile thật sự chạy ở đây)
    t0 = time.perf_counter()
    for c in CAU[:3]:
        sinh(model, voc, ref, c, nfe)
    print(f"lam nong {time.perf_counter()-t0:.1f}s  VRAM dinh {torch.cuda.max_memory_allocated()/2**20:.0f}MB", flush=True)
    torch.cuda.reset_peak_memory_stats()

    if a.lo:
        nhom = [CAU[i:i + a.lo] for i in range(0, len(CAU), a.lo)]
        for n in nhom:
            sinh_lo(model, voc, ref, n, nfe)
        ket = []
        for luot in range(a.luot):
            for j, n in enumerate(nhom):
                d, v = sinh_lo(model, voc, ref, n, nfe)
                ket.append(d / len(n))
                print(f"  [{luot}] lo{j} ({len(n)} manh) dit {d:6.0f}ms -> {d/len(n):5.0f}ms/manh  voc {v:4.0f}ms", flush=True)
        print(f"KQ LO gop={a.gop} lo={a.lo}: DiT trung vi {statistics.median(ket):.0f}ms/manh  tb {statistics.mean(ket):.0f}  VRAM dinh {torch.cuda.max_memory_allocated()/2**20:.0f}MB")
        return

    dit_ms, voc_ms, rows = [], [], []
    for luot in range(a.luot):
        for i, c in enumerate(CAU):
            wav, d, v = sinh(model, voc, ref, c, nfe)
            dit_ms.append(d); voc_ms.append(v)
            rows.append(dict(luot=luot, i=i, dit=d, voc=v, giay=len(wav) / 24000))
            if luot == 0:
                sf.write(str(ra / f"{i}.wav"), wav, 24000)
            print(f"  [{luot}] cau{i} dit {d:6.0f}ms  voc {v:5.0f}ms  am {len(wav)/24000:.2f}s", flush=True)
    tong = [d + v for d, v in zip(dit_ms, voc_ms)]
    kq = dict(gop=a.gop, compile=a.compile, nfe=nfe,
              dit_tv=statistics.median(dit_ms), voc_tv=statistics.median(voc_ms),
              tong_tv=statistics.median(tong), tong_tb=statistics.mean(tong),
              vram_dinh_mb=torch.cuda.max_memory_allocated() / 2**20, rows=rows)
    (ra / "kq.json").write_text(json.dumps(kq, indent=1), encoding="utf-8")
    print(f"KQ gop={a.gop}: DiT trung vi {kq['dit_tv']:.0f}ms  vocoder {kq['voc_tv']:.0f}ms  "
          f"tong trung vi {kq['tong_tv']:.0f}ms (tb {kq['tong_tb']:.0f})  VRAM dinh {kq['vram_dinh_mb']:.0f}MB")


if __name__ == "__main__":
    main()
