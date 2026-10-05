"""Add source-checked multi-turn age questions after 9B question generation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_threshold_curriculum import BASE_SYSTEM, source


def build_rows() -> list[dict]:
    rows = []
    for filename, product, ages, incomes, minimum, maximum in (
        ("vay_mua_nha.md", "vay mua nhà", (19, 20, 21, 22, 23, 65, 66), (12, 18, 30), 22, 65),
        ("the_tin_dung.md", "mở thẻ tín dụng", (17, 18, 20), (6, 12, 18), 18, None),
    ):
        content, source_id = source(filename)
        for age in ages:
            for income in incomes:
                question = (
                    f"Lương tôi {income} triệu một tháng rồi; vậy riêng tuổi của tôi "
                    f"có đạt điều kiện {product} chưa?"
                )
                reached = age >= minimum and (maximum is None or age <= maximum)
                if reached:
                    answer = (f"Dạ, {age} tuổi đã đạt riêng ngưỡng tuổi {product} ạ. "
                              "Các điều kiện khác vẫn cần xem xét.")
                else:
                    limit = (f"từ {minimum} đến {maximum} tuổi" if maximum is not None
                             else f"từ {minimum} tuổi")
                    answer = (f"Dạ, dù thu nhập {income} triệu một tháng, {age} tuổi "
                              f"chưa đạt điều kiện tuổi {product} ạ; tài liệu yêu cầu {limit}.")
                messages = [
                    {"role": "system", "content": BASE_SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + content},
                    {"role": "user", "content": f"Tôi {age} tuổi."},
                    {"role": "assistant", "content": "Dạ, em nghe rồi ạ. Anh/chị muốn hỏi điều kiện nào?"},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
                if len(answer.split()) > 35:
                    raise ValueError(answer)
                rows.append({"messages": messages, "source_id": source_id,
                             "source_file": filename, "teacher": "deterministic-source-comparison",
                             "reviewed_by": "manual-rule", "style_review": "multiturn-repair-v5"})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(line) for line in args.base.read_text(encoding="utf-8").splitlines() if line.strip()]
    extras = build_rows()
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in base + extras), encoding="utf-8")
    print(f"{len(base)} prior + {len(extras)} multi-turn repairs = {len(base)+len(extras)} -> {args.output}")


if __name__ == "__main__":
    main()
