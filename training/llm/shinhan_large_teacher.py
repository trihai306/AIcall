"""Resumable Qwen 9B question factory for verified Shinhan fact cards.

Generated rows are review candidates, never training targets by default.
The canonical answer comes from a checked fact card, not from Qwen.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import socket
import sqlite3
import time
import unicodedata
import urllib.request
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .shinhan_fact_miner import ensure_tables, load_chunks, mine_one
    from .shinhan_progress import collect as collect_progress, save as save_progress
else:
    from shinhan_fact_miner import ensure_tables, load_chunks, mine_one
    from shinhan_progress import collect as collect_progress, save as save_progress

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "data" / "training" / "shinhan_large"
CARDS = ROOT / "data" / "training" / "shinhan_verified_fact_cards.json"
MANIFEST = ROOT / "data" / "external" / "shinhan" / "manifest.json"
PERSONAS = ["người trẻ hỏi ngắn", "khách lớn tuổi", "khách đang lo lắng",
            "khách bận, hỏi vội", "khách nói kiểu miền Bắc", "khách nói kiểu miền Nam",
            "khách lịch sự trung tính", "khách hỏi tiếp sau một lượt trò chuyện"]


def http_json(url: str, body: dict | None = None, timeout: int = 30) -> dict:
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"} if payload else {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def allowed(availability_url: str, dedicated: bool = False) -> bool:
    if dedicated:
        # Dedicated training is valid only while the customer backend is down.
        # If someone starts the app, stop before the next teacher request.
        with socket.socket() as probe:
            probe.settimeout(0.2)
            return probe.connect_ex(("127.0.0.1", 8100)) != 0
    try:
        return bool(http_json(availability_url, timeout=5).get("can_use_gpu"))
    except Exception:
        return False


def free_gib() -> float:
    import shutil
    return shutil.disk_usage(ROOT).free / 1024 ** 3


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def valid_question(question: str, card: dict) -> bool:
    if not 5 <= len(question.split()) <= 35 or len(question) > 220:
        return False
    if not question.endswith("?"):
        return False
    if not re.search(card["intent"], question, re.I):
        return False
    if re.search(r"\b\d+\b|%|@|https?://|duyệt chắc|đảm bảo được vay|"
                 r"mật khẩu của tôi là|OTP của tôi là|ngoài ngân hàng Shinhan|"
                 r"ngân hàng khác|họ hàng|có cần tư vấn|quy trình.*chuẩn bị gì|"
                 r"đợt biến thể|em gọi cho anh|thư yêu cầu gửi nhầm|"
                 r"(?:anh|chị|bác|chú|cô)\s+(?:nói rõ|cho biết|hỏi xem)", question, re.I):
        return False
    if card["id"] == "early_repayment" and re.search(r"bao nhiêu|mức phí|quy trình", question, re.I):
        return False
    if card["id"] == "lost_card" and re.search(r"mở khóa", question, re.I):
        return False
    if card["id"] == "activate_digital_card" and re.search(r"tại sao|vì sao", question, re.I):
        return False
    if card["id"] == "set_pin" and re.search(
            r"đổi PIN|nhập mã PIN|đến chi nhánh.*như thế nào", question, re.I):
        return False
    return True


def db_open(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS questions ("
               "id INTEGER PRIMARY KEY, fact_id TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE, "
               "question TEXT NOT NULL, answer TEXT NOT NULL, source_url TEXT NOT NULL, "
               "source_sha256 TEXT NOT NULL, persona TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_review', "
               "created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE TABLE IF NOT EXISTS progress (fact_id TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, "
               "dry_calls INTEGER NOT NULL DEFAULT 0, exhausted INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS rejected ("
               "id INTEGER PRIMARY KEY, fact_id TEXT NOT NULL, question TEXT NOT NULL, "
               "reason TEXT NOT NULL, created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE TABLE IF NOT EXISTS judge_attempts ("
               "question_id INTEGER PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0)")
    db.commit()
    return db


class CustomerBusy(Exception):
    pass


def ask(ollama_url: str, availability_url: str, card: dict, persona: str, nonce: int,
        dedicated: bool = False) -> list[str]:
    prompt = (
        "Viết 5 CÂU HỎI khác nhau của khách hàng Shinhan Bank Việt Nam; chỉ câu hỏi, "
        "không viết đáp án. Các câu hỏi phải hỏi đúng một ý từ tài liệu sau:\n"
        + card["fact"] + "\n"
        + f"Kiểu khách: {persona}. "
        + "Mỗi câu phải nêu rõ đúng chủ đề. Các cách gọi gợi ý: "
        + card["intent"].replace(".*", " ").replace("|", ", ") + ". "
        "Không chép ký tự regex như '.*' vào câu hỏi. "
        "Khách đang hỏi nhân viên ngân hàng về việc của chính mình, "
        "không đóng vai tư vấn viên, không hỏi người khác có cần tư vấn không. "
        "Viết thành câu hỏi tự nhiên đầy đủ, kết thúc bằng dấu ?. "
        "Không viết kiểu liệt kê 'Anh cho biết', 'Bác giải thích', 'Chị nói rõ'. "
        "Có thể xưng tôi/mình/em/anh/chị/bác/cô/chú theo ngữ cảnh, "
        "không thêm số tiền, lãi suất, độ tuổi, thời hạn, tên sản phẩm mới, "
        "không hỏi việc khác. Mỗi câu 8-25 từ. "
        'Trả JSON {"questions":["...","..."]}.'
    )
    payload = {"model": "qwen3.5:9b", "messages": [
        {"role": "system", "content": "Bạn chỉ tạo lời hỏi tự nhiên của khách hàng, không tư vấn."},
        {"role": "user", "content": prompt}], "stream": True, "think": False,
        "format": "json", "keep_alive": -1,
        # Match production's context size so Ollama does not reallocate the
        # shared 9B model on the customer's next request.
        "options": {"temperature": 0.75, "seed": nonce, "num_ctx": 4096,
                    "num_predict": 600}}
    req = urllib.request.Request(ollama_url.rstrip("/") + "/api/chat",
                                 data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    fragments = []
    next_check = time.monotonic()
    with urllib.request.urlopen(req, timeout=90) as response:
        for line in response:
            if time.monotonic() >= next_check:
                if not allowed(availability_url, dedicated):
                    raise CustomerBusy("customer activity; teacher request cancelled")
                next_check = time.monotonic() + 0.3
            if line.strip():
                event = json.loads(line)
                fragments.append((event.get("message") or {}).get("content") or "")
    parsed = json.loads("".join(fragments) or "{}")
    return [x.strip() for x in parsed.get("questions", []) if isinstance(x, str)]


def judge_batch(db: sqlite3.Connection, cards: dict, args: argparse.Namespace) -> int:
    """9B screens candidates; its verdict never promotes a row to training."""
    first = db.execute("SELECT fact_id FROM questions WHERE status='pending_review' "
                       "ORDER BY id LIMIT 1").fetchone()
    if not first:
        return 0
    fact_id = first[0]
    rows = db.execute("SELECT id,question FROM questions WHERE status='pending_review' "
                      "AND fact_id=? ORDER BY id LIMIT 5", (fact_id,)).fetchall()
    card = cards.get(fact_id)
    if card is None:
        for row_id, question in rows:
            db.execute("UPDATE questions SET status='teacher_reject' WHERE id=?", (row_id,))
            db.execute("INSERT INTO rejected (fact_id,question,reason) VALUES (?,?,?)",
                       (fact_id, question, "fact_card_withdrawn_after_source_review"))
        db.commit()
        print(f"judge {fact_id}: withdrawn fact card; {len(rows)} rejected", flush=True)
        return len(rows)
    eligible = []
    for row_id, question in rows:
        if valid_question(question, card):
            eligible.append((row_id, question))
        else:
            db.execute("UPDATE questions SET status='teacher_reject' WHERE id=? "
                       "AND status='pending_review'", (row_id,))
            db.execute("INSERT INTO rejected (fact_id,question,reason) "
                       "SELECT fact_id,question,'teacher_precheck' FROM questions WHERE id=?", (row_id,))
    db.commit()
    rows = eligible
    if not rows:
        print(f"judge {fact_id}: 0/{len(eligible)} precheck", flush=True)
        return 0
    prompt = (
        "Bạn chấm câu hỏi của KHÁCH HÀNG ngân hàng, không viết thêm câu mới. "
        "Dữ kiện đã được đối chiếu với PDF Shinhan:\n" + card["fact"] + "\n"
        "Đáp án cố định sẽ dùng để huấn luyện:\n" + card["answer"] + "\n"
        "Ưu tiên loại sai: chỉ cho pass=true khi câu hỏi nghe tự nhiên như khách thật, khách hỏi về "
        "việc của chính họ, đúng một chủ đề, và đáp án cố định trả lời được đầy đủ "
        "mà không cần biết tài khoản, số dư, điều kiện hay mức phí riêng. "
        "Loại câu đảo vai, lủng củng, mơ hồ, hỏi nguyên nhân/số liệu/thủ tục "
        "mà đáp án không có, hoặc câu thêm tiền/lãi/thời hạn không có trong nguồn. "
        "Ví dụ phải loại: 'Làm sao để nhập mã PIN sau khi nhận thẻ online?' "
        "nếu đáp án chỉ nói nơi thiết lập PIN; 'Đến chi nhánh như thế nào?' "
        "nếu nguồn không có đường đi/thủ tục. 'Chị cho biết...' nghe như mẫu máy. "
        "Nếu không chắc, chọn pass=false. Không sửa câu. Trả JSON duy nhất: "
        '{"results":[{"id":1,"pass":true,"reason":""}]}. '
        "Có đúng một kết quả cho mỗi ID; nếu fail, reason ngắn gọn.\n"
        + json.dumps([{"id": i, "question": q} for i, q in rows], ensure_ascii=False)
    )
    payload = {"model": "qwen3.5:9b", "messages": [
        {"role": "system", "content": "Chấm nghiêm ngặt câu hỏi tiếng Việt theo nguồn; không tự phê duyệt train."},
        {"role": "user", "content": prompt}], "stream": True, "think": False,
        "format": "json", "keep_alive": -1,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1600}}
    req = urllib.request.Request(args.ollama_url.rstrip("/") + "/api/chat",
                                 data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    fragments = []
    next_check = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as response:
        for line in response:
            if time.monotonic() >= next_check:
                if not allowed(args.availability_url, args.dedicated):
                    raise CustomerBusy("backend or GPU busy; judge cancelled")
                next_check = time.monotonic() + 0.3
            if line.strip():
                fragments.append((json.loads(line).get("message") or {}).get("content") or "")
    try:
        result = json.loads("".join(fragments) or "{}").get("results", [])
        expected = {i for i, _ in rows}
        if (not isinstance(result, list) or len(result) != len(rows) or
                {x.get("id") for x in result if isinstance(x, dict)} != expected or
                any(type(x.get("pass")) is not bool for x in result)):
            raise ValueError(f"Incomplete judge response for {fact_id}")
    except (ValueError, TypeError) as exc:
        for row_id, _ in rows:
            db.execute("INSERT INTO judge_attempts(question_id,attempts) VALUES (?,1) "
                       "ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1", (row_id,))
        attempts = db.execute("SELECT min(attempts) FROM judge_attempts WHERE "
                              f"question_id IN ({','.join('?' for _ in rows)})",
                              tuple(i for i, _ in rows)).fetchone()[0]
        if attempts >= 3:
            for row_id, _ in rows:
                db.execute("UPDATE questions SET status='teacher_unscored' "
                           "WHERE id=? AND status='pending_review'", (row_id,))
            db.commit()
            print(f"judge {fact_id}: {len(rows)} moved to manual review after "
                  f"{attempts} malformed responses ({type(exc).__name__})", flush=True)
            return 0
        db.commit()
        raise
    passed = 0
    for item in result:
        row_id = item["id"]
        status = "teacher_pass" if item["pass"] else "teacher_reject"
        db.execute("UPDATE questions SET status=? WHERE id=? AND status='pending_review'",
                   (status, row_id))
        if item["pass"]:
            passed += 1
        else:
            db.execute("INSERT INTO rejected (fact_id,question,reason) "
                       "SELECT fact_id,question,? FROM questions WHERE id=?",
                       ("teacher_judge:" + str(item.get("reason", "unspecified"))[:160], row_id))
        db.execute("DELETE FROM judge_attempts WHERE question_id=?", (row_id,))
    db.commit()
    print(f"judge {fact_id}: {passed}/{len(rows)} passed to source review", flush=True)
    return len(rows)


def revalidate_teacher_pass(db: sqlite3.Connection, cards: dict) -> int:
    """Apply stricter deterministic checks to previously screened rows."""
    changed = 0
    for row_id, fact_id, question in db.execute(
            "SELECT id,fact_id,question FROM questions WHERE status='teacher_pass'"):
        card = cards.get(fact_id)
        if card and valid_question(question, card):
            continue
        db.execute("UPDATE questions SET status='teacher_reject' WHERE id=?", (row_id,))
        db.execute("INSERT INTO rejected (fact_id,question,reason) VALUES (?,?,?)",
                   (fact_id, question, "teacher_precheck_revalidation"))
        changed += 1
    db.commit()
    if changed:
        print(f"revalidated teacher_pass: {changed} rejected", flush=True)
    return changed


def run(args: argparse.Namespace) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    manifest = {x["name"]: x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))
                if x.get("status") == "downloaded"}
    for card in cards:
        if card["source"] not in manifest:
            raise SystemExit(f"Missing verified PDF: {card['source']}")
    db = db_open(STATE_DIR / "pending.sqlite")
    ensure_tables(db)
    chunks = load_chunks()
    card_by_id = {x["id"]: x for x in cards}
    revalidate_teacher_pass(db, card_by_id)
    rng = random.Random()
    attempts = accepted = 0
    consecutive_errors = 0
    reason = "call_limit"
    last_snapshot = 0.0

    def snapshot(phase: str, force: bool = False) -> None:
        nonlocal last_snapshot
        now = time.monotonic()
        if force or now - last_snapshot >= 30:
            save_progress(collect_progress(db, args.max_per_fact,
                                           "stopped" if force else "running", phase),
                          force_history=force)
            last_snapshot = now

    for cycle in range(args.calls):
        snapshot("creating_scoring_and_mining")
        if free_gib() < args.min_free_gib:
            reason = "disk_low"
            break
        if not allowed(args.availability_url, args.dedicated):
            reason = "customer_or_gpu_busy"
            break
        if chunks and cycle % 12 == 0:
            try:
                mine_one(db, chunks, args.ollama_url,
                         lambda: allowed(args.availability_url, args.dedicated), CustomerBusy)
            except CustomerBusy:
                reason = "backend_or_gpu_busy"
                break
            except Exception as exc:
                print(f"mine_error {type(exc).__name__}: {exc}", flush=True)
        pending = db.execute("SELECT count(*) FROM questions WHERE status='pending_review'").fetchone()[0]
        if pending:
            try:
                judge_batch(db, card_by_id, args)
                consecutive_errors = 0
            except CustomerBusy:
                reason = "backend_or_gpu_busy"
                break
            except Exception as exc:
                print(f"judge_error {type(exc).__name__}: {exc}", flush=True)
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    reason = "judge_errors"
                    break
                continue
        if db.execute("SELECT count(*) FROM questions").fetchone()[0] >= args.target:
            reason = "target_reached" if not pending else "judge_backlog"
            if not pending:
                if chunks:
                    try:
                        mined = mine_one(db, chunks, args.ollama_url,
                                         lambda: allowed(args.availability_url, args.dedicated),
                                         CustomerBusy)
                    except CustomerBusy:
                        reason = "backend_or_gpu_busy"
                        break
                    except Exception as exc:
                        print(f"mine_error {type(exc).__name__}: {exc}", flush=True)
                        continue
                    if mined is not None:
                        continue
                break
            continue
        eligible = []
        for card in cards:
            have = db.execute("SELECT count(*) FROM questions WHERE fact_id=?", (card["id"],)).fetchone()[0]
            row = db.execute("SELECT dry_calls,exhausted FROM progress WHERE fact_id=?", (card["id"],)).fetchone()
            if have < args.max_per_fact and not (row and row[1]):
                eligible.append((have, card))
        if not eligible:
            reason = "need_more_verified_facts" if not pending else "judge_backlog"
            if not pending:
                if chunks:
                    try:
                        mined = mine_one(db, chunks, args.ollama_url,
                                         lambda: allowed(args.availability_url, args.dedicated),
                                         CustomerBusy)
                    except CustomerBusy:
                        reason = "backend_or_gpu_busy"
                        break
                    except Exception as exc:
                        print(f"mine_error {type(exc).__name__}: {exc}", flush=True)
                        continue
                    if mined is not None:
                        continue
                reason = "awaiting_new_verified_facts"
                break
            continue
        least = min(h for h, _ in eligible)
        card = rng.choice([c for h, c in eligible if h <= least + 15])
        persona = rng.choice(PERSONAS)
        try:
            questions = ask(args.ollama_url, args.availability_url, card, persona,
                            rng.randrange(1_000_000_000), args.dedicated)
        except CustomerBusy:
            reason = "customer_or_gpu_busy"
            break
        except Exception as exc:
            print(f"teacher_error {card['id']}: {type(exc).__name__}: {exc}", flush=True)
            consecutive_errors += 1
            if consecutive_errors >= 3:
                reason = "teacher_errors"
                break
            continue
        consecutive_errors = 0
        new = 0
        source = manifest[card["source"]]
        for question in questions[:5]:
            if not valid_question(question, card):
                db.execute("INSERT INTO rejected (fact_id,question,reason) VALUES (?,?,?)",
                           (card["id"], question, "topic_or_safety_filter"))
                continue
            norm = normalize(question)
            try:
                db.execute("INSERT INTO questions (fact_id,normalized,question,answer,source_url,"
                           "source_sha256,persona) VALUES (?,?,?,?,?,?,?)",
                           (card["id"], norm, question, card["answer"], source["url"],
                            source["sha256"], persona))
                new += 1
            except sqlite3.IntegrityError:
                db.execute("INSERT INTO rejected (fact_id,question,reason) VALUES (?,?,?)",
                           (card["id"], question, "duplicate"))
        db.execute("INSERT INTO progress (fact_id,calls,dry_calls,exhausted) VALUES (?,1,?,0) "
                   "ON CONFLICT(fact_id) DO UPDATE SET calls=calls+1, "
                   "dry_calls=CASE WHEN ?=0 THEN dry_calls+1 ELSE 0 END, "
                   "exhausted=CASE WHEN ?=0 AND dry_calls>=5 THEN 1 ELSE exhausted END",
                   (card["id"], int(new == 0), new, new))
        db.commit()
        attempts += 1
        accepted += new
        print(f"{card['id']}: {new}/{len(questions)} new; total={db.execute('SELECT count(*) FROM questions').fetchone()[0]}", flush=True)
    total = db.execute("SELECT count(*) FROM questions").fetchone()[0]
    statuses = dict(db.execute("SELECT status,count(*) FROM questions GROUP BY status"))
    report = {"reason": reason, "calls": attempts, "new": accepted,
              "generated": total, "status": statuses, "verified_facts": len(cards),
              "fact_candidates": db.execute("SELECT count(*) FROM fact_candidates").fetchone()[0],
              "mined_chunks": db.execute("SELECT count(*) FROM mining_chunks WHERE status='done'").fetchone()[0],
              "source_chunks": len(chunks),
              "free_gib": round(free_gib(), 2),
              "target": args.target,
              "note": "No generated question is approved for training until audit."}
    (STATE_DIR / "status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot(reason, force=True)
    print(json.dumps(report, ensure_ascii=False), flush=True)


@contextmanager
def exclusive_worker(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        if __import__("os").name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise SystemExit("Shinhan teacher already running")
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise SystemExit("Shinhan teacher already running")
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=24)
    ap.add_argument("--target", type=int, default=1_000_000)
    ap.add_argument("--max-per-fact", type=int, default=300)
    ap.add_argument("--min-free-gib", type=float, default=11.0)
    ap.add_argument("--availability-url", default="http://127.0.0.1:8100/api/training/availability")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--dedicated", action="store_true",
                    help="Run only while the customer backend on port 8100 is stopped")
    args = ap.parse_args()
    if args.calls < 1 or args.max_per_fact < 1:
        ap.error("calls and max-per-fact must be positive")
    with exclusive_worker(STATE_DIR / "worker.lock"):
        run(args)


if __name__ == "__main__":
    main()
