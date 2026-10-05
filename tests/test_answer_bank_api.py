from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import knowledge
from backend.services.answer_bank_learning import bo_hoc_tra_loi


def _status(enabled=True):
    return {
        "enabled": enabled, "model": "qwen3.5:9b",
        "config": {"questions_per_document": 120, "variants_per_answer": 4,
                   "learn_history": True},
        "stats": {"answers": 0, "questions": 0, "memory_questions": 0,
                  "voice_ready": 0, "voice_total": 0},
        "job": {"id": "", "status": "idle", "phase": "", "current_document": "",
                "documents_done": 0, "documents_total": 0, "answers_added": 0,
                "voice_done": 0, "voice_total": 0, "logs": [], "error": ""},
        "last_run": None,
    }


def test_answer_bank_routes_follow_shared_contract(monkeypatch):
    app = FastAPI()
    app.include_router(knowledge.router)
    client = TestClient(app)
    monkeypatch.setattr(bo_hoc_tra_loi, "trang_thai", lambda: _status())
    monkeypatch.setattr(bo_hoc_tra_loi, "configure", lambda **kw: _status(kw["enabled"]))
    monkeypatch.setattr(bo_hoc_tra_loi, "request_build", lambda full_rebuild=False: _status())
    monkeypatch.setattr(bo_hoc_tra_loi, "cancel", lambda: {**_status(),
                         "job": {**_status()["job"], "status": "cancelled"}})

    assert client.get("/api/knowledge/thu-vien-tu-dong").json()["model"] == "qwen3.5:9b"
    configured = client.post("/api/knowledge/thu-vien-tu-dong", json={
        "enabled": False, "questions_per_document": 120,
        "variants_per_answer": 4, "learn_history": True,
    }).json()
    assert configured["enabled"] is False
    assert client.post("/api/knowledge/thu-vien-tu-dong/build",
                       json={"full_rebuild": False}).status_code == 200
    assert client.post("/api/knowledge/thu-vien-tu-dong/cancel").json()["job"]["status"] == "cancelled"



def test_manual_document_endpoint_returns_current_provenance_bank(monkeypatch, tmp_path):
    import json
    import sqlite3

    from backend.models import db
    from backend.services import answer_bank_learning as learning
    from backend.services import knowledge_qa_service as qa

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(
        "CREATE TABLE hoi_dap (id TEXT PRIMARY KEY,cau_dem TEXT,cau_hoi TEXT NOT NULL,"
        "tra_loi TEXT NOT NULL,san_pham TEXT,bat INTEGER NOT NULL DEFAULT 1,"
        "created_at REAL,updated_at REAL)"
    )
    monkeypatch.setattr(db, "connection", lambda: conn)
    monkeypatch.setattr(learning, "_prepared_conn", None)
    root = tmp_path / "knowledge"
    folder = root / "products"
    folder.mkdir(parents=True)
    source = "Phí thường niên theo biểu phí."
    (folder / "the.md").write_text(source, encoding="utf-8")
    monkeypatch.setattr(knowledge, "GOC", root)
    monkeypatch.setattr(learning, "_knowledge_root", lambda: root.resolve())
    generated_calls = []
    voiced = []

    async def generated(doc, count, variants, fixed_questions=None):
        generated_calls.append((count, fixed_questions))
        return [{"cau_hoi": list(fixed_questions or ["Có phí thường niên không?"]),
                 "tra_loi": "Dạ phí thường niên theo biểu phí ạ.", "evidence": source}], {}

    async def runtime(*, build_voice=True):
        assert build_voice is False
        return {"so_dong": 1, "voice": None}

    async def voice(ids):
        voiced.extend(ids)

    monkeypatch.setattr(learning, "generate_document", generated)
    monkeypatch.setattr(qa, "nap_lai_duong_goi", runtime)
    monkeypatch.setattr(learning.AnswerBankLearning, "_voice_rows", lambda self, ids: voice(ids))
    app = FastAPI()
    app.include_router(knowledge.router)
    with TestClient(app) as client:
        result = client.post("/api/knowledge/tao-hoi-dap", data={
            "nhom": "products", "ten": "the", "so_cau": "120",
        }).json()
        assert result["ok"]
        assert generated_calls == [(120, None)]
        assert result["items"][0]["id"].startswith("ab_auto_")
        assert learning.row_is_current(result["items"][0]["id"])
        result = client.post("/api/knowledge/tao-hoi-dap", data={
            "nhom": "products", "ten": "the", "cau_hoi_nhan_vien": "Phí thu khi nào?",
        }).json()
        assert result["ok"]
        assert {row["nguon"] for row in result["items"]} == {"tu_dong", "nhan_vien"}
        listed = client.get("/api/knowledge/hoi-dap", params={"nhom": "products", "ten": "the"}).json()
        assert listed["so_dong"] == 2
        assert len(voiced) == 2
        assert all(learning.row_is_current(row["id"]) for row in listed["items"])
    assert {row[0] for row in conn.execute("SELECT origin FROM answer_bank_entries")} == {"auto", "staff"}
    assert json.loads(conn.execute("SELECT cau_hoi FROM hoi_dap WHERE id LIKE 'ab_staff_%'").fetchone()[0]) == ["Phí thu khi nào?"]
