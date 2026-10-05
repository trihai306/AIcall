"""Repair contradictory threshold answers and spoken Vietnamese in a candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_threshold_curriculum import row


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for age in (19, 20, 23, 24, 65, 66):
        reached = 22 <= age <= 65
        decision = "đã đạt riêng điều kiện tuổi" if reached else "chưa đạt điều kiện tuổi"
        answer = (f"Dạ, {age} tuổi {decision} của gói vay nhà ạ; "
                  "mức trong tài liệu là từ 22 đến 65 tuổi.")
        for income in (11, 19, 28):
            question = (f"Em {age} tuổi, lương {income} triệu một tháng. "
                        "Chỉ xét tuổi thì có qua điều kiện vay mua nhà không?")
            rows.append(row("vay_mua_nha.md", question, answer))

    for months, counter_rate in ((1, "3,5"), (3, "3,8"), (6, "4,5"),
                                 (12, "5,5"), (24, "5,8"), (36, "6")):
        for region in ("miền Bắc", "miền Nam"):
            question = (f"Nói kiểu {region} nhé. Tôi gửi {months} tháng trên ứng dụng, "
                        "được cộng bao nhiêu lãi so với tại quầy?")
            answer = ("Vâng" if region == "miền Bắc" else "Dạ") + (
                f", gửi trên ứng dụng được cộng thêm 0,2 điểm phần trăm một năm "
                f"so với mức {counter_rate}% tại quầy ạ.")
            rows.append(row("tiet_kiem.md", question, answer))

    for amount in (80, 120, 200, 350):
        for customer in ("anh", "chị", "cô"):
            question = (f"{customer.capitalize()} đang tính vay {amount} triệu. "
                        "Lãi từ 7,9% là chắc chắn cho hồ sơ của tôi chứ?")
            answer = (f"Dạ {customer}, 7,9% một năm là mức khởi điểm trong tài liệu, "
                      "chưa thể xác định lãi áp dụng cho hồ sơ của mình ạ.")
            rows.append(row("vay_tin_chap.md", question, answer))

    for item in rows:
        item.update(teacher="deterministic-source-repair", reviewed_by="manual-source-check",
                    style_review="dialogue-repair-v6")
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
