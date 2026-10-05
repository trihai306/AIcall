import argparse
import json
import sqlite3

import pytest

from training.llm import shinhan_large_teacher as teacher
from training.llm import shinhan_progress as progress


def test_malformed_judge_batch_is_quarantined_after_three_attempts(tmp_path, monkeypatch):
    db = teacher.db_open(tmp_path / "pending.sqlite")
    db.execute("INSERT INTO questions(fact_id,normalized,question,answer,source_url,"
               "source_sha256,persona) VALUES (?,?,?,?,?,?,?)",
               ("activate_card", "activate", "Tôi vừa nhận thẻ, kích hoạt thẻ thế nào?",
                "Vào SOL để kích hoạt thẻ.", "https://shinhan.com.vn/source.pdf", "abc", "neutral"))
    db.commit()

    class Response:
        def __enter__(self):
            return [json.dumps({"message": {"content": '{"results":[]}'}}).encode()]

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(teacher.urllib.request, "urlopen", lambda *_, **__: Response())
    monkeypatch.setattr(teacher, "allowed", lambda *_, **__: True)
    args = argparse.Namespace(ollama_url="http://localhost:11434", availability_url="",
                              dedicated=True)
    card = {"id": "activate_card", "fact": "Có thể kích hoạt thẻ qua SOL.",
            "answer": "Vào SOL để kích hoạt thẻ.", "intent": "kích hoạt thẻ"}
    for _ in range(2):
        with pytest.raises(ValueError, match="Incomplete judge response"):
            teacher.judge_batch(db, {"activate_card": card}, args)
    assert teacher.judge_batch(db, {"activate_card": card}, args) == 0
    assert db.execute("SELECT status FROM questions").fetchone()[0] == "teacher_unscored"


def test_progress_separates_raw_reviewed_trained_and_eval(tmp_path, monkeypatch):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE questions(status TEXT)")
    db.executemany("INSERT INTO questions VALUES (?)",
                   [(x,) for x in ("pending_review", "teacher_pass", "teacher_reject", "approved")])
    db.execute("CREATE TABLE bulk_reviews(status TEXT)")
    db.executemany("INSERT INTO bulk_reviews VALUES (?)",
                   [("accepted",), ("rejected",), ("uncertain",)])
    monkeypatch.setattr(progress, "_runs", lambda: [{"run_id": "old", "model": "candidate",
        "dataset_rows": 30, "train_rows": 27, "holdout_rows": 3, "epochs": 1,
        "status": "candidate_evaluated", "quality_gate_passed": False}])
    monkeypatch.setattr(progress, "_eval_scores", lambda _: {"shinhan_heldout":
        {"passed": 6, "total": 6, "report": "report.json"}})
    report = progress.collect(db, max_per_fact=300, worker_state="running")
    assert report["questions"]["generated_unique"] == 4
    assert report["questions"]["approved_for_future_training"] == 1
    assert report["bulk_candidate"]["second_pass_accepted"] == 1
    assert report["training"]["training_examples_seen_across_runs"] == 27
    assert report["learning_checks"]["passed_cases"] == 6
    assert report["learning_checks"]["quality_gate_passed"] is False
    text = progress.render_text(report)
    assert "Câu thật sự dùng cập nhật model qua các lượt: 27" in text
    assert "Ứng viên lô lớn qua lọc lượt hai, chưa duyệt tay: 1" in text
    assert "Kiểm tra Shinhan: 6/6 ca đạt" in text
    assert "Kết luận chất lượng: chưa đạt" in text


def test_loaded_candidate_is_linked_to_the_matching_training_run(tmp_path, monkeypatch):
    ledger = tmp_path / "runs.jsonl"
    gguf = tmp_path / "candidate-gguf"
    ledger.write_text(json.dumps({"run_id": "run-1", "gguf_dir": str(gguf),
                                  "model": None, "status": "adapter_saved"}) + "\n")
    monkeypatch.setattr(progress, "RUNS", ledger)
    assert progress.link_model(gguf, "banking-shinhan-candidate")
    assert progress._runs()[0]["model"] == "banking-shinhan-candidate"
    assert progress._runs()[0]["status"] == "candidate_loaded"
    assert not progress.link_model(tmp_path / "other", "wrong-model")
