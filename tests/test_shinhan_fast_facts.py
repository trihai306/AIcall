"""Đường trả lời nhanh chỉ dùng dữ kiện Shinhan chắc chắn và file còn nguyên."""

import hashlib
import json

from backend.pipeline import shinhan_fast_facts as fast


def _setup(monkeypatch, tmp_path):
    doc = tmp_path / "shinhan_card_user_guide_vi.md"
    doc.write_text("Shinhan Bank — kích hoạt thẻ qua SOL", encoding="utf-8")
    index = tmp_path / "fast_answers.json"
    index.write_text(json.dumps({
        "version": 1,
        "entries": [{
            "id": "activate_card",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Dạ, mình kích hoạt thẻ qua SOL ạ.",
        }, {
            "id": "activate_digital_card",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Nhập mã SMS để kích hoạt thẻ điện tử.",
        }, {
            "id": "register_and_activate_digital_card",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Đăng ký trên SOL rồi nhập mã SMS để kích hoạt.",
        }, {
            "id": "activation_status_unknown",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Em chưa xác nhận được trạng thái thẻ qua cuộc trò chuyện này.",
        }, {
            "id": "digital_card_fee_unknown",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Chưa có căn cứ về phí.",
        }, {
            "id": "digital_card_comparison_unknown",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Chưa có căn cứ so sánh.",
        }, {
            "id": "digital_card_fee_comparison_unknown",
            "source_file": doc.name,
            "source_file_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "answer": "Chưa có căn cứ về phí hoặc so sánh.",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(fast, "ROOT", tmp_path)
    monkeypatch.setattr(fast, "INDEX", index)
    return doc


def test_fast_answer_rejects_other_bank_and_personal_status(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    assert fast.tra_loi_nhanh("Kích hoạt thẻ thế nào?", bank="Shinhan") == (
        "activate_card", "Dạ, mình kích hoạt thẻ qua SOL ạ.")
    assert fast.tra_loi_nhanh("Kích hoạt thẻ thế nào?", bank="Ngân hàng khác") is None
    assert fast.tra_loi_nhanh("Thẻ Shinhan của tôi đã kích hoạt chưa?") == (
        "activation_status_unknown",
        "Em chưa xác nhận được trạng thái thẻ qua cuộc trò chuyện này.",
    )
    assert fast.tra_loi_nhanh("Kích hoạt thẻ điện tử Shinhan thế nào?") == (
        "activate_digital_card", "Nhập mã SMS để kích hoạt thẻ điện tử.")
    assert fast.tra_loi_nhanh("Kích hoạt thẻ điện tử Shinhan sau khi đăng ký thế nào?") == (
        "activate_digital_card", "Nhập mã SMS để kích hoạt thẻ điện tử.")
    assert fast.tra_loi_nhanh("Đăng ký và kích hoạt thẻ điện tử Shinhan thế nào?") == (
        "register_and_activate_digital_card",
        "Đăng ký trên SOL rồi nhập mã SMS để kích hoạt.")
    assert fast.tra_loi_nhanh("Mở thẻ điện tử Shinhan và có mất phí không?")[0] == (
        "digital_card_fee_unknown")
    assert fast.tra_loi_nhanh("Đăng ký và kích hoạt thẻ điện tử Shinhan có mất phí không?")[0] == (
        "digital_card_fee_unknown")
    assert fast.tra_loi_nhanh("Thẻ điện tử Shinhan khác thẻ vật lý thế nào?")[0] == (
        "digital_card_comparison_unknown")
    assert fast.tra_loi_nhanh("Thẻ điện tử Shinhan khác thẻ vật lý và có mất phí không?")[0] == (
        "digital_card_fee_comparison_unknown")
    assert fast.tra_loi_nhanh(
        "Thẻ điện tử Shinhan của tôi đã kích hoạt chưa và có mất phí không?") is None
    assert fast.tra_loi_nhanh(
        "Phí thẻ điện tử Shinhan và ngân hàng khác thế nào?") is None


def test_fast_answer_stops_when_source_document_changes(monkeypatch, tmp_path):
    doc = _setup(monkeypatch, tmp_path)
    question = "Thẻ Shinhan mới nhận kích hoạt thế nào?"
    assert fast.tra_loi_nhanh(question) is not None

    doc.write_text("Nguồn đã được người dùng sửa", encoding="utf-8")
    assert fast.tra_loi_nhanh(question) is None
