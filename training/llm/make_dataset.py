"""
Gom và chuẩn hoá dataset hội thoại tư vấn thành JSONL cho fine-tune.

Nguồn dữ liệu hỗ trợ (đặt trong data/training/):
  1. File .jsonl đã đúng format messages (từ API upload hoặc tự viết)
  2. File .txt transcript cuộc gọi, mỗi dòng "KH: ..." / "TV: ..."
     (KH = khách hàng, TV = tư vấn viên - giọng bạn muốn model học)

Output: data/training/merged_dataset.jsonl - mỗi dòng:
  {"messages": [{"role":"system",...},{"role":"user",...},{"role":"assistant",...}]}

Usage:
    python training/llm/make_dataset.py
    python training/llm/make_dataset.py --system "Bạn là chuyên viên tư vấn của công ty X..."
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Console Windows mặc định là cp1252: in chữ "Tổng" ra là ném UnicodeEncodeError
# và script thoát mã lỗi, dù merged_dataset.jsonl đã ghi xong ngay trước đó.
# Nhìn từ ngoài thì tưởng hỏng, nên ép UTF-8 cho luồng ra.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_DIR / "data" / "training"
OUTPUT_PATH = DATA_DIR / "merged_dataset.jsonl"

DEFAULT_SYSTEM = "Bạn là nhân viên tư vấn ngân hàng ABC, tên Lan, đang gọi điện cho khách. Trả lời tối đa 2 câu, xưng em, gọi khách là anh/chị."


def parse_transcript(path: Path, system_prompt: str) -> list[dict]:
    """Chuyển transcript 'KH:/TV:' thành các mẫu hội thoại nhiều lượt."""
    samples = []
    messages = [{"role": "system", "content": system_prompt}]
    pending_user = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        upper = line[:3].upper()
        if upper.startswith("KH:"):
            pending_user = line[3:].strip()
        elif upper.startswith("TV:"):
            reply = line[3:].strip()
            if pending_user and reply:
                messages.append({"role": "user", "content": pending_user})
                messages.append({"role": "assistant", "content": reply})
                # Mỗi lượt TV trả lời = 1 mẫu train (kèm toàn bộ ngữ cảnh trước đó)
                samples.append({"messages": list(messages)})
                pending_user = None

    return samples


# Tên cột chấp nhận được, viết thường không dấu. Người dùng sửa tiêu đề hoặc
# lưu từ Excel bản khác vẫn đọc được, khỏi phải khớp từng ký tự.
_COT_HOI = {"khach_hoi", "cau_khach_hoi", "khach", "hoi", "user", "question", "input"}
_COT_TRA_LOI = {"tu_van_tra_loi", "cau_tu_van_tra_loi", "tu_van", "tra_loi",
                "assistant", "answer", "output"}


def _chuan_ten_cot(ten: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (ten or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "d")
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


def parse_csv(path: Path, system_prompt: str) -> list[dict]:
    """Đọc bảng tính hai cột (câu khách hỏi / câu tư vấn trả lời).

    Mở bằng utf-8-sig: Excel trên Windows lưu CSV kèm BOM, đọc bằng utf-8
    thường thì BOM dính vào tên cột đầu tiên và cột đó không bao giờ khớp.
    """
    samples: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = [r for r in reader if any((c or "").strip() for c in r)]

    if not rows:
        return []

    # Dò cột theo tiêu đề; không nhận ra thì mặc định hai cột đầu.
    tieu_de = [_chuan_ten_cot(c) for c in rows[0]]
    i_hoi = next((i for i, c in enumerate(tieu_de) if c in _COT_HOI), None)
    i_tra = next((i for i, c in enumerate(tieu_de) if c in _COT_TRA_LOI), None)

    if i_hoi is None or i_tra is None:
        i_hoi, i_tra = 0, 1
        bat_dau = 0          # không có tiêu đề -> dòng đầu cũng là dữ liệu
        print(f"  [WARN] {path.name}: không nhận ra tiêu đề cột, dùng cột 1 và 2")
    else:
        bat_dau = 1

    for r in rows[bat_dau:]:
        if len(r) <= max(i_hoi, i_tra):
            continue
        hoi, tra_loi = (r[i_hoi] or "").strip(), (r[i_tra] or "").strip()
        if not hoi or not tra_loi:
            continue
        samples.append({"messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": hoi},
            {"role": "assistant", "content": tra_loi},
        ]})
    return samples


def validate_sample(obj: dict) -> str | None:
    """Trả về lý do lỗi, hoặc None nếu hợp lệ."""
    msgs = obj.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 2:
        return "thiếu messages"
    roles = [m.get("role") for m in msgs]
    if "assistant" not in roles:
        return "không có lượt assistant"
    for m in msgs:
        if not m.get("content", "").strip():
            return "có message rỗng"
    # Cảnh báo câu trả lời quá dài so với văn nói
    last_assistant = [m for m in msgs if m["role"] == "assistant"][-1]
    if len(last_assistant["content"].split()) > 60:
        return None  # vẫn nhận, nhưng sẽ đếm warning ở ngoài
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", default=DEFAULT_SYSTEM,
                        help="System prompt gắn vào các mẫu chuyển từ transcript")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        sys.exit(f"[ERROR] Chưa có thư mục {DATA_DIR}. Upload dataset qua web UI hoặc copy file vào đó.")

    samples: list[dict] = []

    # 1. JSONL có sẵn
    for f in sorted(DATA_DIR.glob("*.jsonl")):
        if f.name == OUTPUT_PATH.name:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f"  [WARN] {f.name}:{i+1} không phải JSON hợp lệ - bỏ qua")
                continue
            err = validate_sample(obj)
            if err:
                print(f"  [WARN] {f.name}:{i+1} {err} - bỏ qua")
                continue
            samples.append(obj)
        print(f"[OK] {f.name}")

    # 2. Transcript .txt
    for f in sorted(DATA_DIR.glob("*.txt")):
        converted = parse_transcript(f, args.system)
        if converted:
            samples.extend(converted)
            print(f"[OK] {f.name} -> {len(converted)} mẫu")

    # 3. Bảng tính .csv (mẫu cho người dùng tự điền)
    for f in sorted(DATA_DIR.glob("*.csv")):
        converted = parse_csv(f, args.system)
        if converted:
            samples.extend(converted)
            print(f"[OK] {f.name} -> {len(converted)} mẫu")
        else:
            print(f"  [WARN] {f.name}: không đọc được dòng nào")

    if not samples:
        sys.exit("[ERROR] Không có mẫu nào. Xem training/llm/README.md phần chuẩn bị dữ liệu.")

    # Khử trùng lặp. Các file dataset thường chồng lên nhau: một bản là bản cũ
    # đã được sửa và mở rộng thành bản mới, để cả hai trong thư mục là mẫu chung
    # bị đếm hai lần và model học lệch hẳn về chúng. Đo được: hai file 284 và
    # 229 mẫu có tới 137 mẫu GIỐNG HỆT nhau.
    #
    # So theo cặp (câu hỏi, câu trả lời) chứ không riêng câu hỏi: hội thoại
    # nhiều lượt cố ý dùng lại cùng một câu hỏi với đáp án khác nhau tuỳ ngữ
    # cảnh, khử theo câu hỏi là mất hết những mẫu đó.
    da_thay, giu = set(), []
    for s in samples:
        msgs = s.get("messages", [])
        hoi = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
        dap = next((m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
        khoa = (hoi.strip().lower(), dap.strip().lower(), len(msgs))
        if khoa in da_thay:
            continue
        da_thay.add(khoa)
        giu.append(s)

    if len(giu) < len(samples):
        print(f"\n[OK] Bỏ {len(samples) - len(giu)} mẫu trùng lặp "
              f"({len(samples)} -> {len(giu)})")
    samples = giu

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fw:
        for s in samples:
            fw.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\nTổng: {len(samples)} mẫu -> {OUTPUT_PATH}")

    # Soi phong cách theo đúng luật của system prompt lúc chạy thật. Trước đây
    # chỉ đếm ">40 từ" - một con số không khớp với bất kỳ quy tắc nào, nên mẫu
    # 35 từ dùng chữ số vẫn lọt qua sạch sẽ.
    sys.path.insert(0, str(PROJECT_DIR))
    try:
        from backend.core.dataset_rules import kiem_tra_tra_loi, GIOI_HAN_TU
    except ImportError:
        print("[WARN] Không nạp được bộ luật kiểm tra, bỏ qua bước soi phong cách.")
    else:
        vi_pham = []
        for s in samples:
            cuoi = [m for m in s["messages"] if m["role"] == "assistant"][-1]["content"]
            loi, _ = kiem_tra_tra_loi(cuoi)
            if loi:
                vi_pham.append((cuoi, loi))
        if vi_pham:
            print(f"\n[WARN] {len(vi_pham)}/{len(samples)} mẫu vi phạm phong cách "
                  f"(tối đa {GIOI_HAN_TU} từ, 2 câu, không chữ số, không liệt kê):")
            for cuoi, loi in vi_pham[:5]:
                print(f"   - {'; '.join(loi)}")
                print(f"     {cuoi[:100]}")
            if len(vi_pham) > 5:
                print(f"   ... và {len(vi_pham) - 5} mẫu nữa")
            print("       Model học theo DATA chứ không theo system prompt: train")
            print("       bằng mẫu dài dòng thì model sẽ nói dài dòng.")
    if len(samples) < 200:
        print(f"[WARN] Chỉ có {len(samples)} mẫu (<200). Fine-tune hiệu quả thấp;")
        print("       cân nhắc bổ sung data hoặc dùng system prompt + RAG thay thế.")
    # train.sh cần bash; Windows không có sẵn và chưa có bản .ps1 tương đương,
    # nên chỉ gọi thẳng train_lora.py trong venv training.
    if os.name == "nt":
        print("\nBước tiếp (Windows, chưa có train.ps1 cho LLM):")
        print("   .venv-train\\Scripts\\python.exe training\\llm\\train_lora.py")
        print("   Venv .venv-train phải có sẵn torch + unsloth (xem training/llm/train.sh).")
    else:
        print("\nBước tiếp: bash training/llm/train.sh")


if __name__ == "__main__":
    main()
