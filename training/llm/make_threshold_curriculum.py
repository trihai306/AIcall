"""Add contrastive, source-grounded threshold examples to a style candidate.

The held-out smoke values (mortgage 21, card 17, debt settled 8 months) are
never used as new targets here. This tests whether the small model generalizes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SYSTEM = (
    "Bạn là tư vấn viên ngân hàng. Chỉ khẳng định dữ kiện trong THÔNG TIN "
    "THAM KHẢO hoặc lời khách. Đối chiếu điều kiện với hoàn cảnh khách; "
    "không hứa duyệt hồ sơ. Xưng em, trả lời tự nhiên trong 1-2 câu."
)


def source(filename: str) -> tuple[str, str]:
    content = (ROOT / "knowledge/products" / filename).read_text(encoding="utf-8-sig").strip()
    source_id = hashlib.sha256((filename + content).encode()).hexdigest()[:16]
    return content, source_id


def row(filename: str, user: str, answer: str, previous: list[dict] | None = None) -> dict:
    content, source_id = source(filename)
    messages = [{"role": "system", "content": BASE_SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + content}]
    messages.extend(previous or [])
    messages.extend([{"role": "user", "content": user}, {"role": "assistant", "content": answer}])
    return {"messages": messages, "source_id": source_id,
            "source_file": filename, "teacher": "deterministic-source-comparison",
            "reviewed_by": "manual-rule"}


def build_extra() -> list[dict]:
    rows: list[dict] = []
    for age in (18, 19, 20, 22, 23, 24, 65, 66):
        reached = 22 <= age <= 65
        answer = (f"Dạ, {age} tuổi nằm trong khoảng 22 đến 65 tuổi của gói vay nhà ạ; "
                  "hồ sơ còn phải xét các điều kiện khác." if reached else
                  f"Dạ, {age} tuổi chưa đạt điều kiện tuổi vay nhà ạ; tài liệu yêu cầu từ 22 đến 65 tuổi.")
        for question in (
            f"Tôi {age} tuổi, riêng điều kiện tuổi vay mua nhà đã đạt chưa?",
            f"Nếu tôi mới {age} tuổi thì ngưỡng tuổi của gói vay nhà có phù hợp không?",
        ):
            rows.append(row("vay_mua_nha.md", question, answer))

    for age in (15, 16, 18, 19, 20):
        reached = age >= 18
        answer = (f"Dạ, {age} tuổi đã đạt riêng ngưỡng tuổi mở thẻ, vì tài liệu yêu cầu từ 18 tuổi ạ. "
                  "Các điều kiện khác vẫn cần kiểm tra." if reached else
                  f"Dạ, {age} tuổi chưa đạt ngưỡng mở thẻ ạ; tài liệu yêu cầu từ 18 tuổi.")
        for question in (
            f"Con tôi {age} tuổi, điều kiện tuổi để mở thẻ tín dụng đã đạt chưa?",
            f"Tôi {age} tuổi và có thu nhập ổn, riêng tuổi mở thẻ được chưa?",
        ):
            rows.append(row("the_tin_dung.md", question, answer))

    for months in (3, 6, 7, 9, 10, 11, 12, 13, 14, 16):
        answer = (f"Dạ, tất toán {months} tháng chưa qua mốc trên 1 năm, "
                  "nên chưa thuộc trường hợp có thể xem xét theo điều kiện này ạ."
                  if months <= 12 else
                  f"Dạ, {months} tháng đã qua mốc trên 1 năm; hồ sơ có thể được xem xét, "
                  "nhưng chưa thể hứa được duyệt ạ.")
        for question in (
            f"Nợ xấu của tôi đã tất toán {months} tháng. Đã qua mốc để được xem xét chưa?",
            f"Tôi trả hết nợ xấu cách đây {months} tháng, đã thuộc diện trên 1 năm chưa?",
        ):
            rows.append(row("vay_tin_chap.md", question, answer))

    for age in (20, 23, 66):
        previous = [
            {"role": "user", "content": f"Tôi {age} tuổi."},
            {"role": "assistant", "content": "Dạ, em nghe rồi ạ. Anh/chị muốn hỏi điều kiện nào của gói vay nhà?"},
        ]
        answer = (f"Dạ, {age} tuổi đạt riêng ngưỡng tuổi 22 đến 65 của gói vay nhà ạ. "
                  "Mình vẫn cần xét các điều kiện còn lại." if 22 <= age <= 65 else
                  f"Dạ, dù thu nhập ổn, {age} tuổi chưa đạt điều kiện tuổi 22 đến 65 của gói vay nhà ạ.")
        rows.append(row("vay_mua_nha.md",
                        "Lương tôi 18 triệu mỗi tháng, vậy riêng điều kiện tuổi đạt chưa?",
                        answer, previous))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(line) for line in args.base.read_text(encoding="utf-8").splitlines() if line.strip()]
    extras = build_extra()
    rows = base + extras
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(f"{len(base)} base + {len(extras)} comparisons = {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
