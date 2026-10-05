"""Create source-grounded banking SFT examples; Qwen 9B audits every example.

This prepares a *candidate* dataset only. It never changes the live model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM = (
    "Bạn là tư vấn viên ngân hàng. Chỉ khẳng định dữ kiện có trong THÔNG TIN "
    "THAM KHẢO hoặc lời khách. Đối chiếu điều kiện với hoàn cảnh khách; thiếu "
    "dữ kiện thì hỏi đúng một ý. Không hứa phê duyệt, kiểm tra hồ sơ hay liên "
    "hệ lại nếu chưa thực hiện. Khi nguồn có ví dụ trả góp đúng câu hỏi, nêu "
    "con số và điều kiện của ví dụ, không coi đó là cam kết cho khách. Khi "
    "khách hỏi giấy tờ, xác định thứ họ đã có và chỉ nói phần còn thiếu hoặc "
    "liên quan; nếu hỏi toàn bộ hồ sơ thì liệt kê đủ theo nguồn. Khi khách "
    "nêu tuổi hoặc thu nhập, nói rõ trường hợp của họ đạt hay chưa đạt ngưỡng "
    "trong nguồn, không chỉ đọc lại ngưỡng. Trả lời tự "
    "nhiên bằng tiếng Việt, tối đa 2 câu."
)
GENERATOR = (
    "Dựa CHỈ trên đoạn MD dưới đây, tạo 4 tình huống khách hỏi tự nhiên và "
    "câu trả lời ngắn của tư vấn viên. Gồm ít nhất một câu hỏi về điều kiện "
    "hoặc trường hợp thiếu thông tin nếu nguồn cho phép. Không chép lại câu "
    "trong tài liệu thành lời khách. Không tự thêm lãi suất, điều kiện, thủ tục. "
    "Trả JSON: {\"cases\":[{\"user\":\"...\",\"answer\":\"...\"}]}"
)
REVIEWER = (
    "Bạn là kiểm định viên độc lập. Đọc ĐÚNG đoạn nguồn, câu khách và câu trả "
    "lời. Chỉ chấp nhận nếu mọi khẳng định về nghiệp vụ được nguồn hỗ trợ; "
    "đối chiếu ngưỡng/đơn vị/chủ thể, không biến mức sản phẩm thành mức đã "
    "duyệt cho khách. Từ chối câu hứa thao tác chưa làm, câu né tránh khi "
    "nguồn đã đủ để trả lời, và văn phong máy móc. Nếu không chắc, từ chối. "
    "Trả JSON: {\"accept\":true hoặc false,\"reason\":\"lý do ngắn\"}."
)


def sections(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    title = next((line.strip('# ').strip() for line in text.splitlines()
                  if line.startswith('# ')), path.stem)
    parts = re.split(r"(?=^##\s)", text, flags=re.MULTILINE)
    return [(f"{path.name}: {title}", part.strip()) for part in parts
            if len(part.strip()) >= 70]


def ask(url: str, model: str, system: str, user: str, predict: int,
        retry: bool = True) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False, "format": "json", "think": False,
        "options": {"temperature": 0, "num_ctx": 4096,
                    "num_predict": predict},
        "keep_alive": "15m",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url.rstrip('/') + '/api/chat', data=payload,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        outer = json.load(response)
    try:
        return json.loads((outer.get("message") or {}).get("content") or "{}")
    except json.JSONDecodeError:
        if not retry:
            raise
        return ask(url, model, system, user, min(predict * 2, 1800), False)


def safe_numbers(user: str, answer: str, source: str) -> bool:
    """Reject novel numeric claims before calling the more nuanced teacher judge."""
    pattern = r"\d+(?:[.,]\d+)*\s*%?"
    known = {x.replace(' ', '') for x in re.findall(pattern, user + '\n' + source)}
    return all(x.replace(' ', '') in known for x in re.findall(pattern, answer))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--knowledge', type=Path, default=ROOT / 'knowledge')
    ap.add_argument('--output', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_verified.jsonl')
    ap.add_argument('--audit', type=Path,
                    default=ROOT / 'data/training/qwen35_2b_audit.jsonl')
    ap.add_argument('--model', default='qwen3.5:9b')
    ap.add_argument('--url', default='http://127.0.0.1:11434')
    ap.add_argument('--max-sections', type=int, default=0)
    args = ap.parse_args()
    sources = sorted(args.knowledge.rglob('*.md'))
    groups = [(label, source) for path in sources for label, source in sections(path)]
    if args.max_sections:
        groups = groups[:args.max_sections]
    if not groups:
        raise SystemExit('Không có đoạn MD đủ nội dung để tạo dữ liệu')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.audit.exists():
        for line in args.audit.read_text(encoding='utf-8').splitlines():
            try:
                done.add(json.loads(line)['section_id'])
            except (KeyError, json.JSONDecodeError):
                pass
    existing_keys = set()
    if args.output.exists():
        for line in args.output.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
                existing_keys.add((row['source_id'], row['messages'][-2]['content']))
            except (KeyError, IndexError, json.JSONDecodeError):
                pass
    kept = rejected = 0
    with args.output.open('a', encoding='utf-8') as out, args.audit.open('a', encoding='utf-8') as audit:
        for index, (label, source) in enumerate(groups, 1):
            section_id = hashlib.sha256((label + source).encode()).hexdigest()[:16]
            if section_id in done:
                continue
            print(f'[{index}/{len(groups)}] {label} {section_id}', flush=True)
            try:
                generated = ask(args.url, args.model, GENERATOR,
                                f'NGUỒN: {label}\n{source}', 750)
                cases = generated.get('cases') or []
                if not isinstance(cases, list):
                    cases = []
                audit_rows = []
                for item in cases[:4]:
                    user = str(item.get('user') or '').strip()
                    answer = str(item.get('answer') or '').strip()
                    reason = ''
                    if len(user) < 8 or len(answer) < 8 or len(answer.split()) > 55:
                        reason = 'độ dài hoặc định dạng không hợp lệ'
                    elif not safe_numbers(user, answer, source):
                        reason = 'có con số không xuất hiện trong nguồn/lời khách'
                    if reason:
                        verdict = {'accept': False, 'reason': reason}
                    else:
                        try:
                            verdict = ask(args.url, args.model, REVIEWER,
                                          f'NGUỒN: {label}\n{source}\n\nKHÁCH: {user}\nTRẢ LỜI: {answer}', 220)
                        except (ValueError, TimeoutError) as exc:
                            verdict = {'accept': False,
                                       'reason': f'kiểm định không đọc được: {type(exc).__name__}'}
                    accepted = verdict.get('accept') is True
                    audit_rows.append({'user': user, 'answer': answer, 'verdict': verdict})
                    if accepted and (section_id, user) not in existing_keys:
                        row = {
                            'messages': [
                                {'role': 'system', 'content': SYSTEM + '\n\nTHÔNG TIN THAM KHẢO:\n' + source},
                                {'role': 'user', 'content': user},
                                {'role': 'assistant', 'content': answer},
                            ],
                            'source_id': section_id, 'source_file': label,
                            'teacher': args.model, 'reviewed_by': args.model,
                        }
                        out.write(json.dumps(row, ensure_ascii=False) + '\n')
                        out.flush()
                        existing_keys.add((section_id, user))
                        kept += 1
                    elif not accepted:
                        rejected += 1
                audit.write(json.dumps({'section_id': section_id, 'source': label,
                                        'cases': audit_rows}, ensure_ascii=False) + '\n')
                audit.flush()
            except Exception as exc:
                print(f'[WARN] {label}: {type(exc).__name__}: {exc}', flush=True)
    print(json.dumps({'sections': len(groups), 'kept': kept, 'rejected': rejected,
                      'output': str(args.output), 'audit': str(args.audit)},
                     ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
