"""The spoken continuation and cached audio must use the same exact text."""
import pytest

from backend.pipeline.noi_cau_dem import loi_sau_dem, xep_ghep_dau


DEM = "Dạ em nói rõ cho anh chị phần này luôn nhé,"


@pytest.mark.parametrize("prefix", ["Dạ ", "Dạ, ", "Dạ vâng ạ, ", "Vâng, ", "dạ dạ "])
@pytest.mark.parametrize("body", [
    "gói này hỗ trợ tối đa 500 triệu đồng, chưa phải hạn mức được duyệt.",
    "nếu được duyệt 275 triệu đồng trong 24 tháng, tháng đầu khoảng 13,2 triệu đồng.",
    "không thể xác nhận lãi suất này khi chưa có hồ sơ ạ.",
    "CCCD và sao kê lương 3 tháng gần nhất là giấy tờ cần chuẩn bị ạ.",
])
def test_only_salutation_changes(prefix, body):
    assert loi_sau_dem(DEM, prefix + body) == body


@pytest.mark.parametrize("text", ["Dạ.", "Vâng ạ.", "Dạ vâng ạ.", "Vâng lời cha mẹ là điều tốt."])
def test_short_acknowledgement_and_lexical_vang_are_not_erased(text):
    assert loi_sau_dem(DEM, text) == text


def test_no_filler_keeps_original_exactly():
    text = "  Dạ nếu được duyệt 400 triệu đồng thì mới áp dụng ạ. "
    assert loi_sau_dem("", text) == text


def test_topic_and_conditions_are_never_deleted_from_fixed_answers():
    text = "Dạ nếu nợ xấu nhóm 3 thì hồ sơ cần được xem xét riêng ạ."
    assert loi_sau_dem("Dạ về trường hợp nếu nợ xấu nhóm 3 thì,", text) == text[3:]


@pytest.mark.parametrize(("filler", "answer", "expected"), [
    (
        "Dạ về hạn mức vay thì,",
        "Dạ hạn mức tối đa của gói vay là 500 triệu đồng ạ.",
        "tối đa của gói vay là 500 triệu đồng ạ.",
    ),
    (
        "Dạ về hồ sơ thì,",
        "Hồ sơ chính gồm CCCD và sao kê lương 3 tháng gần nhất ạ.",
        "chính gồm CCCD và sao kê lương 3 tháng gần nhất ạ.",
    ),
    (
        "Dạ về lãi suất thì,",
        "Mức lãi suất áp dụng từ 7,9% một năm ạ.",
        "áp dụng từ 7,9% một năm ạ.",
    ),
    (
        "Dạ hạn mức bên em thì,",
        "Hạn mức vay tối đa là 500 triệu đồng ạ.",
        "tối đa là 500 triệu đồng ạ.",
    ),
])
def test_repeated_safe_topic_head_is_removed(filler, answer, expected):
    assert loi_sau_dem(filler, answer) == expected


@pytest.mark.parametrize(("filler", "answer"), [
    (
        "Dạ về phần nợ xấu,",
        "Nợ xấu nhóm 3 thì hồ sơ cần được xem xét riêng ạ.",
    ),
    (
        "Dạ về điều kiện vay thì,",
        "Nếu thu nhập dưới 8 triệu đồng thì cần thẩm định thêm ạ.",
    ),
    (
        "Dạ em nói rõ cho anh chị phần này luôn nhé,",
        "Hạn mức tối đa là 500 triệu đồng ạ.",
    ),
])
def test_risky_or_generic_filler_never_trims_topic(filler, answer):
    assert loi_sau_dem(filler, answer) == answer


def test_first_clauses_merge_only_with_headroom():
    first = ("Hồ sơ gồm căn cước công dân,", 0.0)
    rest = [("và sao kê lương ba tháng gần nhất.", 0.0)]
    merged, pending = xep_ghep_dau(first, rest, True, 2000, lambda _: 400)
    assert merged == [first] + rest and pending == [None]
    merged, pending = xep_ghep_dau(first, rest, True, 300, lambda _: 400)
    assert merged == [first] and pending == rest + [None]


def test_first_sentence_boundary_is_kept():
    first = ("Em đã ghi nhận ạ.", 0.0)
    rest = [("Anh cần chuẩn bị căn cước.", 0.0)]
    merged, pending = xep_ghep_dau(first, rest, True, 3000, lambda _: 100)
    assert merged == [first] and pending == rest + [None]


def test_partial_budget_keeps_order_and_end_marker():
    first = ("Căn cước công dân,", 0.0)
    rest = [("và sao kê lương,", 0.0), ("cùng thông tin liên hệ.", 0.0)]
    merged, pending = xep_ghep_dau(first, rest, True, 700,
                                  lambda text: 200 * (text.count(",") + int(text.endswith("."))))
    assert merged == [first, rest[0]] and pending == [rest[1], None]


def test_filler_text_is_snapshotted_before_another_session_can_change_it(monkeypatch):
    import asyncio
    import io
    import time
    import wave
    from types import SimpleNamespace
    from backend.pipeline import streaming_pipeline as sp

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\0\0" * 2400)
    pipe = sp.StreamingPipeline.__new__(sp.StreamingPipeline)
    pipe.tts = SimpleNamespace(_filler_text_cuoi=DEM,
        filler_dai_nhat_ms=lambda *a: 2000,
        pick_filler=lambda *a, **kw: (output.getvalue(), "", "chung"))
    async def send(*args, **kwargs):
        pipe.tts._filler_text_cuoi = "Dạ về một chủ đề của phiên khác,"
        await asyncio.sleep(0)
    pipe._send_audio = send
    monkeypatch.setattr(sp, "lay_kho", lambda: SimpleNamespace(duoi=()))
    session = SimpleNamespace(latency_log=[], spec_answer="", spec_stt=None,
                              tinh_huong=None, voice_name="g", turn_id=1)
    metrics = {}
    asyncio.run(pipe._send_filler(None, session, time.perf_counter(), metrics, False))
    assert metrics["filler_text"] == DEM


# --- Câu đệm KHÔNG còn chữ "thì" (13-09-2026) ---------------------------------
#
# Khung dấu phẩy "Dạ về X," không đỡ được vị ngữ cụt: cắt chủ đề ra "Dạ về hồ sơ,
# chính gồm căn cước..." nghe như rớt chữ (đo trên câu trả lời thật của luật tài
# chính). Nên khung mới giữ NGUYÊN câu trả lời, chỉ bỏ lễ phép lặp.
@pytest.mark.parametrize(("filler", "answer", "expected"), [
    ("Dạ về hạn mức vay,", "Dạ hạn mức tối đa của gói vay là 500 triệu đồng ạ.",
     "hạn mức tối đa của gói vay là 500 triệu đồng ạ."),
    ("Dạ về hạn mức bên em,", "Hạn mức vay tối đa là 500 triệu đồng ạ.",
     "Hạn mức vay tối đa là 500 triệu đồng ạ."),
    ("Dạ về hồ sơ,", "Dạ hồ sơ chính gồm căn cước công dân ạ.",
     "hồ sơ chính gồm căn cước công dân ạ."),
])
def test_khung_moi_khong_thi_giu_nguyen_chu_de(filler, answer, expected):
    assert loi_sau_dem(filler, answer) == expected


def test_duoi_bat_dau_bang_cua_thi_giu_chu_de():
    """"Dạ về lãi suất thì, của gói vay là..." cụt nghĩa. Giữ nguyên chủ đề."""
    text = "Lãi suất của gói vay là từ 7.9%/năm ạ."
    assert loi_sau_dem("Dạ về lãi suất thì,", text) == text
