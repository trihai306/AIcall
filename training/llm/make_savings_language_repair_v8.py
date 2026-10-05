"""Source-grounded repairs for online-savings wording and rate composition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_threshold_curriculum import row


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for region, opener in (("miền Bắc", "Vâng"), ("miền Nam", "Dạ")):
        for title in ("cô", "chú", "bác"):
            for question in (
                "Gửi trên ứng dụng có hơn lãi tại quầy không?",
                "Nếu mở sổ bằng ứng dụng thì được cộng thêm mấy điểm phần trăm?",
                "Gửi online được thêm lãi thế nào?",
                "Tôi chỉ hỏi phần lãi cộng thêm khi gửi qua ứng dụng, bao nhiêu?",
            ):
                rows.append(row(
                    "tiet_kiem.md", f"Nói kiểu {region} nhé, gọi tôi là {title}. {question}",
                    f"{opener} {title}, gửi trên ứng dụng được cộng thêm 0,2 điểm phần trăm "
                    "một năm so với cùng kỳ hạn tại quầy ạ.",
                ))

    for months, counter_rate, app_rate in (
        (1, "3,5", "3,7"), (3, "3,8", "4,0"), (6, "4,5", "4,7"),
        (12, "5,5", "5,7"), (24, "5,8", "6,0"), (36, "6", "6,2"),
    ):
        previous = [
            {"role": "user", "content": f"Kỳ hạn {months} tháng gửi tại quầy lãi thế nào?"},
            {"role": "assistant", "content": f"Dạ, kỳ hạn {months} tháng tại quầy là {counter_rate}% một năm ạ."},
        ]
        for question in (
            "Nếu gửi trên ứng dụng thì tính ra lãi cuối cùng là bao nhiêu?",
            "Còn chuyển qua ứng dụng thì mức cụ thể của kỳ hạn đó là mấy phần trăm?",
            "Vậy gửi online, cộng thêm phần ưu đãi rồi, tôi nhận mức nào?",
        ):
            rows.append(row(
                "tiet_kiem.md", question,
                f"Dạ, kỳ hạn {months} tháng gửi trên ứng dụng là {app_rate}% một năm ạ; "
                f"mức {counter_rate}% tại quầy cộng thêm 0,2 điểm phần trăm.",
                previous,
            ))
    for item in rows:
        item.update(teacher="deterministic-source-repair", reviewed_by="manual-source-check",
                    style_review="savings-language-repair-v8")
        answer = item["messages"][-1]["content"]
        if len(answer.split()) > 35 or any(term in answer.lower() for term in ("online", "cashback")):
            raise ValueError(answer)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(s) for s in args.base.read_text(encoding="utf-8").splitlines() if s.strip()]
    rows = base + build_rows()
    args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
    print(f"{len(base)} prior + {len(rows)-len(base)} repairs = {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
