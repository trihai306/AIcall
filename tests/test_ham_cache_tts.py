"""Hâm nóng cache TTS trong quãng im — và KHÔNG được phát gì từ đó.

Ý tưởng: `speculate` đã soạn sẵn CHỮ trả lời trong lúc khách còn nói, nhưng toàn
bộ chi phí F5 vẫn nằm sau khi lượt mở (đo được 287-472ms mảnh đầu). Quãng im
cuối lượt (nay 1 giây) đang bỏ không.

Cách làm KHÔNG dựng đường phát mới: `F5TTSService.synthesize` vốn có cache theo
nội dung, khoá `(voice, text, fast, target_sr, nfe_step, speed)`. Ta chỉ sinh
trước đúng mảnh đầu để NẠP CACHE. Lượt thật chạy y nguyên và gặp cache.

BẤT BIẾN AN TOÀN, đây là lý do tệp test này tồn tại: tra cache bằng ĐÚNG chữ
sắp phát, nên đoán sai chỉ có thể thành MISS, không bao giờ thành SAI TIẾNG.
Đường duy nhất phá được bất biến đó là ai đó về sau "tối ưu" bằng cách cất bytes
vào session rồi phát thẳng. `test_khong_cat_bytes_vao_phien` canh đúng chuyện đó.
"""
import asyncio

from backend.pipeline.session_manager import CallSession
from backend.pipeline.streaming_pipeline import StreamingPipeline


def test_manh_dau_lay_dung_luat_cat_chung():
    """Phải dùng `chia_ca_luot` - nguồn duy nhất của luật cắt, đừng viết lại."""
    from backend.pipeline.text_chunker import chia_ca_luot
    tra_loi = "Lãi suất vay tín chấp từ 7.9% một năm ạ. Anh chị cần vay bao nhiêu?"
    assert StreamingPipeline._manh_dau_ham_cache(tra_loi) == chia_ca_luot(tra_loi)[0]


def test_bo_qua_khi_mo_dau_bang_tieu_tu():
    """`_don_loi` có thể bỏ 'Dạ'/'Vâng' tuỳ lượt chẵn lẻ và tuỳ có câu đệm.

    Đoán không nổi thì thà MISS còn hơn sinh một mảnh chắc chắn sai khoá.
    """
    assert StreamingPipeline._manh_dau_ham_cache("Dạ lãi suất từ 7.9% ạ.") is None
    assert StreamingPipeline._manh_dau_ham_cache("Vâng ạ, em tra ngay.") is None


def test_bo_qua_khi_rong():
    assert StreamingPipeline._manh_dau_ham_cache("") is None
    assert StreamingPipeline._manh_dau_ham_cache("   ") is None


class TtsGia:
    _is_loaded = True          # `_tts_available` đọc cờ này

    def __init__(self, ban=0):
        self.dang_ban = ban
        self.da_sinh = []

    async def synthesize(self, text, **kw):
        self.da_sinh.append(text)
        return b"TIENG-GIA"

    def toc_do_cua(self, voice):
        return 1.0

    def he_so_thoai(self):
        return 0.9


def _pipeline(tts):
    p = StreamingPipeline.__new__(StreamingPipeline)
    p.tts = tts
    p._da_bao_tts_chet = False
    return p          # `_tts_available` là property, không gán được


def test_khong_cat_bytes_vao_phien():
    """BẤT BIẾN QUAN TRỌNG NHẤT: hâm cache xong, phiên không giữ tiếng nào."""
    def _co_tieng(s):
        """Các trường đang giữ byte, kèm độ dài - để so trước/sau.

        `CallSession` vốn có `_audio_buf` là bytearray, nên phải so CHÊNH LỆCH
        chứ không phải "có byte nào không".
        """
        return {k: len(v) for k, v in vars(s).items()
                if isinstance(v, (bytes, bytearray))}

    async def kich_ban():
        tts = TtsGia()
        p, s = _pipeline(tts), CallSession()
        truoc_truong, truoc_byte = set(vars(s)), _co_tieng(s)
        await p._ham_cache_tts("Lãi suất từ 7.9% một năm ạ.", s)
        await asyncio.sleep(0.05)
        return tts.da_sinh, set(vars(s)) - truoc_truong, truoc_byte, _co_tieng(s)

    da_sinh, moi, byte_truoc, byte_sau = asyncio.run(kich_ban())
    assert da_sinh == ["Lãi suất từ 7.9% một năm ạ."], "phải có sinh để nạp cache"
    assert not moi, f"đã cất thêm trường vào phiên: {moi}"
    assert byte_sau == byte_truoc, (
        f"tiếng đã lọt vào phiên: {byte_truoc} -> {byte_sau} "
        "-> mở đường phát tiếng chưa xác thực")


def test_khong_chen_khi_worker_dang_ban():
    """Worker F5 chỉ có một. Chen vào là đẩy lùi mảnh kế của lượt đang phát."""
    async def kich_ban():
        tts = TtsGia(ban=1)
        p, s = _pipeline(tts), CallSession()
        await p._ham_cache_tts("Lãi suất từ 7.9% một năm ạ.", s)
        await asyncio.sleep(0.05)
        return tts.da_sinh

    assert asyncio.run(kich_ban()) == []
