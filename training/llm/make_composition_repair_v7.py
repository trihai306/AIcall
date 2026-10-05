"""Teach separate conditions and carry the product/term across a follow-up."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_threshold_curriculum import row


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for age in (22, 23, 24, 25, 64, 65):
        for income in (11, 14, 22):
            rows.append(row(
                "vay_mua_nha.md",
                f"Tôi {age} tuổi, lương {income} triệu nhưng chưa có tài sản bảo đảm. Vay nhà đã đủ điều kiện chưa?",
                f"Dạ, {age} tuổi đã đạt riêng điều kiện tuổi 22 đến 65 ạ. "
                "Nhưng mình chưa có tài sản bảo đảm nên chưa đủ điều kiện vay nhà.",
            ))

    for card, fee in (("Classic", "200.000"), ("Gold", "400.000"),
                      ("Platinum", "800.000")):
        for wording in (
            "Thế năm thứ hai phí bao nhiêu?",
            "Tôi chỉ hỏi phí thường niên từ năm thứ hai.",
            "Sau năm đầu miễn phí, tôi trả bao nhiêu mỗi năm?",
            "Năm kế tiếp của thẻ này có phí thế nào?",
            "Đừng nhắc lại năm đầu; năm thứ hai là bao nhiêu?",
        ):
            rows.append(row(
                "the_tin_dung.md", wording,
                f"Dạ, từ năm thứ hai thẻ {card} có phí thường niên {fee} đồng một năm ạ.",
                [{"role": "user", "content": f"Năm đầu của thẻ {card} có phí thường niên không?"},
                 {"role": "assistant", "content": "Dạ, năm đầu được miễn phí thường niên ạ."}],
            ))

    for region in ("miền Bắc", "miền Nam"):
        for title in ("cô", "chú"):
            for wording in ("Gửi trên ứng dụng được cộng thêm lãi bao nhiêu?",
                            "Mở sổ trên ứng dụng hơn tại quầy mấy điểm phần trăm?"):
                opener = "Vâng" if region == "miền Bắc" else "Dạ"
                rows.append(row(
                    "tiet_kiem.md", f"Nói kiểu {region} giúp {title}. {wording}",
                    f"{opener} {title}, gửi trên ứng dụng được cộng thêm "
                    "0,2 điểm phần trăm một năm so với gửi tại quầy ạ.",
                ))

    for months, counter_rate, app_rate in (
        (1, "3,5", "3,7"), (3, "3,8", "4,0"), (6, "4,5", "4,7"),
        (12, "5,5", "5,7"), (24, "5,8", "6,0"), (36, "6", "6,2"),
    ):
        for wording in ("Nếu gửi trên ứng dụng thì lãi cuối cùng là bao nhiêu?",
                        "Chuyển sang gửi trên ứng dụng, mức mới là mấy phần trăm?"):
            rows.append(row(
                "tiet_kiem.md", wording,
                f"Dạ, kỳ hạn {months} tháng gửi trên ứng dụng là {app_rate}% một năm ạ, "
                f"gồm mức {counter_rate}% tại quầy cộng thêm 0,2 điểm phần trăm.",
                [{"role": "user", "content": f"Kỳ hạn {months} tháng tại quầy lãi bao nhiêu?"},
                 {"role": "assistant", "content": f"Dạ, kỳ hạn {months} tháng tại quầy là {counter_rate}% một năm ạ."}],
            ))

    for item in rows:
        item.update(teacher="deterministic-source-repair", reviewed_by="manual-source-check",
                    style_review="composition-repair-v7")
        answer = item["messages"][-1]["content"]
        if len(answer.split()) > 35 or any(term in answer.lower() for term in ("online", "cashback")):
            raise ValueError(answer)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(line) for line in args.base.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = base + build_rows()
    args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
                           encoding="utf-8")
    print(f"{len(base)} prior + {len(rows) - len(base)} repairs = {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
