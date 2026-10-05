"""Tạo tài liệu RAG Shinhan từ fact card đã đối chiếu với PDF nguồn.

Chỉ lấy card thuộc PDF có nhãn `review` và kiểm tra SHA-256 của PDF trước khi
ghi. Không nhập nguyên PDF vì tài liệu lưu trữ và bảng phí/lãi suất có thể đã
thay đổi; những nguồn đó không thuộc bộ fact card này.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/external/shinhan/manifest.json"
CARDS = ROOT / "data/training/shinhan_verified_fact_cards.json"
OUTPUT = ROOT / "knowledge/shinhan"
# Chỉ các ý đơn có đường trả lời tức thì; các card khác vẫn dùng RAG + Qwen.
FAST_IDS = ("activate_card", "lost_card", "register_digital_card", "activate_digital_card")


def build() -> dict[str, int]:
    manifest = {item["name"]: item for item in json.loads(MANIFEST.read_text("utf-8"))}
    cards = json.loads(CARDS.read_text("utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        source = card["source"]
        item = manifest[source]
        if item.get("status") != "downloaded" or item.get("use") != "review":
            raise ValueError(f"Nguồn chưa được rà để lập chỉ mục: {source}")
        pdf = ROOT / "data/external/shinhan" / f"{source}.pdf"
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"PDF đã thay đổi so với manifest: {source}")
        grouped[source].append(card)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {}
    document_hashes = {}
    for source, source_cards in sorted(grouped.items()):
        item = manifest[source]
        lines = [
            f"# Shinhan Bank — {source}",
            "",
            f"Nguồn PDF chính thức: {item['url']}",
            f"SHA-256 PDF: {item['sha256']}",
            "Phạm vi: thông tin chung đã đối chiếu; kiểm tra hiệu lực trước khi tư vấn chính sách hiện hành.",
            "",
        ]
        for card in source_cards:
            lines += [
                f"## {card['id']}",
                "",
                f"Shinhan Bank — {card['fact']}",
                f"Trả lời đã đối chiếu: {card['answer']}",
                "",
            ]
        target = OUTPUT / f"shinhan_{source}.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        document_hashes[source] = hashlib.sha256(target.read_bytes()).hexdigest()
        result[source] = len(source_cards)

    fast = []
    for card in cards:
        if card["id"] not in FAST_IDS:
            continue
        source = card["source"]
        fast.append({
            "id": card["id"],
            "source_file": f"shinhan_{source}.md",
            "source_file_sha256": document_hashes[source],
            "source_pdf_url": manifest[source]["url"],
            "fact": card["fact"],
            "answer": card["answer"],
        })
    if {item["id"] for item in fast} != set(FAST_IDS):
        raise ValueError("Thiếu dữ kiện cho câu trả lời tức thì")
    register = next(card for card in cards if card["id"] == "register_digital_card")
    digital = next(card for card in cards if card["id"] == "activate_digital_card")
    if register["source"] != digital["source"]:
        raise ValueError("Hai bước thẻ điện tử phải cùng nguồn đã đối chiếu")
    fast.append({
        "id": "register_and_activate_digital_card",
        "source_file": f"shinhan_{digital['source']}.md",
        "source_file_sha256": document_hashes[digital["source"]],
        "source_pdf_url": manifest[digital["source"]]["url"],
        "fact": f"{register['fact']} {digital['fact']}",
        "answer": ("Dạ, mình mở SOL, chọn Đăng ký thẻ điện tử và xác nhận thỏa thuận. "
                   "Sau đó mình yêu cầu mã xác thực qua SMS, nhập mã theo hướng dẫn "
                   "để kích hoạt ạ. Mình không đọc mã cho người khác nhé."),
    })
    for id_th, answer in (
        ("digital_card_fee_unknown",
         "Dạ, tài liệu hiện có hướng dẫn đăng ký thẻ điện tử trên SOL và kích hoạt bằng mã SMS. Em chưa có căn cứ để xác nhận thẻ có mất phí hay không ạ."),
        ("digital_card_comparison_unknown",
         "Dạ, tài liệu hiện có hướng dẫn đăng ký thẻ điện tử trên SOL và kích hoạt bằng mã SMS. Em chưa có căn cứ để so sánh với thẻ vật lý ạ."),
        ("digital_card_fee_comparison_unknown",
         "Dạ, tài liệu hiện có hướng dẫn đăng ký thẻ điện tử trên SOL và kích hoạt bằng mã SMS. Em chưa có căn cứ để so sánh với thẻ vật lý hoặc xác nhận phí ạ."),
    ):
        fast.append({
            "id": id_th,
            "source_file": f"shinhan_{digital['source']}.md",
            "source_file_sha256": document_hashes[digital["source"]],
            "source_pdf_url": manifest[digital["source"]]["url"],
            "fact": "Kho fact card hiện chưa có dữ kiện về phí hoặc so sánh thẻ vật lý.",
            "answer": answer,
        })
    activate = next(card for card in cards if card["id"] == "activate_card")
    fast.append({
        "id": "activation_status_unknown",
        "source_file": f"shinhan_{activate['source']}.md",
        "source_file_sha256": document_hashes[activate["source"]],
        "source_pdf_url": manifest[activate["source"]]["url"],
        "fact": "Trạng thái thẻ riêng của khách không có trong kho tài liệu chung.",
        "answer": "Em chưa xác nhận được trạng thái kích hoạt thẻ của anh/chị qua cuộc trò chuyện này. Anh/chị có thể kiểm tra trên SOL hoặc gọi 1900 1577 để được hỗ trợ ạ.",
    })
    (OUTPUT / "fast_answers.json").write_text(
        json.dumps({"version": 1, "entries": fast}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    counts = build()
    print(f"Đã tạo {len(counts)} tài liệu, {sum(counts.values())} dữ kiện:")
    for source, count in counts.items():
        print(f"  {source}: {count}")
