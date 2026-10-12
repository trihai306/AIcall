import asyncio
from decimal import Decimal
import json

import pytest

from scripts import thu_hoi_thoai_kho as runner


class FakeSocket:
    def __init__(self, server):
        self.server = server
        self.events = asyncio.Queue()
        self.sent = []

    async def __aenter__(self):
        self.server.active += 1
        self.server.max_active = max(self.server.max_active, self.server.active)
        self.server.connections.append(self)
        await self.events.put(json.dumps({"type": "session_connected"}))
        return self

    async def __aexit__(self, *_args):
        self.server.active -= 1

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        if message["type"] == "set_session":
            await self.events.put(json.dumps({"type": "session_updated"}))
            return
        if message["type"] != "text_soi":
            return
        await asyncio.sleep(self.server.delay)
        turn_id = message["turn_id"]
        if message["text"].startswith("SERVICE_ERROR"):
            await self.events.put(json.dumps({
                "type": "response_chunk", "text": "dở dang",
            }))
            await self.events.put(json.dumps({
                "type": "error", "message": "model unavailable",
            }))
            return
        # A tagged event from another turn must be ignored. The real server's
        # completion is currently untagged, so the following event is accepted.
        await self.events.put(json.dumps({
            "type": "response_chunk", "turn_id": turn_id + 100,
            "text": "stale",
        }))
        reply = "Dạ hạn mức là 100 triệu đồng"
        await self.events.put(json.dumps({"type": "response_chunk", "text": reply}))
        await self.events.put(json.dumps({
            "type": "turn_complete",
            "full_response": reply,
            "metrics": {
                "answer_route": {"mode": "answer_bank", "reason": "matched"},
                "du_kien_vay": {"khoan": {"so_tien": "100.00"}},
            },
        }))

    async def recv(self):
        return await self.events.get()


class FakeServer:
    def __init__(self, delay=0):
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.connections = []

    def connect(self, _url, **_kwargs):
        return FakeSocket(self)


def _case(case_id, question="xin hạn mức"):
    return {
        "ma": case_id,
        "san_pham": "vay",
        "luot": [{
            "khach": question,
            "expect": {
                "require": ["100 trieu"],
                "modes": ["answer_bank"],
                "facts": {"khoan": {"so_tien": 100}},
            },
        }],
    }


def test_check_keeps_text_rules_and_compares_numeric_facts_by_value():
    expected = {
        "require": ["lai suat"],
        "forbid": ["khong biet"],
        "modes": ["answer_bank"],
        "reasons": ["matched"],
        "facts": {"vay": {"lai": "1.00", "han": Decimal("12.0")}},
    }
    passed, issues = runner.check(
        "Dạ, lãi suất là 1% ạ",
        {"answer_route": {"mode": "answer_bank", "reason": "matched"},
         "du_kien_vay": {"vay": {"lai": Decimal("1"), "han": "12"}}},
        expected,
    )
    assert passed is True
    assert issues == []


def test_forbid_affirmative_scopes_negation_to_the_claim_clause():
    expected = {"forbid_affirmative": [r"(?:chac chan|dam bao).*duyet"]}
    accepted = (
        "Em không thể đảm bảo hồ sơ được duyệt.",
        "Không thể đảm bảo hồ sơ sẽ được duyệt.",
        "Em không thể nói hồ sơ chắc chắn được duyệt.",
        "Em không thể khẳng định rằng hồ sơ của anh sẽ được duyệt.",
        "Em không tư vấn rằng hồ sơ chắc chắn được duyệt.",
        'Nếu ai nói "hồ sơ chắc chắn được duyệt" thì đó là sai.',
    )
    rejected = (
        "Hồ sơ chắc chắn được duyệt ạ.",
        "Em không chắc gì, nhưng hồ sơ chắc chắn được duyệt.",
        "Hồ sơ không đủ vẫn chắc chắn được duyệt.",
    )
    for reply in accepted:
        assert runner.check(reply, {}, expected) == (True, []), reply
    for reply in rejected:
        passed, issues = runner.check(reply, {}, expected)
        assert passed is False, reply
        assert issues == ["affirmative forbidden: (?:chac chan|dam bao).*duyet"]

    interest_oracle = {"forbid_affirmative": [r"lai kep"]}
    assert runner.check("Khoản này không tính lãi kép.", {}, interest_oracle) == (True, [])
    assert runner.check("Khoản này tính lãi kép.", {}, interest_oracle) == (
        False, ["affirmative forbidden: lai kep"])
    early_payment = {"forbid_affirmative": [r"tra no truoc han"]}
    assert runner.check(
        "Không áp dụng miễn phí trả nợ trước hạn.", {}, early_payment) == (True, [])
    rate_claim = {"forbid_affirmative": [r"lai suat.*chac chan"]}
    assert runner.check(
        "Không thể đảm bảo lãi suất chắc chắn giữ nguyên.", {}, rate_claim) == (True, [])
    assert runner.check("Lãi suất chắc chắn giữ nguyên.", {}, rate_claim) == (
        False, ["affirmative forbidden: lai suat.*chac chan"])


