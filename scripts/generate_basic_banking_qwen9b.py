"""Generate a resumable, synthetic Vietnamese banking Q&A pack with Qwen 9B.

Writes a separate dataset; never imports, enables answers, or changes services.
GPU availability is checked before and during generation. Standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.request import Request, urlopen
import uuid

MODEL = 'qwen3.5:9b'
ROOT = Path(__file__).resolve().parents[1]
TOPICS = [
    'Tài khoản thanh toán và mục đích sử dụng',
    'Số dư khả dụng: giải thích định tính',
    'Phân biệt tài khoản ngân hàng và thẻ',
    'Phân biệt chuyển khoản và thanh toán',
    'Ngân hàng số và ngân hàng trực tuyến',
    'Thói quen tiết kiệm và quản lý tiền cá nhân',
    'Thẻ ghi nợ: nguyên tắc sử dụng',
    'Thẻ tín dụng: sử dụng có trách nhiệm, không bàn phí hoặc lãi',
    'Thẻ vật lý và thẻ điện tử',
    'Giữ gìn thẻ và bảo vệ thông tin thẻ',
    'Khóa thẻ khi nghi ngờ rủi ro',
    'Thẻ bị mất hoặc bị lấy cắp',
    'Thẻ bị máy ATM giữ lại',
    'An toàn khi sử dụng máy ATM',
    'Thanh toán tại máy POS',
    'Thanh toán không tiếp xúc',
    'Thanh toán trực tuyến an toàn',
    'Quét mã QR an toàn',
    'Kiểm tra người nhận trước khi chuyển tiền',
    'Chuyển khoản đang chờ xử lý',
    'Chuyển khoản báo lỗi',
    'Người nhận chưa thấy tiền chuyển đến',
    'Chuyển nhầm người nhận',
    'Nhận tiền chuyển đến không rõ nguồn',
    'Xem lịch sử giao dịch trên ứng dụng',
    'Thông báo biến động tài khoản',
    'Phát hiện giao dịch không nhận ra',
    'Mật khẩu ngân hàng số',
    'Mã PIN: khái niệm và bảo vệ',
    'OTP: khái niệm và bảo vệ',
    'Đăng nhập và đăng xuất an toàn',
    'Thiết bị lạ và phiên đăng nhập',
    'Mất điện thoại có ứng dụng ngân hàng',
    'Đổi điện thoại và chuyển thiết bị',
    'Cài ứng dụng ngân hàng từ nguồn chính thức',
    'Ứng dụng bị lỗi và kết nối mạng',
    'Nhận diện tin nhắn và đường dẫn giả',
    'Mạo danh nhân viên ngân hàng',
    'Lừa đảo chia sẻ màn hình và điều khiển máy',
    'Liên hệ hỗ trợ và diễn đạt vấn đề rõ ràng',
]
SYSTEM = (
    'Bạn tự biên soạn câu hỏi của khách rồi tự trả lời bằng tiếng Việt. '
    'Chỉ kiến thức ngân hàng phổ thông, không gắn ngân hàng hoặc sản phẩm cụ thể. '
    'Cấm số liệu, chữ số, tỷ lệ, lãi suất, biểu phí, hạn mức, thời hạn cam kết, '
    'số điện thoại, URL; không thay chữ số bằng chữ để lách yêu cầu. '
    'Không nói về giấy tờ, hồ sơ, sao kê, chứng từ, hợp đồng hay thủ tục xét duyệt. '
    'Không yêu cầu khách gửi OTP, PIN, mật khẩu hoặc thông tin thẻ. '
    'Không giả vờ đã xem tài khoản, khóa thẻ, chuyển tiền hay xử lý yêu cầu. '
    'Không bảo đảm hoàn tiền hoặc kết quả giao dịch. Không bịa tính năng hoặc '
    'đường dẫn menu của ứng dụng; tính năng tùy ngân hàng phải nói rõ khi cần. '
    'Trả lời trực tiếp, tự nhiên, hữu ích, khoảng hai mươi đến bốn mươi từ; '
    'không chỉ lặp lại lời khuyên liên hệ ngân hàng. Mỗi cặp một tình huống riêng. '
    'Chỉ xuất JSON {"items":[{"q":"câu hỏi","a":"câu trả lời"}]}.'
)

class GPUBusy(RuntimeError):
    pass

def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.lower().replace('đ', 'd'))
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', ''.join(
        c for c in text if not unicodedata.combining(c))).split())

def rejection(q: str, a: str) -> str:
    if not (8 <= len(q) <= 300 and 25 <= len(a) <= 650):
        return 'length'
    text = normalize(q + ' ' + a)
    if any(c.isdigit() for c in q + a) or re.search(r'[%₫$€]|https?://|www\.', q + a):
        return 'numbers_or_links'
    if re.search(r'\b(giay to|ho so|sao ke|chung tu|hop dong|can cuoc|cccd|cmnd|ho chieu|xet duyet|lai suat|bieu phi|muc phi|han muc)\b', text):
        return 'excluded_scope'
    if re.search(r'\b(trieu|ty dong|phan tram|bao dau)\b', text):
        return 'quantified_or_promised'
    if re.search(r'\b(em|toi|chung toi) da (kiem tra|khoa|chuyen|xu ly|hoan tien)\b', normalize(a)):
        return 'fabricated_action'
    if re.search(r'\b(cam ket|chac chan duoc|an toan tuyet doi|dam bao hoan tien)\b', normalize(a)):
        return 'unfounded_guarantee'
    if re.search(r'\b(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|tram|nghin)(?: (?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|tram|nghin))* (?:gio|ngay|thang|nam|dong|phan tram)\b', text):
        return 'quantified_or_promised'
    for raw_sentence in re.split(r'[.!?;,]|\bnhưng\b|\btuy nhiên\b', a, flags=re.I):
        sentence = normalize(raw_sentence)
        for match in re.finditer(r'(?:cung cap|gui|doc|chia se) (?:ma )?(?:otp|pin|mat khau)', sentence):
            if not re.search(r'\b(?:khong|dung|tranh|tuyet doi)\b', sentence[max(0, match.start() - 80):match.start()]):
                return 'secret_request'
    if '<think' in (q + a).lower() or re.search(r'[\u4e00-\u9fff]', q + a):
        return 'non_vietnamese_or_internal'
    return ''

def get_json(url: str, timeout: int = 8) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)

def check_gpu(url: str) -> None:
    status = get_json(url)
    if status.get('can_use_gpu') is not True:
        raise GPUBusy(status.get('reason') or 'GPU unavailable; service priority preserved')

def atomic_json(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)

@contextmanager
def endpoints(args):
    if not args.ssh_host:
        yield args.base_url.rstrip('/'), args.availability_url
        return
    ports = []
    while len(ports) < 2:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            if port not in ports:
                ports.append(port)
    with tempfile.TemporaryFile() as errors:
        command = ['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                   '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15']
        for local, remote in zip(ports, (11434, 8100)):
            command += ['-L', f'127.0.0.1:{local}:127.0.0.1:{remote}']
        process = subprocess.Popen(command + [args.ssh_host], stdout=subprocess.DEVNULL, stderr=errors)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError('SSH tunnel exited before readiness')
                try:
                    with socket.create_connection(('127.0.0.1', ports[0]), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('SSH tunnel readiness timeout')
                    time.sleep(0.1)
            yield f'http://127.0.0.1:{ports[0]}', f'http://127.0.0.1:{ports[1]}/api/training/availability'
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

def draft(base: str, availability: str, prompt: str, output: Path) -> tuple[list, str]:
    check_gpu(availability)
    payload = {'model': MODEL, 'messages': [
        {'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}],
        'stream': True, 'think': False, 'format': 'json', 'keep_alive': '5m',
        'options': {'temperature': 0.7, 'num_ctx': 8192, 'num_predict': 3500}}
    request = Request(base + '/api/chat', json.dumps(payload, ensure_ascii=False).encode(),
                      {'Content-Type': 'application/json'})
    chunks, final, checked = [], {}, time.monotonic()
    with urlopen(request, timeout=90) as response:
        for line in response:
            if time.monotonic() - checked >= 1:
                check_gpu(availability)
                checked = time.monotonic()
            frame = json.loads(line)
            if frame.get('error'):
                raise RuntimeError(frame['error'])
            if frame.get('model') != MODEL:
                raise RuntimeError('Unexpected model in response')
            chunks.append(frame.get('message', {}).get('content', ''))
            if frame.get('done'):
                final = frame
    content = ''.join(chunks)
    receipt = uuid.uuid4().hex + '.json'
    atomic_json(output / 'raw' / receipt, {'request': payload, 'response': final, 'content': content})
    if not final.get('done') or final.get('done_reason') == 'length':
        raise ValueError('Incomplete model output; raw receipt retained')
    items = json.loads(content).get('items')
    if not isinstance(items, list):
        raise ValueError('Model response lacks an items array')
    return items, receipt

def export(output: Path, rows: list[dict], report: dict) -> None:
    atomic_json(output / 'banking_basic.json', {'metadata': report, 'responses': [
        {'key': r['id'], 'category': r['category'], 'title': r['question'],
         'examples': [r['question']], 'answer': r['answer'], 'source_receipt': r['receipt']} for r in rows]})
    with (output / 'banking_basic.messages.jsonl').open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps({'id': row['id'], 'category': row['category'],
                'provenance': 'qwen9b_synthetic', 'messages': [
                {'role': 'user', 'content': row['question']},
                {'role': 'assistant', 'content': row['answer']}]}, ensure_ascii=False) + '\n')
    lines = [f'# Bộ hỏi–đáp ngân hàng cơ bản — {len(rows)} cặp', '',
             'Dữ liệu tổng hợp do Qwen tạo, đã qua bộ lọc tự động; không phải quy định chính thức của ngân hàng.',
             'Chưa tự động đưa vào hệ thống trả lời khách hàng.', '']
    for index, row in enumerate(rows, 1):
        lines += [f'## {index}. {row["question"]}', '',
                  f'Chủ đề: {row["category"]}', '', row['answer'], '']
    (output / 'banking_basic.md').write_text('\n'.join(lines), encoding='utf-8')

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/generated/basic_banking_qwen9b_20261001')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--availability-url', default='http://127.0.0.1:8100/api/training/availability')
    parser.add_argument('--ssh-host', help='Existing SSH alias; temporary loopback-only tunnel')
    args = parser.parse_args()
    if args.count < 1 or not 1 <= args.batch_size <= 20:
        parser.error('count must be positive and batch-size must be between 1 and 20')
    output = args.output.resolve()
    (output / 'raw').mkdir(parents=True, exist_ok=True)
    ledger = output / 'accepted.jsonl'
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines() if line.strip()] if ledger.exists() else []
    seen_q, seen_a = set(), set()
    for row in rows:
        if row.get('model') != MODEL or rejection(row['question'], row['answer']):
            raise ValueError('Existing ledger fails validation; preserve it for inspection')
        qkey, akey = normalize(row['question']), normalize(row['answer'])
        if qkey in seen_q or akey in seen_a or not (output / 'raw' / row['receipt']).is_file():
            raise ValueError('Existing ledger has duplicate rows or a missing model receipt')
        seen_q.add(qkey)
        seen_a.add(akey)
    report = {'model': MODEL, 'target': args.count, 'accepted': len(rows), 'complete': False,
              'status': 'preflight', 'review': 'synthetic_automated_checks_only',
              'excluded': ['numbers', 'rates', 'fees', 'documents', 'credentials', 'guarantees'],
              'rejections': {}, 'categories': dict(Counter(r['category'] for r in rows))}
    atomic_json(output / 'generation_spec.json', {'model': MODEL, 'system_prompt': SYSTEM, 'topics': TOPICS, 'target': args.count})
    try:
        if len(rows) > args.count:
            raise ValueError('Existing dataset exceeds target; use a new output folder')
        with endpoints(args) as (base, availability):
            models = get_json(base + '/api/tags').get('models', [])
            model = next((m for m in models if m.get('name') == MODEL), None)
            if model is None:
                raise RuntimeError('Required qwen3.5:9b is not installed; no model substitution')
            atomic_json(output / 'model.json', model)
            check_gpu(availability)
            rejected = Counter()
            for topic_index, topic in enumerate(TOPICS):
                goal = args.count // len(TOPICS) + (topic_index < args.count % len(TOPICS))
                current = [r for r in rows if r['category'] == topic]
                attempts = 0
                while len(current) < goal and attempts < max(8, goal * 2):
                    attempts += 1
                    needed = min(args.batch_size, goal - len(current) + 2)
                    prompt = (f'Tự đặt {needed} câu hỏi khác nhau rồi tự trả lời. Chủ đề: {topic}. '
                              'Không đổi vài từ để lặp lại cùng câu hỏi. Tránh các câu hỏi đã có: '
                              + json.dumps([r['question'] for r in current], ensure_ascii=False))
                    try:
                        candidates, receipt = draft(base, availability, prompt, output)
                    except (ValueError, json.JSONDecodeError) as exc:
                        rejected['invalid_json_or_truncated'] += 1
                        print(json.dumps({'status': 'retry', 'reason': str(exc)}, ensure_ascii=False), flush=True)
                        continue
                    for candidate in candidates:
                        if not isinstance(candidate, dict) or not all(isinstance(candidate.get(k), str) for k in ('q', 'a')):
                            rejected['schema'] += 1
                            continue
                        q, a = candidate['q'].strip(), candidate['a'].strip()
                        reason = rejection(q, a)
                        qkey, akey = normalize(q), normalize(a)
                        if reason or qkey in seen_q or akey in seen_a:
                            rejected[reason or 'duplicate'] += 1
                            continue
                        row = {'id': 'qwen9b_' + hashlib.sha256((q + '\n' + a).encode()).hexdigest()[:20],
                               'category': topic, 'question': q, 'answer': a, 'model': MODEL, 'receipt': receipt}
                        with ledger.open('a', encoding='utf-8') as f:
                            f.write(json.dumps(row, ensure_ascii=False) + '\n')
                            f.flush()
                        rows.append(row)
                        current.append(row)
                        seen_q.add(qkey)
                        seen_a.add(akey)
                        if len(current) == goal:
                            break
                    report.update(status='generating', accepted=len(rows), rejections=dict(rejected),
                                  categories=dict(Counter(r['category'] for r in rows)))
                    atomic_json(output / 'progress.json', report)
                    print(json.dumps({'accepted': len(rows), 'target': args.count, 'topic': topic}, ensure_ascii=False), flush=True)
                if len(current) != goal:
                    raise RuntimeError('Topic did not reach its target within bounded attempts')
        report.update(complete=len(rows) == args.count, status='completed', accepted=len(rows))
        export(output, rows, report)
        return 0
    except GPUBusy as exc:
        report.update(status='blocked_gpu_busy', reason=str(exc), accepted=len(rows))
        return 2
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='incomplete', reason=f'{type(exc).__name__}: {exc}', accepted=len(rows))
        return 1
    finally:
        if rows and not report['complete']:
            export(output, rows, report)
        atomic_json(output / 'progress.json', report)
        print(json.dumps(report, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    sys.exit(main())
