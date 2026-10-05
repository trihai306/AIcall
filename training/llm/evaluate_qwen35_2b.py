"""Have Qwen 9B audit a 2B candidate on source-held-out banking questions."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from distill_qwen35_2b import ask, safe_numbers

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[2]
JUDGE = (
    "Bạn là kiểm định viên ngân hàng. Chấm câu trả lời CANDIDATE theo câu hỏi "
    "KHÁCH và đúng đoạn MD. Câu THAM KHẢO chỉ là một cách trả lời, không phải "
    "khuôn bắt buộc. Pass khi câu trả lời giải quyết đúng ý khách, đủ những "
    "dữ kiện liên quan trực tiếp, mọi khẳng định nghiệp vụ có căn cứ, không "
    "hứa thao tác chưa làm và tiếng Việt tự nhiên. Không bắt liệt kê toàn bộ "
    "MD khi khách chỉ hỏi một phần; chấp nhận cách diễn đạt khác. Fail khi "
    "bỏ sót chi tiết được hỏi, nhầm điều kiện/con số, hoặc chỉ nói chung dù "
    "MD có ví dụ trực tiếp. Nếu MD không đủ để kết luận thì câu trả lời phải "
    "nói rõ giới hạn và có thể hỏi thêm một ý cụ thể. "
    "JSON: {\"pass\":true hoặc false,\"reason\":\"...\"}."
)


def chat(url: str, model: str, messages: list[dict]) -> str:
    payload = json.dumps({
        'model': model, 'messages': messages, 'stream': False, 'think': False,
        'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 180},
        'keep_alive': '10m',
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url.rstrip('/') + '/api/chat', data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        outer = json.load(response)
    return str((outer.get('message') or {}).get('content') or '').strip()


def holdout(rows: list[dict], ratio: float = 0.1) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row['source_id']].append(row)
    shuffled = list(groups.values())
    random.Random(42).shuffle(shuffled)
    target = max(1, round(len(rows) * ratio))
    result: list[dict] = []
    for group in shuffled:
        if len(result) >= target:
            break
        result.extend(group)
    if len(result) == len(rows) and len(shuffled) > 1:
        del result[-len(shuffled[-1]):]
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_verified.jsonl')
    ap.add_argument('--model', default='banking-qwen35-2b-candidate')
    ap.add_argument('--teacher', default='qwen3.5:9b')
    ap.add_argument('--url', default='http://127.0.0.1:11434')
    ap.add_argument('--output', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_eval.json')
    ap.add_argument('--max-cases', type=int, default=16)
    ap.add_argument('--all-rows', action='store_true',
                    help='Chấm toàn bộ file benchmark thay vì chỉ source holdout')
    ap.add_argument('--allow-derived-numbers', action='store_true',
                    help='Cho phép số được tính từ các số trong nguồn; nhờ 9B kiểm tra phép tính')
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    cases = (rows if args.all_rows else holdout(rows))[:args.max_cases]
    results = []
    for i, row in enumerate(cases, 1):
        messages = row['messages']
        source = messages[0]['content'].split('THÔNG TIN THAM KHẢO:\n', 1)[-1]
        user = messages[-2]['content']
        reference = messages[-1]['content']
        answer = chat(args.url, args.model, messages[:-1])
        if row.get('forbid_match') and re.search(row['forbid_match'], answer, re.I):
            verdict = {'pass': False, 'reason': 'chứa mệnh đề bị cấm của ca kiểm tra'}
        elif row.get('must_match') and not re.search(row['must_match'], answer, re.I):
            verdict = {'pass': False, 'reason': 'thiếu kết luận bắt buộc của ca kiểm tra'}
        elif not args.allow_derived_numbers and not safe_numbers(user, answer, source):
            verdict = {'pass': False, 'reason': 'con số không có trong nguồn/lời khách'}
        else:
            verdict = ask(args.url, args.teacher, JUDGE,
                          f'MD:\n{source}\n\nKHÁCH: {user}\nTHAM KHẢO: {reference}\nCANDIDATE: {answer}', 250)
        results.append({'source_id': row['source_id'], 'question': user,
                        'reference': reference, 'answer': answer, 'verdict': verdict})
        print(f'[{i}/{len(cases)}] {"PASS" if verdict.get("pass") is True else "FAIL"}: {user}', flush=True)
    summary = {'model': args.model, 'teacher': args.teacher,
               'total': len(results),
               'passed': sum(r['verdict'].get('pass') is True for r in results),
               'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{summary["passed"]}/{summary["total"]} passed; {args.output}', flush=True)


if __name__ == '__main__':
    main()
