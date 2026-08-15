"""`cfg_strength` và `sway_sampling_coef` phải lấy từ cài đặt, ở CẢ HAI đường sinh.

Đo ngày 16-08-2026 trên 16 cấu hình, thước đo là khoảng cách tới 5 clip người
thật (phẳng phổ, F0 dao động, jitter, HNR):

    nfe48 cfg2.0 sway 0.0   lệch  8.3%   CER 1.44%
    nfe32 cfg3.0 sway-1.0   lệch 10.0%   CER 1.74%
    nfe16 cfg2.0 sway-1.0   lệch 18.0%            <- mặc định cũ

Hai núm này trước đây KHÔNG chỉnh được:
  - `_synthesize_sync` gọi `infer_batch_process` mà không truyền, ăn mặc định
    của thư viện;
  - `_synthesize_lo_sync` ghi cứng `cfg_strength=2.0, sway_sampling_coef=-1`.

Phải khoá CẢ HAI. Đường lô KHÔNG phải mã chết: `streaming_pipeline` gọi
`_try_synthesize_lo` cho mọi lượt ra nhiều hơn một mảnh, và nó không bị chặn bởi
cờ `GOP_LO`. Sửa mỗi đường một mảnh thì cuộc gọi một mảnh và cuộc gọi nhiều mảnh
đọc bằng hai chất giọng khác nhau - đúng kiểu lỗi im lặng mà dự án này đã dính
vài lần (xem chú thích `van_tay` trong `filler_store`).

Và hai núm này KHÔNG độc lập: sway 0.0 ghép với cfg 3.0 đo ra lệch 88%, HNR tụt
từ 5.87dB xuống 1.56dB. Nên chúng phải đi cùng nhau từ một chỗ cấu hình, không
được để mỗi đường một giá trị.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
import torch

from backend.config import settings
from backend.services import tts_service as M


@pytest.fixture
def dich_vu(monkeypatch):
    """Một F5TTSService có đủ đồ giả để chạy tới chỗ gọi model, không nạp GPU."""
    sv = M.F5TTSService()
    # 1 giây tiếng giả ở 24kHz: đủ dài để `thoi_luong_ep` không trả None.
    sv._voices = {"g": (torch.zeros(1, 24000), 24000, "câu mẫu để thử")}
    sv._model = object()
    sv._vocoder = object()
    monkeypatch.setattr(settings, "f5tts_cfg_strength", 3.0, raising=False)
    monkeypatch.setattr(settings, "f5tts_sway_sampling_coef", 0.0, raising=False)
    return sv


def test_duong_mot_manh_truyen_cfg_va_sway(dich_vu, monkeypatch):
    """`_synthesize_sync` phải truyền cả hai núm xuống `infer_batch_process`."""
    da_goi = {}

    def gia(*args, **kwargs):
        da_goi.update(kwargs)
        yield (np.zeros(2400, dtype=np.float32), 24000, None)

    import f5_tts.infer.utils_infer as U
    monkeypatch.setattr(U, "infer_batch_process", gia)

    dich_vu._synthesize_sync("một câu để thử", "g")

    assert "cfg_strength" in da_goi, (
        "infer_batch_process bị gọi mà KHÔNG truyền cfg_strength -> ăn mặc định "
        "thư viện, chỉnh trong .env không có tác dụng"
    )
    assert "sway_sampling_coef" in da_goi, (
        "infer_batch_process bị gọi mà KHÔNG truyền sway_sampling_coef"
    )
    assert da_goi["cfg_strength"] == 3.0
    assert da_goi["sway_sampling_coef"] == 0.0


def test_duong_gop_lo_truyen_cfg_va_sway(dich_vu, monkeypatch):
    """`_synthesize_lo_sync` phải lấy từ cài đặt, không ghi cứng 2.0 / -1."""
    da_goi = {}

    class ModelGia:
        def sample(self, **kwargs):
            da_goi.update(kwargs)
            b = kwargs["cond"].shape[0]
            dai = int(kwargs["duration"].max().item())
            return torch.zeros(b, dai, 100), None

    class VocoderGia:
        def decode(self, gen):
            return torch.zeros(gen.shape[0], gen.shape[-1] * 256)

    dich_vu._model = ModelGia()
    dich_vu._vocoder = VocoderGia()

    dich_vu._synthesize_lo_sync(["câu một để thử", "câu hai để thử"], "g")

    assert da_goi["cfg_strength"] == 3.0, (
        f"đường gộp lô đọc cfg_strength={da_goi.get('cfg_strength')} thay vì lấy "
        "từ cài đặt -> lượt nhiều mảnh đọc khác lượt một mảnh"
    )
    assert da_goi["sway_sampling_coef"] == 0.0, (
        f"đường gộp lô đọc sway_sampling_coef={da_goi.get('sway_sampling_coef')} "
        "thay vì lấy từ cài đặt"
    )


def test_mac_dinh_giu_nguyen_hanh_vi_cu():
    """Không đặt gì trong .env thì phải ra ĐÚNG cấu hình cũ.

    Nếu mặc định đổi theo, mọi máy chưa sửa .env sẽ âm thầm đổi giọng.
    """
    from backend.config import Settings

    mac_dinh = Settings.model_fields
    assert mac_dinh["f5tts_cfg_strength"].default == 2.0
    assert mac_dinh["f5tts_sway_sampling_coef"].default == -1.0
