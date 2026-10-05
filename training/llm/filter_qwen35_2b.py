"""Final deterministic gate after both Qwen 9B review passes."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from distill_qwen35_2b import ROOT

BLOCKED = {
    'kiểm tra giúp': 'hứa tự kiểm tra hồ sơ',
    'tốt nhất thị trường': 'tuyên bố so sánh thị trường chưa chứng minh',
    'tốp cao trên thị trường': 'tuyên bố so sánh thị trường chưa chứng minh',
    'không ngân hàng nào': 'khẳng định tuyệt đối về ngân hàng khác',
    'tốt nhất thị trường': 'so sánh thị trường chưa được kiểm chứng',
    'mức ưu đãi tốt nhất': 'so sánh thị trường chưa được kiểm chứng',
    'chưa có chính sách': 'suy từ việc tài liệu không đề cập',
    'không có trường hợp ngoại lệ': 'suy từ việc tài liệu không đề cập',
    'md không': 'văn phong nhắc tên định dạng tài liệu',
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_final.jsonl')
    ap.add_argument('--output', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_train.jsonl')
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    kept = []
    rejected: Counter[str] = Counter()
    seen = set()
    for row in rows:
        answer = row['messages'][-1]['content'].casefold()
        reason = next((reason for phrase, reason in BLOCKED.items()
                       if phrase in answer), None)
        key = (row['source_id'], row['messages'][-2]['content'].casefold())
        if not reason and key in seen:
            reason = 'mẫu trùng'
        if reason:
            rejected[reason] += 1
            continue
        seen.add(key)
        kept.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n'
                                   for row in kept), encoding='utf-8')
    print(json.dumps({'input': len(rows), 'kept': len(kept),
                      'rejected': dict(rejected), 'output': str(args.output)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