def test_service_error_preserves_partial_row_and_stops_case(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr(runner.websockets, "connect", server.connect)
    case = {"ma": "bad", "luot": ["SERVICE_ERROR first", "must not run"]}

    record = asyncio.run(runner.execute_case(
        case, "ws://fake/", case_timeout=2, turn_timeout=1))

    assert record["_runner"]["completed"] is False
    assert record["ket_qua"][0]["response_chunks"] == ["dở dang"]
    assert record["ket_qua"][0]["error"]["message"] == "model unavailable"
    sent_turns = [item for item in server.connections[0].sent
                  if item["type"] == "text_soi"]
    assert [item["text"] for item in sent_turns] == ["SERVICE_ERROR first"]
    assert server.connections[0].sent[0]["customer_name"] == "Khách kiểm thử"


def test_jsonl_resume_skips_complete_assert_fail_but_retries_error(tmp_path, monkeypatch):
    output = tmp_path / "evidence.jsonl"
    complete_assert_fail = {
        "ma": "done", "luot": ["x"], "manual_review": True,
        "ket_qua": [{"khach": "x", "pass": False, "issues": ["missing: y"]}],
        "errors": [],
        "_runner": {"completed": True},
    }
    partial = {
        "ma": "retry", "luot": ["x"], "manual_review": True,
        "ket_qua": [{"khach": "x", "pass": False,
                      "error": {"message": "service error"}}],
        "errors": [{"type": "service_error"}],
        "_runner": {"completed": False},
    }
    output.write_text(
        json.dumps(complete_assert_fail) + "\n" + json.dumps(partial) + "\n{\"ma\":",
        encoding="utf-8",
    )
    server = FakeServer()
    monkeypatch.setattr(runner.websockets, "connect", server.connect)

    summary, produced = asyncio.run(runner.run_all(
        [{**_case("done"), "manual_review": True},
         {**_case("retry"), "manual_review": True},
         {**_case("pending"), "manual_review": True}], output,
        ws="ws://fake/", jsonl=True, resume=True,
        concurrency=1, limit=1, case_timeout=2, turn_timeout=1, progress_every=100,
    ))

    assert summary["skipped_resume"] == 1
    assert summary["selected_cases"] == 1
    assert summary["this_run"]["scored_pass"] == 1
    assert summary["this_run"]["scored_fail"] == 0
    assert summary["cumulative"]["scored_pass"] == 1
    assert summary["cumulative"]["scored_fail"] == 1
    assert summary["cumulative"]["pending_execution_cases"] == 1
    assert summary["manual_review"] == {
        "status": "pending_human_review",
        "cases_total": 3,
        "cases_with_evidence": 2,
        "cases_pending_execution": 1,
        "cases_ready_for_human_review": 2,
        "cases_pending_human_review": 3,
        "invariant_turns_scored": 2,
        "invariant_scored_pass": 1,
        "invariant_scored_fail": 1,
        "unscored_turns": 0,
    }
    assert [case["ma"] for case in produced] == ["retry"]
    assert produced[0]["_runner"]["completed"] is True
    assert len(server.connections) == 1
    raw_lines = output.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 3
    last = json.loads(raw_lines[-1])
    assert last["luot"] == _case("retry")["luot"]
    assert last["ket_qua"][0]["pass"] is True


def test_concurrency_is_bounded_and_default_output_remains_json_array(
        tmp_path, monkeypatch):
    output = tmp_path / "results.json"
    server = FakeServer(delay=0.01)
    monkeypatch.setattr(runner.websockets, "connect", server.connect)
    cases = [_case(f"case-{index}") for index in range(5)]

    summary, produced = asyncio.run(runner.run_all(
        cases, output, ws="ws://fake/", concurrency=2,
        case_timeout=2, turn_timeout=1, progress_every=100,
    ))

    assert server.max_active == 2
    assert summary["this_run"]["executed_cases"] == 5
    assert summary["this_run"]["newly_completed_cases"] == 5
    assert summary["cumulative"]["completed_cases"] == 5
    assert summary["this_run"]["turns"] == summary["this_run"]["scored_pass"] == 5
    assert (summary["this_run"]["scored_fail"] ==
            summary["this_run"]["unscored"] == summary["this_run"]["errors"] == 0)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert [case["ma"] for case in saved] == [case["ma"] for case in cases]
    assert len(produced) == 5


def test_jsonl_rejects_middle_corruption_but_allows_final_truncation(tmp_path):
    valid = json.dumps({"ma": "ok", "luot": [], "ket_qua": [],
                        "errors": [], "_runner": {"completed": True}})
    middle = tmp_path / "middle.jsonl"
    middle.write_text(valid + "\n{broken}\n" + valid + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"corrupt JSONL at line 2"):
        runner.latest_records(middle, True)

    final = tmp_path / "final.jsonl"
    final.write_text(valid + "\n{\"ma\":", encoding="utf-8")
    assert list(runner.latest_records(final, True)) == ["ok"]
    assert runner._is_completed({
        "luot": ["one", "two"],
        "ket_qua": [{"pass": True}],
        "errors": [],
        "_runner": {"completed": True},
    }) is False


def test_parser_defaults_and_limits_concurrency_to_one_or_two():
    args = runner.build_parser().parse_args(["in.json", "out.json"])
    assert args.concurrency == 1
    assert args.case_timeout == 180
    assert args.turn_timeout == 45
    try:
        runner.build_parser().parse_args(["in.json", "out.json", "--concurrency", "3"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("concurrency 3 must be rejected")
