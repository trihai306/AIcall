"""Human-reviewed selection of Qwen-drafted Shinhan style examples."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "training"
SOURCE = ROOT / "data" / "external" / "shinhan"
OUTPUT = AUDITS / "shinhan_dialogue_style_v1.jsonl"

# Keys are source audit files; values are row indices checked against the
# downloaded PDF passages. Unsafe or unverifiable suggestions are omitted.
APPROVED = {
    "shinhan_dialogue_draft_audit.json": [6, 7, 8, 10, 12, 13, 14, 17, 24, 27, 31, 36, 40, 43, 46],
    "shinhan_dialogue_draft_audit_b.json": [1, 4, 6, 8, 9, 11, 13, 14, 15, 17, 20, 22, 31, 35, 36],
}

# Clear up forms of address and overly certain wording.  We keep the 9B's
# dialogue framing and only replace the specific unsupported or awkward span.
EDIT = {
    ("shinhan_dialogue_draft_audit.json", 17): "Dạ mình nên khóa thẻ ngay ạ. Mình có thể gọi Shinhan qua 1900 1577, hoặc vào SOL chọn Thẻ > Mở/Khóa Thẻ.",
    ("shinhan_dialogue_draft_audit.json", 10): "Dạ, sau khi kích hoạt thẻ, chị có thể đăng nhập Mobile Banking để thiết lập PIN ạ.",
    ("shinhan_dialogue_draft_audit.json", 12): "Dạ, sau khi nhận và kích hoạt thẻ, mình có thể thiết lập PIN qua Internet Banking hoặc Mobile Banking ạ.",
    ("shinhan_dialogue_draft_audit.json", 14): "Dạ có ạ. Sau khi kích hoạt thẻ, mình có thể thiết lập PIN trên Mobile Banking mà không cần ra chi nhánh.",
    ("shinhan_dialogue_draft_audit.json", 24): "Dạ, số tiền tối thiểu của kỳ này nằm trên sao kê thẻ. Anh xem mục thanh toán tối thiểu và ngày đến hạn giúp em nhé.",
    ("shinhan_dialogue_draft_audit.json", 31): "Dạ đúng ạ. Mình cần trả ít nhất số tiền thanh toán tối thiểu trước hoặc vào ngày đến hạn để tránh phí trả chậm.",
    ("shinhan_dialogue_draft_audit.json", 36): "Dạ có ạ. Sao kê ghi các giao dịch, phí và lãi nếu phát sinh trong kỳ, cùng ngày đến hạn thanh toán.",
    ("shinhan_dialogue_draft_audit.json", 43): "Dạ, để đăng ký chức năng thẻ điện tử, anh vào SOL chọn Đăng ký thẻ điện tử, xác nhận thỏa thuận rồi làm theo các bước xác thực và kích hoạt ạ.",
    ("shinhan_dialogue_draft_audit.json", 46): "Dạ, mình mở ứng dụng SOL, chọn Đăng ký thẻ điện tử, xác nhận thỏa thuận rồi làm theo các bước xác thực ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 1): "Dạ, sau khi nhận thẻ, mình mở SOL hoặc Internet Banking, vào Thẻ rồi chọn Kích hoạt thẻ ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 4): "Dạ, mình vào mục Thẻ trên SOL hoặc Internet Banking rồi chọn Kích hoạt thẻ ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 6): "Dạ, nếu mình muốn dùng thẻ mới nhận thì trước tiên cần kích hoạt thẻ. Mình có thể làm trong SOL hoặc Internet Banking, mục Thẻ ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 11): "Dạ, sau khi kích hoạt thẻ, mình có thể thiết lập PIN qua Internet Banking hoặc Mobile Banking, không cần đến chi nhánh ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 17): "Dạ, mình nên khóa thẻ ngay. Vào SOL hoặc Internet Banking, chọn Thẻ > Mở/Khóa Thẻ; mình cũng có thể gọi 1900 1577 ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 14): "Dạ, mình nên khóa thẻ ngay ạ. Mình có thể gọi 1900 1577 hoặc vào SOL/Internet Banking chọn Thẻ > Mở/Khóa Thẻ.",
    ("shinhan_dialogue_draft_audit_b.json", 15): "Dạ cần xử lý ngay ạ. Mình gọi 1900 1577 hoặc vào SOL/Internet Banking, mục Thẻ > Mở/Khóa Thẻ để khóa thẻ.",
    ("shinhan_dialogue_draft_audit_b.json", 20): "Dạ, em chưa có quyền xem sao kê của khách trong cuộc trò chuyện này. Mình kiểm tra mục thanh toán tối thiểu và ngày đến hạn trên sao kê thẻ giúp em nhé.",
    ("shinhan_dialogue_draft_audit_b.json", 22): "Dạ, mình xem số tiền thanh toán tối thiểu ghi trên sao kê và trả trước hoặc vào ngày đến hạn để tránh phí trả chậm ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 31): "Dạ, mình mở ứng dụng SOL, chọn Đăng ký thẻ điện tử rồi xác nhận thỏa thuận và làm theo các bước xác thực ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 35): "Dạ, mình vào mục Đăng ký thẻ điện tử trong SOL, xác nhận thỏa thuận rồi làm theo các bước xác thực ạ.",
    ("shinhan_dialogue_draft_audit_b.json", 36): "Dạ được ạ. Mình vào Đăng ký thẻ điện tử trên SOL, xác nhận thỏa thuận và hoàn tất xác thực theo hướng dẫn.",
}


def main() -> None:
    manifest = {x["name"]: x for x in json.loads((SOURCE / "manifest.json").read_text())
                if x["status"] == "downloaded"}
    rows = []
    seen = set()
    for filename, indices in APPROVED.items():
        audit = json.loads((AUDITS / filename).read_text(encoding="utf-8"))
        for idx in indices:
            item = audit[idx]
            assert item["status"] == "needs_human_review", (filename, idx)
            assert item["source"] in manifest, (filename, idx)
            question = item["customer"].strip()
            answer = EDIT.get((filename, idx), item["assistant"].strip())
            if question.casefold() in seen:
                continue
            seen.add(question.casefold())
            source = manifest[item["source"]]
            assert Path(source["path"]).exists(), source["path"]
            rows.append({
                "messages": [
                    {"role": "system", "content": (
                        "Bạn là tư vấn viên Shinhan Bank Việt Nam. Nói tiếng Việt tự nhiên, "
                        "xưng hô theo khách, trả lời đúng tài liệu được cung cấp. "
                        "Không tự nhận đã xem dữ liệu riêng của khách; không hứa duyệt hồ sơ. "
                        "Nếu thiếu biểu phí/lãi suất hiện hành, hướng dẫn khách kiểm tra kênh chính thức.\n\n"
                        "THÔNG TIN THAM KHẢO:\n" + item["approved_fact"]
                    )},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                "source_id": hashlib.sha256(item["source_url"].encode()).hexdigest()[:16],
                "source_file": item["source"] + ".pdf",
                "source_url": item["source_url"],
                "source_sha256": source["sha256"],
                "teacher": "qwen3.5:9b+human_review",
                "reviewed_by": "human_source_and_style_review",
                "region": item["region"],
                "scenario_id": "shinhan-" + item["topic"],
            })
    assert len(rows) >= 20, len(rows)
    OUTPUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(json.dumps({"approved": len(rows), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
