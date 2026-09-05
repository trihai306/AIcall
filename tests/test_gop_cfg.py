"""GopCFG phải trả ĐÚNG những gì hai lượt gọi rời của CFM.sample trả.

Stub DiT ở đây không có attention thật, chỉ cần các phép tuyến tính theo từng
phần tử batch để kiểm: gộp batch=2 rồi tách ra có bằng chạy rời từng lượt không,
cắt CFG có làm guidance về 0 đúng bước không, và ranh giới câu có được dọn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import torch

from backend.services.f5_gop_cfg import GopCFG, LoiDiT

D, MEL, TDIM = 8, 4, 3


class _Rope:
    def forward_from_seq_len(self, n):
        return None


class _Block(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.lin = torch.nn.Linear(D, D)

    def forward(self, x, t, mask=None, rope=None):
        return self.lin(x) + t[:, None, :]


class _InputEmbed(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(MEL * 2 + TDIM, D)

    def forward(self, x, cond, te, drop_audio_cond=False):
        if drop_audio_cond:
            cond = torch.zeros_like(cond)
        return self.proj(torch.cat((x, cond, te), dim=-1))


class _TimeEmbed(torch.nn.Module):
    """Như TimestepEmbedding của F5: nhận (b,) trả (b, D)."""

    def __init__(self):
        super().__init__()
        self.lin = torch.nn.Linear(1, D)

    def forward(self, time):
        return self.lin(time[:, None])


class _NormOut(torch.nn.Module):
    def forward(self, x, t):
        return x * 2


class StubDiT(torch.nn.Module):
    """Đủ thuộc tính mà LoiDiT chạm tới, và forward gốc y hệt fork để đối chứng."""

    def __init__(self):
        super().__init__()
        torch.manual_seed(1)
        self.time_embed = _TimeEmbed()
        self.emb = torch.nn.Embedding(10, TDIM)
        self.input_embed = _InputEmbed()
        self.rotary_embed = _Rope()
        self.transformer_blocks = torch.nn.ModuleList([_Block(), _Block()])
        self.long_skip_connection = None
        self.norm_out = _NormOut()
        self.proj_out = torch.nn.Linear(D, MEL)
        self.text_cond = self.text_uncond = None

    def clear_cache(self):
        self.text_cond = self.text_uncond = None

    def text_embed(self, text, seq_len, drop_text=False):
        text = torch.zeros_like(text) if drop_text else text
        return self.emb(text)

    def forward(self, x, cond, text, time, drop_audio_cond, drop_text, mask=None, cache=False):
        if time.ndim == 0:
            time = time.repeat(x.shape[0])
        t = self.time_embed(time)
        te = self.text_embed(text, x.shape[1], drop_text=drop_text)
        h = self.input_embed(x, cond, te, drop_audio_cond=drop_audio_cond)
        for b in self.transformer_blocks:
            h = b(h, t)
        return self.proj_out(self.norm_out(h, t))


def _dau_vao(batch=1, n=5):
    torch.manual_seed(7)
    return (torch.randn(batch, n, MEL), torch.randn(batch, n, MEL),
            torch.randint(1, 10, (batch, n)), torch.tensor(0.3))


def test_gop_bang_hai_luot_roi():
    raw = StubDiT()
    x, cond, text, t = _dau_vao()
    pred_roi = raw(x, cond, text, t, drop_audio_cond=False, drop_text=False)
    null_roi = raw(x, cond, text, t, drop_audio_cond=True, drop_text=True)

    gop = GopCFG(raw)
    pred = gop(x, cond, text, t, drop_audio_cond=False, drop_text=False, cache=True)
    null = gop(x, cond, text, t, drop_audio_cond=True, drop_text=True, cache=True)
    assert torch.allclose(pred, pred_roi, atol=1e-6)
    assert torch.allclose(null, null_roi, atol=1e-6)


def test_gop_giu_dung_lo_nhieu_phan_tu_co_mask():
    raw = StubDiT()
    x, cond, text, t = _dau_vao(batch=3)
    mask = torch.ones(3, 5, dtype=torch.bool)
    pred_roi = raw(x, cond, text, t, drop_audio_cond=False, drop_text=False, mask=mask)
    gop = GopCFG(raw)
    pred = gop(x, cond, text, t, drop_audio_cond=False, drop_text=False, mask=mask, cache=True)
    assert pred.shape == (3, 5, MEL)
    assert torch.allclose(pred, pred_roi, atol=1e-6)


def test_cat_cfg_sau_n_buoc_thi_null_bang_pred():
    raw = StubDiT()
    x, cond, text, t = _dau_vao()
    gop = GopCFG(raw, cfg_buoc=2)
    for buoc in range(1, 4):
        pred = gop(x, cond, text, t, drop_audio_cond=False, drop_text=False, cache=True)
        null = gop(x, cond, text, t, drop_audio_cond=True, drop_text=True, cache=True)
        if buoc <= 2:
            assert not torch.allclose(pred, null)   # còn dẫn dắt
        else:
            assert torch.equal(pred, null)           # guidance = 0


def test_clear_cache_bat_dau_lai_cau_moi():
    raw = StubDiT()
    x, cond, text, t = _dau_vao()
    gop = GopCFG(raw, cfg_buoc=1)
    gop(x, cond, text, t, False, False, cache=True)
    gop(x, cond, text, t, True, True, cache=True)
    gop(x, cond, text, t, False, False, cache=True)
    null = gop(x, cond, text, t, True, True, cache=True)
    pred_khac = gop._null  # đã lấy ra nên phải rỗng
    assert pred_khac is None
    gop.clear_cache()
    assert gop._buoc == 0 and gop._tc is None
    pred = gop(x, cond, text, t, False, False, cache=True)
    null2 = gop(x, cond, text, t, True, True, cache=True)
    assert not torch.allclose(pred, null2)  # bước 1 câu mới: CFG lại có hiệu lực
    del null


def test_goi_uncond_truoc_thi_bao_loi():
    raw = StubDiT()
    x, cond, text, t = _dau_vao()
    gop = GopCFG(raw)
    with pytest.raises(RuntimeError):
        gop(x, cond, text, t, drop_audio_cond=True, drop_text=True, cache=True)


def test_loi_dit_don_va_gop_cung_ket_qua_phan_cond():
    raw = StubDiT()
    x, cond, text, t = _dau_vao()
    tc = raw.text_embed(text, 5, drop_text=False)
    tu = raw.text_embed(text, 5, drop_text=True)
    ra_gop = LoiDiT(raw, cfg=True)(x, cond, tc, tu, t, None)
    ra_don = LoiDiT(raw, cfg=False)(x, cond, tc, None, t, None)
    assert ra_gop.shape[0] == 2
    assert torch.allclose(ra_gop[:1], ra_don, atol=1e-6)
