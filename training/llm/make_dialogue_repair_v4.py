"""Targeted human-written repairs for held-out conversation failures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from make_natural_dialogue_curriculum import REGIONS, SYSTEM
from make_threshold_curriculum import source

STOP_QUESTIONS = [
    "Thôi, tôi đổi ý, không vay nữa.",
    "Tôi không muốn tiếp tục nghe tư vấn vay.",
    "Dừng lại nhé, tôi chưa cần khoản vay.",
    "Cảm ơn, để hôm khác tôi xem.",
    "Đừng hỏi thêm về hồ sơ của tôi nữa.",
    "Tôi đã nói là ngừng tư vấn rồi.",
    "Không giới thiệu vay nữa, cảm ơn.",
    "Tôi chỉ hỏi cho biết, giờ kết thúc nhé.",
    "Thôi nhé, tôi không muốn làm hồ sơ.",
    "Để tôi tự cân nhắc, em dừng ở đây.",
    "Tôi bận rồi, chào em.",
    "Không gọi thêm, tôi không có nhu cầu vay.",
]
STOP_ANSWERS = (
    "Vâng, em hiểu ạ. Em xin dừng tư vấn ở đây, cảm ơn đã dành thời gian nghe máy.",
    "Dạ, em hiểu rồi. Em dừng trao đổi ở đây nha, cảm ơn đã nghe máy ạ.",
    "Dạ, em hiểu. Em xin kết thúc cuộc trao đổi tại đây, cảm ơn đã nghe máy ạ.",
)

AGE_QUESTIONS = [
    (18, "Tôi vừa tròn 18 tuổi, điều kiện tuổi mở thẻ thế nào?"),
    (18, "Em mới 18, tuổi đó đã đủ để xin mở thẻ chưa?"),
    (19, "Con tôi 19 tuổi, riêng tuổi có được mở thẻ tín dụng không?"),
    (19, "Tôi 19 tuổi nhưng chưa nói thu nhập, riêng tuổi đã đạt chưa?"),
    (20, "Tôi hai mươi tuổi, mức tuổi của thẻ có phù hợp không?"),
    (20, "Đã 20 tuổi rồi thì riêng điều kiện tuổi của thẻ đạt chứ?"),
    (21, "Em 21 tuổi, xét tuổi thôi thì mở thẻ được không?"),
    (21, "Con tôi 21, tuổi đó có thấp hơn mức tối thiểu mở thẻ không?"),
    (16, "Tôi 16 tuổi, có đủ tuổi để mở thẻ tín dụng chưa?"),
    (17, "Em 17 tuổi, chỉ xét tuổi thì đã đạt chưa?"),
    (22, "Tôi 22 tuổi, ngưỡng tuổi mở thẻ có đạt không?"),
    (23, "Con tôi 23, riêng điều kiện tuổi của thẻ thì sao?"),
]

ADDRESS_CASES = [
    ("the_tin_dung.md", "Cô muốn xem thẻ Classic có hạn mức bao nhiêu.", "cô", "thẻ Classic có hạn mức từ 10 đến 50 triệu đồng"),
    ("the_tin_dung.md", "Chú hỏi phí thường niên thẻ Platinum.", "chú", "phí thường niên thẻ Platinum là 800.000 đồng một năm"),
    ("the_tin_dung.md", "Bác cần biết thẻ Classic năm đầu tính phí không.", "bác", "năm đầu thẻ Classic được miễn phí thường niên"),
    ("the_tin_dung.md", "Nói giúp cô thời gian miễn lãi của thẻ nhé.", "cô", "thẻ có thời gian miễn lãi tối đa 55 ngày"),
    ("tiet_kiem.md", "Chú định gửi 6 tháng, lãi suất tại quầy thế nào?", "chú", "kỳ hạn 6 tháng tại quầy có lãi suất 4,5% một năm"),
    ("tiet_kiem.md", "Bác muốn biết mức gửi thấp nhất.", "bác", "mức gửi tối thiểu là một triệu đồng"),
    ("tiet_kiem.md", "Cô hỏi gửi không kỳ hạn được lãi bao nhiêu.", "cô", "lãi suất không kỳ hạn là 0,5% một năm"),
    ("tiet_kiem.md", "Nói cho chú về mở sổ trên ứng dụng.", "chú", "có thể mở sổ trên ứng dụng trong 5 phút, không cần ra quầy"),
    ("vay_tin_chap.md", "Bác hỏi thời hạn vay tín chấp.", "bác", "thời hạn vay tín chấp từ 12 đến 60 tháng"),
    ("vay_tin_chap.md", "Cô muốn biết hồ sơ cần sao kê mấy tháng.", "cô", "hồ sơ vay tín chấp cần sao kê lương 3 tháng gần nhất"),
    ("vay_tin_chap.md", "Chú hỏi vay tín chấp có phải thế chấp nhà không.", "chú", "vay tín chấp không yêu cầu thế chấp tài sản"),
    ("the_tin_dung.md", "Bác hỏi ưu đãi ăn uống của thẻ.", "bác", "chi tiêu ăn uống được hoàn tiền 3%"),
]


def row(filename: str, question: str, answer: str, region: str) -> dict:
    content, source_id = source(filename)
    messages = [
        {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + content},
        {"role": "user", "content": f"Em nói theo cách {region} nhé. {question}"},
        {"role": "assistant", "content": answer},
    ]
    if len(answer.split()) > 35:
        raise ValueError(answer)
    return {"messages": messages, "source_id": source_id, "source_file": filename,
            "teacher": "human-written", "reviewed_by": "manual-source-check",
            "style_review": "dialogue-repair-v4"}


def build_rows() -> list[dict]:
    rows = []
    for question in STOP_QUESTIONS:
        rows.extend(row("vay_tin_chap.md", question, answer, region)
                    for region, answer in zip(REGIONS, STOP_ANSWERS, strict=True))
    for age, question in AGE_QUESTIONS:
        for region in REGIONS:
            opener = "Vâng" if region == "miền Bắc" else "Dạ"
            if age >= 18:
                answer = (f"{opener}, {age} tuổi đã đạt riêng điều kiện tuổi mở thẻ từ 18 tuổi ạ. "
                          "Các điều kiện khác vẫn cần xét riêng.")
            else:
                answer = f"{opener}, {age} tuổi chưa đạt điều kiện tuổi mở thẻ ạ; tài liệu yêu cầu từ 18 tuổi."
            rows.append(row("the_tin_dung.md", question, answer, region))
    for filename, question, title, fact in ADDRESS_CASES:
        for region in REGIONS:
            opener = "Vâng" if region == "miền Bắc" else "Dạ"
            rows.append(row(filename, question, f"{opener} {title}, {fact} ạ.", region))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(line) for line in args.base.read_text(encoding="utf-8").splitlines() if line.strip()]
    repairs = build_rows()
    rows = base + repairs
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"{len(base)} prior + {len(repairs)} repairs = {len(rows)} rows -> {args.output}")


if __name__ == "__main__":
    main()
