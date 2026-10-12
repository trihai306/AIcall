"""Chạy hội thoại thật qua WebSocket và lưu bằng chứng/oracle từng lượt.

Chế độ tương thích (mảng JSON, ghi một lần khi xong)::

    python scripts/thu_hoi_thoai_kho.py input.json output.json

Chế độ bền cho bộ lớn (mỗi case là một dòng, có thể tiếp tục)::

    python scripts/thu_hoi_thoai_kho.py input.json output.jsonl --jsonl --resume

Mỗi ``luot`` là chuỗi hoặc ``{khach, expect}``; không có ``expect`` thì lượt
được giữ là unscored. Script chỉ mô phỏng khách trên WebSocket, không gọi API
điện thoại thật.
"""
import argparse
import asyncio
import copy
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
import json
import re
import time
import unicodedata
import uuid
from collections import Counter
from pathlib import Path

import websockets


def folded(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
                   if unicodedata.category(c) != "Mn")


def _number(value):
    """Return a comparable Decimal for JSON numbers and numeric fact strings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _same_fact(actual, expected):
    left, right = _number(actual), _number(expected)
    if left is not None and right is not None:
        return left == right
    return str(actual) == str(expected)


_CLAUSE_BREAK = re.compile(
    r"(?:[.!?;:,\n]+|\b(?:nhung|tuy nhien|song|ma con)\b)"
)
_AFFIRMATIVE_CUE = re.compile(
    r"\b(?:chac chan|dam bao|cam ket|duoc duyet|se duyet|phe duyet)\b"
)
_NEGATION = re.compile(r"\b(?:khong|chua|chang)\b")
_REJECTED_SUFFIX = re.compile(
    r"^[\s\"'”’]*?(?:thi\s+)?(?:do\s+)?(?:la\s+)?"
    r"(?:sai|khong dung|khong chinh xac|khong the khang dinh)\b"
)


def _affirmative_violation(text, pattern):
    """Whether ``pattern`` appears as a locally affirmative claim.

    Negation is scoped to a short clause and to the positive cue itself. This
    accepts ``không thể đảm bảo hồ sơ được duyệt`` but still rejects
    ``không chắc gì, nhưng chắc chắn duyệt`` and ``không đủ vẫn chắc chắn
    duyệt``. Explicitly rejected quotations such as ``... là sai`` are not
    treated as the assistant making the quoted claim.
    """
    for clause in _CLAUSE_BREAK.split(text):
        for match in re.finditer(pattern, clause):
            matched = clause[match.start():match.end()]
            cue = _AFFIRMATIVE_CUE.search(matched)
            target = match.start() + (cue.start() if cue else 0)
            prefix = clause[:target]
            negations = list(_NEGATION.finditer(prefix))
            locally_negated = False
            if negations:
                gap = prefix[negations[-1].end():]
                words = re.findall(r"\w+", gap)
                scope_broken = bool(re.search(
                    r"\b(?:nhung|tuy nhien|song|ma con|(?<!tu\s)van)\b", gap))
                denial_verb = bool(re.search(
                    r"\b(?:noi|khang dinh|dam bao|cam ket|tu van|ap dung)\b", gap))
                locally_negated = (not scope_broken
                                   and (len(words) <= 2
                                        or denial_verb and len(words) <= 10))
            if locally_negated:
                continue
            if _REJECTED_SUFFIX.search(clause[match.end():]):
                continue
            return True
    return False


def check(reply, metrics, expected):
    if expected is None:
        return None, []
    errors, normalized = [], folded(reply)
    route = metrics.get("answer_route", {})
    for pattern in expected.get("require", []):
        if not re.search(pattern, normalized):
            errors.append("missing: " + pattern)
    for pattern in expected.get("forbid", []):
        if re.search(pattern, normalized):
            errors.append("forbidden: " + pattern)
    for pattern in expected.get("forbid_affirmative", []):
        if _affirmative_violation(normalized, pattern):
            errors.append("affirmative forbidden: " + pattern)
    if expected.get("modes") and route.get("mode") not in expected["modes"]:
        errors.append("mode: " + str(route.get("mode")))
    if expected.get("reasons") and route.get("reason") not in expected["reasons"]:
        errors.append("reason: " + str(route.get("reason")))
    for slot, fields in expected.get("facts", {}).items():
        actual = metrics.get("du_kien_vay", {}).get(slot, {})
        for field, value in fields.items():
            if not _same_fact(actual.get(field), value):
                errors.append(f"{slot}.{field}: {actual.get(field)!r}, wanted {value!r}")
    return not errors, errors


def _event_for_turn(event, turn_id):
    """Only filter when the server actually supplies an event turn id.

    ``response_chunk`` and ``turn_complete`` currently have no turn id. Since
    the runner sends turns sequentially, a timeout/error must close the whole
    case; otherwise an untagged late ``turn_complete`` could be consumed by the
    next turn.
    """
    event_turn = event.get("turn_id")
    return event_turn is None or str(event_turn) == str(turn_id)


def _step_parts(step):
    if isinstance(step, str):
        return step, None
    return step["khach"], step.get("expect")


def _error_row(question, expected, message, chunks, event=None):
    return {
        "khach": question,
        "ai": "",
        "expect": expected,
        "pass": False,
        "issues": [message],
        "response_chunks": list(chunks),
        "error": event or {"message": message},
    }


class TurnTimeoutError(RuntimeError):
    pass


@asynccontextmanager
async def _open_socket(url, timeout):
    try:
        async with websockets.connect(
                url, max_size=None, open_timeout=timeout) as ws:
            yield ws
    except asyncio.TimeoutError as error:
        raise TurnTimeoutError(
            f"timeout opening or closing WebSocket after {timeout:g}s") from error


async def _receive_json(ws, timeout, label):
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout)
    except asyncio.TimeoutError as error:
        raise TurnTimeoutError(f"timeout waiting for {label} after {timeout:g}s") from error
    if isinstance(raw, bytes):
        return None
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError(f"WebSocket event must be an object, got {type(event).__name__}")
    return event


async def run_case(case, ws_base, turn_timeout=45):
    """Populate ``case`` and return whether every turn completed.

    Service errors and timeouts stop the case. The socket context then closes,
    which prevents an untagged late ``turn_complete`` from leaking into a later
    turn. A resume run gets a new, independent session.
    """
    session_id = f"quality_{uuid.uuid4().hex}"
    rows = case.setdefault("ket_qua", [])
    case.setdefault("errors", [])
    async with _open_socket(ws_base + session_id, turn_timeout) as ws:
        await ws.send(json.dumps({
            "type": "set_session",
            "customer_name": "Khách kiểm thử",
            "product": case.get("san_pham", ""),
        }))
        while True:
            event = await _receive_json(ws, turn_timeout, "session_updated")
            if event is None:
                continue
            if event.get("type") == "session_updated":
                break
            if event.get("type") in {"error", "session_config_error"}:
                case["errors"].append({
                    "type": "session_error",
                    "message": event.get("message", "session setup failed"),
                    "event": event,
                })
                return False

        for index, step in enumerate(case["luot"], 1):
            question, expected = _step_parts(step)
            chunks = []
            turn_started = time.monotonic()
            await ws.send(json.dumps({"type": "text_soi", "text": question,
                                      "turn_id": index}))
            deadline = turn_started + turn_timeout
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TurnTimeoutError(
                            f"turn {index} timed out after {turn_timeout:g}s")
                    event = await _receive_json(ws, remaining, f"turn {index}")
                    if event is None or not _event_for_turn(event, index):
                        continue
                    kind = event.get("type")
                    if kind == "response_chunk":
                        chunks.append(event.get("text", ""))
                    elif kind == "error":
                        message = event.get("message", "service error")
                        rows.append(_error_row(question, expected, message, chunks, event))
                        case["errors"].append({
                            "type": "service_error", "turn": index,
                            "message": message, "event": event,
                        })
                        return False
                    elif kind == "turn_complete":
                        reply = event.get("full_response", "")
                        metrics = event.get("metrics", {}) or {}
                        passed, issues = check(reply, metrics, expected)
                        rows.append({
                            "khach": question,
                            "ai": reply,
                            "expect": expected,
                            "pass": passed,
                            "issues": issues,
                            "metrics": metrics,
                            "response_chunks": chunks,
                            "wall_s": round(time.monotonic() - turn_started, 3),
                        })
                        break
            except (Exception, asyncio.CancelledError) as error:
                # Keep evidence received for the interrupted turn. CancelledError
                # is re-raised so the enclosing case timeout remains authoritative.
                message = (f"turn {index} cancelled by case timeout"
                           if isinstance(error, asyncio.CancelledError) else str(error))
                rows.append(_error_row(question, expected, message, chunks))
                raise
    return True


def _is_completed(case):
    marker = case.get("_runner", {})
    if marker.get("completed") is False:
        return False
    rows, steps = case.get("ket_qua", []), case.get("luot", [])
    return (marker.get("completed", True) is True
            and not case.get("loi") and not case.get("errors")
            and len(rows) == len(steps)
            and all(not row.get("error") for row in rows))


def _read_output(path, jsonl):
    if not path.exists() or not path.stat().st_size:
        return []
    if not jsonl:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    records = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            final_unterminated = index == len(lines) and not raw.endswith(("\n", "\r"))
            if final_unterminated:
                # A killed process may leave exactly one truncated final append.
                # OutputWriter removes it before appending the retry.
                continue
            raise ValueError(f"corrupt JSONL at line {index}: {error.msg}") from error
        if not isinstance(record, dict):
            raise ValueError(f"corrupt JSONL at line {index}: expected an object")
        records.append(record)
    return records


def latest_records(path, jsonl):
    latest = {}
    for record in _read_output(path, jsonl):
        if record.get("ma") is not None:
            latest[str(record["ma"])] = record
    return latest


class OutputWriter:
    def __init__(self, path, jsonl):
        self.path = path
        self.jsonl = jsonl
        self.lock = asyncio.Lock()

    async def prepare(self, resume):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.jsonl:
            return
        if not resume:
            await asyncio.to_thread(self.path.write_text, "", encoding="utf-8")
        elif self.path.exists() and self.path.stat().st_size:
            await asyncio.to_thread(self._repair_final_line)

    def _repair_final_line(self):
        """Drop one truncated tail or terminate one valid final JSON record."""
        with self.path.open("rb+") as stream:
            stream.seek(-1, 2)
            if stream.read(1) == b"\n":
                return
            stream.seek(0)
            raw = stream.read()
            boundary = raw.rfind(b"\n") + 1
            tail = raw[boundary:]
            try:
                json.loads(tail.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                stream.seek(boundary)
                stream.truncate()
                return
            stream.seek(0, 2)
            stream.write(b"\n")

    def _append_line(self, case):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
            stream.flush()

    async def write_case(self, case):
        if not self.jsonl:
            return
        async with self.lock:
            await asyncio.to_thread(self._append_line, case)

    async def write_json(self, cases):
        if self.jsonl:
            return
        payload = json.dumps(cases, ensure_ascii=False, indent=2, default=str)
        async with self.lock:
            await asyncio.to_thread(self.path.write_text, payload, encoding="utf-8")


async def execute_case(original, ws_base, case_timeout, turn_timeout):
    case = copy.deepcopy(original)
    case["ket_qua"] = []
    case["errors"] = []
    case.pop("loi", None)
    started = time.monotonic()
    completed = False
    try:
        completed = await asyncio.wait_for(
            run_case(case, ws_base, turn_timeout), timeout=case_timeout)
    except TurnTimeoutError as exc:
        error = {"type": "turn_timeout", "message": str(exc)}
        case["errors"].append(error)
        case["loi"] = error["message"]
    except asyncio.TimeoutError:
        error = {"type": "case_timeout",
                 "message": f"case timed out after {case_timeout:g}s"}
        case["errors"].append(error)
        case["loi"] = error["message"]
    except Exception as exc:
        error = {"type": "runner_error", "message": repr(exc)}
        case["errors"].append(error)
        case["loi"] = error["message"]

    completed = bool(completed and len(case["ket_qua"]) == len(case.get("luot", []))
                     and not case["errors"]
                     and all(not row.get("error") for row in case["ket_qua"]))
    case["_runner"] = {
        "completed": completed,
        "status": "completed" if completed else "error",
        "turns_planned": len(case.get("luot", [])),
        "turns_completed": sum(not row.get("error") for row in case["ket_qua"]),
        "wall_s": round(time.monotonic() - started, 3),
    }
    return case


def _totals(records):
    rows = [row for case in records for row in case.get("ket_qua", [])
            if not row.get("error")]
    routes = Counter()
    for row in rows:
        route = (row.get("metrics") or {}).get("answer_route") or {}
        if route.get("mode"):
            routes[str(route["mode"])] += 1
    return {
        "completed_cases": sum(_is_completed(case) for case in records),
        "incomplete_cases": sum(not _is_completed(case) for case in records),
        "turns": len(rows),
        "scored_pass": sum(row.get("pass") is True for row in rows),
        "scored_fail": sum(row.get("pass") is False for row in rows),
        "unscored": sum(row.get("pass") is None for row in rows),
        "errors": sum(len(case.get("errors", [])) for case in records),
        "route_counts": dict(sorted(routes.items())),
    }


def summarize(this_records, cumulative_records, *, input_cases, selected_cases,
              skipped_resume, wall_s):
    this_run = _totals(this_records)
    this_run["executed_cases"] = len(this_records)
    this_run["newly_completed_cases"] = this_run["completed_cases"]
    this_run["wall_s"] = round(wall_s, 3)
    cumulative = _totals(cumulative_records)
    cumulative["latest_attempt_cases"] = len(cumulative_records)
    cumulative["pending_execution_cases"] = (
        len(input_cases) - cumulative["completed_cases"])

    cumulative_by_id = {str(record.get("ma")): record for record in cumulative_records}
    manual_inputs = [case for case in input_cases if case.get("manual_review") is True]
    manual_records = [cumulative_by_id[str(case.get("ma"))] for case in manual_inputs
                      if str(case.get("ma")) in cumulative_by_id]
    manual_rows = [row for case in manual_records for row in case.get("ket_qua", [])
                   if not row.get("error")]
    manual_completed = sum(_is_completed(case) for case in manual_records)
    manual_review = {
        "status": "pending_human_review" if manual_inputs else "not_applicable",
        "cases_total": len(manual_inputs),
        "cases_with_evidence": len(manual_records),
        "cases_pending_execution": len(manual_inputs) - manual_completed,
        "cases_ready_for_human_review": manual_completed,
        # The runner never turns these into a fully-passed status; human review
        # remains pending even when every machine-checkable invariant passed.
        "cases_pending_human_review": len(manual_inputs),
        "invariant_turns_scored": sum(row.get("pass") is not None for row in manual_rows),
        "invariant_scored_pass": sum(row.get("pass") is True for row in manual_rows),
        "invariant_scored_fail": sum(row.get("pass") is False for row in manual_rows),
        "unscored_turns": sum(row.get("pass") is None for row in manual_rows),
    }
    return {
        "input_cases": len(input_cases),
        "selected_cases": selected_cases,
        "skipped_resume": skipped_resume,
        "this_run": this_run,
        "cumulative": cumulative,
        "manual_review": manual_review,
        "timing_scope": "client wall clock over WebSocket; not server/GPU performance",
    }


async def run_all(cases, output, *, ws, jsonl=False, resume=False, concurrency=1,
                  limit=None, case_timeout=180, turn_timeout=45, progress_every=10):
    output = Path(output)
    previous = latest_records(output, jsonl) if resume else {}
    previous_completed = {case_id for case_id, record in previous.items()
                          if _is_completed(record)}
    pending = [case for case in cases if str(case.get("ma")) not in previous_completed]
    skipped = len(cases) - len(pending)
    if limit is not None:
        pending = pending[:limit]

    writer = OutputWriter(output, jsonl)
    await writer.prepare(resume)
    started = time.monotonic()
    completed_count = 0
    produced = []
    queue = asyncio.Queue()
    for case in pending:
        queue.put_nowait(case)

    async def worker():
        nonlocal completed_count
        while True:
            try:
                original = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            record = await execute_case(
                original, ws, case_timeout=case_timeout, turn_timeout=turn_timeout)
            produced.append(record)
            await writer.write_case(record)
            completed_count += 1
            failed = [index for index, row in enumerate(record.get("ket_qua", []), 1)
                      if row.get("pass") is False and not row.get("error")]
            if (record.get("errors") or completed_count % progress_every == 0
                    or completed_count == len(pending)):
                print(json.dumps({
                    "case": record.get("ma"),
                    "progress": f"{completed_count}/{len(pending)}",
                    "failed_turns": failed,
                    "errors": record.get("errors", []),
                    "elapsed_s": round(time.monotonic() - started),
                }, ensure_ascii=False), flush=True)
            queue.task_done()

    await asyncio.gather(*(worker() for _ in range(concurrency)))

    if not jsonl:
        produced_by_id = {str(case.get("ma")): case for case in produced}
        merged = []
        for original in cases:
            case_id = str(original.get("ma"))
            merged.append(produced_by_id.get(case_id, previous.get(case_id,
                          copy.deepcopy(original))))
        await writer.write_json(merged)

    input_ids = {str(case.get("ma")) for case in cases}
    cumulative_by_id = {case_id: record for case_id, record in previous.items()
                        if case_id in input_ids}
    cumulative_by_id.update({str(case.get("ma")): case for case in produced})
    cumulative_records = [cumulative_by_id[str(case.get("ma"))] for case in cases
                          if str(case.get("ma")) in cumulative_by_id]
    summary = summarize(
        produced, cumulative_records, input_cases=cases, selected_cases=len(pending),
        skipped_resume=skipped, wall_s=time.monotonic() - started)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary, produced


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--ws", default="ws://127.0.0.1:8100/ws/call/")
    parser.add_argument("--jsonl", action="store_true",
                        help="stream one case per line instead of a final JSON array")
    parser.add_argument("--resume", action="store_true",
                        help="skip case IDs already completed in output")
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=1)
    parser.add_argument("--limit", type=int, default=None,
                        help="run at most this many pending cases")
    parser.add_argument("--case-timeout", type=float, default=180)
    parser.add_argument("--turn-timeout", type=float, default=45)
    parser.add_argument("--progress-every", type=int, default=10)
    return parser


def _validate_args(parser, args):
    for name in ("case_timeout", "turn_timeout"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be greater than zero")
    if args.progress_every <= 0:
        parser.error("--progress-every must be greater than zero")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")


async def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    cases = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        parser.error("input must be a JSON array of cases")
    await run_all(
        cases, args.output, ws=args.ws, jsonl=args.jsonl, resume=args.resume,
        concurrency=args.concurrency, limit=args.limit,
        case_timeout=args.case_timeout, turn_timeout=args.turn_timeout,
        progress_every=args.progress_every,
    )


if __name__ == "__main__":
    asyncio.run(main())
