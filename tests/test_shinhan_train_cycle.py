import hashlib
import json

from training.llm import shinhan_train_cycle as cycle


def _row(question: str) -> dict:
    return {"messages": [{"role": "system", "content": "Nguồn Shinhan"},
                         {"role": "user", "content": question},
                         {"role": "assistant", "content": "Dạ, theo nguồn ạ."}]}


def test_bulk_training_requires_exact_hash_and_audited_sample(tmp_path, monkeypatch):
    manual = tmp_path / "manual.jsonl"
    bulk = tmp_path / "bulk.jsonl"
    audit = tmp_path / "audit.json"
    output = tmp_path / "train.jsonl"
    manual.write_text(json.dumps(_row("Câu hỏi duyệt tay"), ensure_ascii=False) + "\n")
    bulk.write_text("".join(json.dumps(_row(f"Câu hỏi {i}"), ensure_ascii=False) + "\n"
                            for i in range(900)))
    monkeypatch.setattr(cycle, "MANUAL_DATASET", manual)
    monkeypatch.setattr(cycle, "BULK_DATASET", bulk)
    monkeypatch.setattr(cycle, "BULK_AUDIT", audit)
    monkeypatch.setattr(cycle, "DATASET", output)
    assert cycle.assemble_dataset()[2] == "awaiting_bulk_shortlist_and_audit"
    audit.write_text(json.dumps({"shortlist_sha256": "wrong", "sample_size": 100,
                                 "errors": 0}))
    assert cycle.assemble_dataset()[2] == "bulk_audit_stale_for_current_shortlist"
    digest = hashlib.sha256(bulk.read_bytes()).hexdigest()
    rows = [json.loads(line) for line in bulk.read_text().splitlines()]
    items = [{"index": i, "scenario_id": None,
              "question": rows[i]["messages"][-2]["content"],
              "answer": rows[i]["messages"][-1]["content"],
              "decision": i >= 4} for i in range(100)]
    audit.write_text(json.dumps({"shortlist_sha256": digest, "sample_size": 100,
                                 "errors": 4, "items": items}))
    assert cycle.assemble_dataset()[2] == "bulk_audit_quality_failed"
    for item in items[:2]:
        item["decision"] = True
    audit.write_text(json.dumps({"shortlist_sha256": digest, "sample_size": 100,
                                 "errors": 2, "items": items}))
    assert cycle.assemble_dataset() == (1, 900, "ready")
    assert len(output.read_text().splitlines()) == 901


def test_train_cycle_waits_for_thousand_diverse_rows(monkeypatch):
    monkeypatch.setattr(cycle, "free_gib", lambda: 14.0)
    monkeypatch.setattr(cycle, "allowed", lambda *_, **__: True)
    old = [{"dataset_rows": 145, "dataset_sha256": "old"}]
    assert cycle.ready(900, "new", old).startswith("need_1000_total")
    assert cycle.ready(1000, "new", old) == "ready"
    assert cycle.ready(1000, "old", old) == "same_dataset_already_trained"
