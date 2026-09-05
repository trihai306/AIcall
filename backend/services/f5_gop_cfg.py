"""Gộp hai lượt CFG của F5-TTS thành một, và mở đường cho CUDA graphs.

`CFM.sample` của fork gọi transformer HAI lần mỗi bước khuếch tán: một lượt có
điều kiện (pred) rồi một lượt rỗng (null_pred) cho classifier-free guidance.
nfe 16 thành 32 lần phóng DiT với batch=1. F5 upstream từ 1.1 gộp hai lượt thành
MỘT forward batch=2 (`cfg_infer`). Đo 04-09-2026 trên RTX 5070 (scripts/do_gop_cfg.py,
8 câu × 3 vòng, bỏ vòng biên dịch):

    hiện tại                     340ms/câu    "Dạ vâng ạ" 228ms
    gộp CFG                      290ms        184ms
    gộp CFG + CUDA graphs        247ms        140ms

Chất lượng không đổi: cùng seed, sóng ra tương quan 0,98-0,9999 với bản cũ,
lệch chỉ ở thứ tự phép tính fp16.

Cách làm KHÔNG đụng mã fork: bọc `model.transformer` bằng `GopCFG`. `sample()`
vẫn gọi hai lượt như cũ; lượt cond chạy lõi một lần với batch=2, trả pred và
cất null_pred; lượt uncond ngay sau trả cái đã cất.

Vì sao text-embed tính NGOÀI vùng compile: bản gốc cache `text_cond` trên
module bên trong forward. Với CUDA graphs, tensor đó là ĐẦU RA của graph và bị
ghi đè ở lượt sau -> "accessing tensor output of CUDAGraphs that has been
overwritten". Tính một lần ở ngoài rồi truyền vào lõi là hết.

CUDA graphs (`mode="reduce-overhead"`) trên Windows cần `cl.exe` của MSVC trong
PATH lúc biên dịch - máy Win có MSVC BuildTools nhưng PATH không có, đó là lý
do trước đây nó chết `CppCompileError`. `nap_moi_truong_msvc()` nạp môi trường
từ vcvars64.bat vào tiến trình hiện tại.
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess

import torch

logger = logging.getLogger(__name__)

_MAU_VCVARS = [
    r"C:\Program Files*\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files*\Microsoft Visual Studio\*\VC\Auxiliary\Build\vcvars64.bat",
]


def nap_moi_truong_msvc() -> bool:
    """Đưa cl.exe (và INCLUDE/LIB đi kèm) vào môi trường tiến trình này.

    Trả True nếu sau đó tìm thấy `cl`. Trên hệ khác Windows trả False ngay.
    """
    if shutil.which("cl"):
        return True
    if os.name != "nt":
        return False
    ung = [p for mau in _MAU_VCVARS for p in glob.glob(mau)]
    if not ung:
        logger.warning("Không thấy vcvars64.bat - CUDA graphs cần MSVC BuildTools.")
        return False
    try:
        ra = subprocess.run(
            ["cmd", "/c", f'call "{ung[0]}" >nul && set'],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception as e:  # noqa: BLE001
        logger.warning("Nạp vcvars64.bat hỏng: %s", e)
        return False
    for dong in ra.splitlines():
        k, co, v = dong.partition("=")
        if k and co:
            os.environ[k] = v
    ok = shutil.which("cl") is not None
    logger.info("MSVC: %s (%s)", "đã nạp" if ok else "nạp mà vẫn không thấy cl", ung[0])
    return ok


class LoiDiT(torch.nn.Module):
    """Phần lõi DiT nhận text-embed ĐÃ tính sẵn. Đây là phần đem compile.

    `cfg=True`: nhận cả hai embed, chạy batch=2 (cond xếp trước, uncond sau).
    `cfg=False`: chỉ lượt cond, batch như đầu vào.
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
    """Bọc ngoài `model.transformer`, giữ nguyên giao diện `CFM.sample` gọi tới.

    `cfg_buoc` > 0: chỉ dẫn dắt (CFG) ở N bước ĐẦU, các bước sau chạy lượt cond
    một mình (batch=1) và trả null = pred để guidance bằng 0. Đo được 12/16 bước
    -34%, 8/16 bước -41% so với hiện tại, NHƯNG sóng ra khác hẳn (tương quan
    0,44-0,98) - chỉ tai người phán được, mặc định 0.
    """

    def __init__(self, raw, compile_kw: dict | None = None, cfg_buoc: int = 0):
        super().__init__()
        self.raw = raw
        self.loi = LoiDiT(raw, cfg=True)
        self.loi_don = LoiDiT(raw, cfg=False)
        if compile_kw is not None:
            self.loi = torch.compile(self.loi, **compile_kw)
            self.loi_don = torch.compile(self.loi_don, **compile_kw)
        self.cfg_buoc = int(cfg_buoc or 0)
        self._null = None
        self._tc = self._tu = None
        self._buoc = 0

    def clear_cache(self):
        """`CFM.sample` gọi sau mỗi lần sinh - đây là ranh giới giữa hai câu."""
        self.raw.clear_cache()
        self._null = self._tc = self._tu = None
        self._buoc = 0

    def forward(self, x, cond, text, time, drop_audio_cond, drop_text,
                mask=None, cache=False):
        seq_len = x.shape[1]
        if not drop_audio_cond and not drop_text:
            if self._tc is None:  # text-embed tính MỘT lần mỗi câu, ngoài graph
                self._tc = self.raw.text_embed(text, seq_len, drop_text=False)
                self._tu = self.raw.text_embed(text, seq_len, drop_text=True)
            self._buoc += 1
            torch.compiler.cudagraph_mark_step_begin()
            if self.cfg_buoc and self._buoc > self.cfg_buoc:
                pred = self.loi_don(x, cond, self._tc, None, time, mask).clone()
                self._null = pred  # pred + (pred - null) * cfg = pred
                return pred
            ra = self.loi(x, cond, self._tc, self._tu, time, mask).clone()
            pred, self._null = torch.chunk(ra, 2, dim=0)
            return pred
        if drop_audio_cond and drop_text and self._null is not None:
            n, self._null = self._null, None
            return n
        raise RuntimeError(
            "GopCFG: thứ tự gọi không như CFM.sample mong đợi "
            f"(drop_audio_cond={drop_audio_cond}, drop_text={drop_text})"
        )
