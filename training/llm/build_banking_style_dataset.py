"""Build a source-grounded, manually edited style candidate from reviewed rows.

The 9B automatic rewrites are deliberately excluded: a smoother sentence can
quietly turn a product limit into an approval promise.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

STYLE_EDITS = {
    1: "Dạ, năm đầu thẻ được miễn phí thường niên ạ.",
    2: "Dạ, thời gian miễn lãi tối đa là 55 ngày ạ.",
    3: "Dạ, hạn mức thẻ từ 10 đến 500 triệu đồng ạ.",
    4: "Nếu anh muốn hạn mức tối đa 500 triệu thì có thể xem thẻ Platinum ạ. Loại này có hạn mức từ 100 đến 500 triệu.",
    5: "Thẻ Classic có phí thường niên thấp nhất, 200.000đ/năm ạ.",
    6: "Dạ, thẻ Gold có hạn mức từ 30 đến 200 triệu đồng, phí thường niên 400.000đ/năm ạ.",
    7: "Chưa được ạ, thẻ tín dụng yêu cầu người mở đủ 18 tuổi trở lên.",
    8: "Mức tối thiểu là 5 triệu đồng/tháng ạ. Thu nhập 4 triệu của anh/chị hiện chưa đạt điều kiện này.",
    9: "Anh/chị đã có CCCD rồi; phần còn lại cần chứng minh thu nhập ổn định từ 5 triệu đồng/tháng ạ.",
    10: "Dạ, tài liệu yêu cầu thu nhập từ 5 triệu đồng/tháng. Nếu chưa đạt mức này thì hiện chưa đủ điều kiện thu nhập để mở thẻ ạ.",
    11: "Dạ có ạ, các loại thẻ trong tài liệu đều được miễn phí thường niên năm đầu.",
    12: "Giao dịch ăn uống được hoàn 3% ạ.",
    13: "Gửi tiết kiệm là mình gửi tiền vào ngân hàng để nhận lãi; vay thì mình nhận tiền từ ngân hàng ạ.",
    15: "Dạ, tiết kiệm không kỳ hạn đang có lãi suất 0.5%/năm ạ.",
    17: "Gửi qua app được cộng thêm 0.2%/năm so với gửi tại quầy ạ.",
    18: "Anh/chị có thể mở sổ trên ứng dụng trong 5 phút, không cần ra quầy ạ.",
    19: "Dạ, anh/chị có thể tất toán online bất kỳ lúc nào ạ.",
    91: "Chưa đạt điều kiện tuổi ạ. Tài liệu yêu cầu từ 22 đến 65 tuổi, còn anh/chị mới 20 tuổi.",
    92: "Mức 8 triệu chưa đạt điều kiện thu nhập ạ; tài liệu yêu cầu từ 10 triệu đồng mỗi tháng.",
    96: "Dạ, chỉ phần rút trước hạn hưởng lãi không kỳ hạn 0.5%/năm; phần còn lại vẫn giữ lãi suất ban đầu ạ.",
    98: "Chưa được ạ, tài liệu yêu cầu đủ 18 tuổi để mở thẻ.",
    99: "Chưa ạ. Trả trước 3 năm vẫn có phí 1-2% số tiền trả trước; sau 3 năm mới được miễn phí.",
}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--repairs", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = read_rows(args.base)
    if len(rows) != 100:
        raise SystemExit(f"Expected 100 reviewed rows, got {len(rows)}")
    for i, answer in STYLE_EDITS.items():
        rows[i]["messages"][-1]["content"] = answer
        rows[i]["style_review"] = "manual"
    repairs = read_rows(args.repairs)
    for row in repairs:
        row["reviewed_by"] = "manual-source-check"
        row["style_review"] = "manual"
    rows.extend(repairs)
    # Same grounded answer in three registers. The TTS reference voice, if any,
    # is selected separately; these examples teach wording and turn-taking.
    for index, fact_answers in (
        (2, {
            "miền Bắc": "Vâng, thời gian miễn lãi tối đa là 55 ngày ạ.",
            "miền Nam": "Dạ, thẻ được miễn lãi tối đa 55 ngày đó anh/chị.",
            "trung tính": "Dạ, thời gian miễn lãi tối đa là 55 ngày ạ.",
        }),
        (5, {
            "miền Bắc": "Vâng, thẻ Classic có phí thường niên thấp nhất, 200.000đ/năm ạ.",
            "miền Nam": "Dạ, thẻ Classic có phí thường niên thấp nhất, 200.000đ/năm đó anh/chị.",
            "trung tính": "Dạ, phí thường niên thấp nhất là thẻ Classic, 200.000đ/năm ạ.",
        }),
    ):
        for region, answer in fact_answers.items():
            variant = copy.deepcopy(rows[index])
            variant["messages"][-2]["content"] = (
                f"Em nói theo cách {region} giúp anh/chị nhé. " + variant["messages"][-2]["content"]
            )
            variant["messages"][-1]["content"] = answer
            variant["style_review"] = "manual-region"
            rows.append(variant)
    before_filter = len(rows)
    rows = [row for row in rows if len(row["messages"][-1]["content"].split()) <= 35]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"{len(rows)} rows; {len(STYLE_EDITS)} style edits, {len(repairs)} factual repairs, "
          f"{before_filter-len(rows)} long answers removed -> {args.output}")


if __name__ == "__main__":
    main()
