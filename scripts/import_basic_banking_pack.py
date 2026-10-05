"""Import authored service scripts through the existing editor; preserve edits."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
GROUP = "shinhan"
STEM = "nghiep_vu_co_ban_va_loi_thoai"


def main(args):
    raw = Path(args.pack).read_bytes()
    pack = json.loads(raw)
    entries = pack["responses"]
    keys = [row["key"] for row in entries]
    assert len(keys) == len(set(keys)) and entries
    source = Path(args.source).read_text(encoding="utf-8")
    assert all(row["answer"].strip() and row["answer"] in source for row in entries)
    digest = hashlib.sha256(raw).hexdigest()

    def request(path, data=None, form=False):
        headers = {}
        payload = None
        if data is not None:
            payload = (urlencode(data).encode() if form else
                       json.dumps(data, ensure_ascii=False).encode())
            headers["Content-Type"] = ("application/x-www-form-urlencoded" if form else
                                       "application/json")
        with urlopen(Request(args.base.rstrip("/") + path, payload, headers), timeout=120) as response:
            result = json.load(response)
        if result.get("error"):
            raise RuntimeError(result["error"])
        return result

    query = "?" + urlencode({"nhom": GROUP, "ten": STEM})
    # Read the source separately: a missing document is the expected first run.
    with urlopen(args.base.rstrip("/") + "/api/knowledge/noi-dung" + query, timeout=30) as response:
        existing = json.load(response)
    if "noi_dung" in existing:
        if existing["noi_dung"] != source:
            raise RuntimeError("Source differs from the pack; preserve operator edits and review first")
    elif str(existing.get("error", "")).startswith("Không có tài liệu"):
        request("/api/knowledge/luu", {"nhom": GROUP, "ten": STEM, "noi_dung": source}, True)
    else:
        raise RuntimeError(existing)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    mapping = old.get("entries", {}) if old.get("pack_sha256") == digest else {}
    report = {"pack_sha256": digest, "source": GROUP + "/" + STEM + ".md",
              "provenance": "authored_generic_service_script", "entries": mapping,
              "expected": len(entries), "created_this_run": 0}

    def save_report():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def mismatch(entry, row):
        if row is None:
            return "missing"
        if row.get("nguon") != "nhap_tay":
            return "origin is not operator-authored"
        if row.get("tra_loi") != entry["answer"]:
            return "answer differs; operator edit preserved"
        if row.get("cau_hoi") != entry.get("examples", []):
            return "examples differ; operator edit preserved"
        if not row.get("bat"):
            return "disabled; operator choice preserved"
        return ""

    current = request("/api/knowledge/hoi-dap" + query)["items"]
    by_id = {row["id"]: row for row in current}
    by_answer = {row["tra_loi"]: row for row in current if row.get("nguon") == "nhap_tay"}
    for index, entry in enumerate(entries, 1):
        recorded = mapping.get(entry["key"], {})
        row = by_id.get(recorded.get("id")) or by_answer.get(entry["answer"])
        if row is not None and mismatch(entry, row):
            raise RuntimeError(f"{entry['key']} / {row['id']}: {mismatch(entry, row)}")
        if row is None:
            result = request("/api/knowledge/hoi-dap", {
                "nhom": GROUP, "ten": STEM, "cau_hoi": entry.get("examples", []),
                "tra_loi": entry["answer"], "bat": True})
            row = result["item"]
            report["created_this_run"] += 1
            by_id[row["id"]] = row
            by_answer[row["tra_loi"]] = row
        mapping[entry["key"]] = {"id": row["id"], "category": entry["category"],
                                  "title": entry["title"]}
        save_report()
        if index % 5 == 0 or index == len(entries):
            print(json.dumps({"imported": index, "total": len(entries)}), flush=True)

    deadline = time.monotonic() + max(0, args.wait_voices)
    ids = {entry["id"] for entry in mapping.values()}
    while True:
        current = request("/api/knowledge/hoi-dap" + query)["items"]
        rows = [row for row in current if row["id"] in ids]
        live_by_id = {row["id"]: row for row in rows}
        report["saved"] = len(rows)
        report["enabled"] = sum(bool(row["bat"]) for row in rows)
        report["voice_ready"] = sum(bool(row["voice_ready"]) for row in rows)
        report["content_intact"] = all(
            live_by_id.get(mapping[entry["key"]]["id"], {}).get("tra_loi") == entry["answer"]
            for entry in entries)
        report["mismatches"] = [
            {"key": entry["key"], "id": mapping[entry["key"]]["id"], "reason": reason}
            for entry in entries
            if (reason := mismatch(entry, live_by_id.get(mapping[entry["key"]]["id"])))
        ]
        if len(ids) != len(entries):
            report["mismatches"].append({"reason": "mapped IDs are not distinct"})
        save_report()
        if report["mismatches"]:
            raise RuntimeError(json.dumps(report["mismatches"], ensure_ascii=True))
        print(json.dumps({k: report[k] for k in ("saved", "enabled", "voice_ready", "expected")}), flush=True)
        if report["voice_ready"] == len(entries) or time.monotonic() >= deadline:
            break
        time.sleep(10)
    assert report["saved"] == len(entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8100")
    parser.add_argument("--pack", default=str(ROOT / "data/templates/nghiep_vu_ngan_hang_co_ban.json"))
    parser.add_argument("--source", default=str(ROOT / "knowledge/shinhan/nghiep_vu_co_ban_va_loi_thoai.md"))
    parser.add_argument("--output", default=str(ROOT / "docs/basic_banking_pack_windows_20261001.json"))
    parser.add_argument("--wait-voices", type=int, default=360)
    main(parser.parse_args())
