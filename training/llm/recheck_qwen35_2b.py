"""Independent second Qwen 9B pass over every accepted banking training row."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from distill_qwen35_2b import ROOT, ask, safe_numbers

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SYSTEM = (
    "Bạn đang kiểm định LẦN HAI một mẫu sẽ dạy AI tư vấn ngân hàng. Đừng mặc "
    "định lần duyệt trước đúng. Soi từng khẳng định theo nguyên văn MD: số, "
    "đơn vị, điều kiện, thời điểm, đối tượng, mức chắc chắn. Từ chối nếu câu "
    "trả lời thêm một chi tiết không có trong MD hoặc lời khách, nói sai ý, "
    "né câu hỏi dù nguồn có câu trả lời, hứa đã/sẽ làm việc chưa thực hiện, "
    "hay nói như mẫu máy móc. Nguồn im lặng thì phải nói thiếu thông tin; "
    "không suy ra điều kiện mới. Chỉ nhận nếu tự tin. JSON: "
    "{\"accept\":true hoặc false,\"reason\":\"lý do cụ thể\"}."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_verified.jsonl')
    ap.add_argument('--output', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_final.jsonl')
    ap.add_argument('--audit', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_recheck.jsonl')
    ap.add_argument('--model', default='qwen3.5:9b')
    ap.add_argument('--url', default='http://127.0.0.1:11434')
    ap.add_argument('--allow-derived-numbers', action='store_true',
                    help='Cho phép số tính từ nguồn; để 9B kiểm tra phép tính')
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checked = set()
    if args.audit.exists():
        for line in args.audit.read_text(encoding='utf-8').splitlines():
            try:
                checked.add(json.loads(line)['row_id'])
            except (KeyError, json.JSONDecodeError):
                pass
    existing = set()
    if args.output.exists():
        for line in args.output.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
                existing.add((row['source_id'], row['messages'][-2]['content']))
            except (KeyError, IndexError, json.JSONDecodeError):
                pass
    with args.output.open('a', encoding='utf-8') as out, args.audit.open('a', encoding='utf-8') as audit:
        for i, row in enumerate(rows, 1):
            messages = row['messages']
            user = messages[-2]['content']
            answer = messages[-1]['content']
            source = messages[0]['content'].split('THÔNG TIN THAM KHẢO:\n', 1)[-1]
            row_id = f"{row['source_id']}:{user}"
            if row_id in checked:
                continue
            if not args.allow_derived_numbers and not safe_numbers(user, answer, source):
                verdict = {'accept': False, 'reason': 'số không có trong nguồn/lời khách'}
            elif 'giờ làm việc' in answer.lower() and 'giờ làm việc' not in source.lower():
                verdict = {'accept': False, 'reason': 'tự thêm điều kiện giờ làm việc'}
            elif 'em sẽ kiểm tra' in answer.lower() or 'chúng tôi sẽ kiểm tra' in answer.lower():
                verdict = {'accept': False, 'reason': 'hứa kiểm tra khi chưa có công cụ/ kết quả'}
            else:
                try:
                    verdict = ask(args.url, args.model, SYSTEM,
                                  f'MD:\n{source}\n\nKHÁCH: {user}\nTRẢ LỜI: {answer}', 320)
                except (ValueError, TimeoutError) as exc:
                    verdict = {'accept': False, 'reason': f'kiểm định lỗi: {type(exc).__name__}'}
            accepted = verdict.get('accept') is True
            audit.write(json.dumps({'row_id': row_id, 'accept': accepted,
                                    'verdict': verdict}, ensure_ascii=False) + '\n')
            audit.flush()
            if accepted and (row['source_id'], user) not in existing:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                existing.add((row['source_id'], user))
            print(f'[{i}/{len(rows)}] {"GIỮ" if accepted else "LOẠI"}: {verdict.get("reason", "")}', flush=True)


if __name__ == '__main__':
    main()
