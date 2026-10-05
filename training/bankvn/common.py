from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Iterable


SPECIAL_TOKENS = [
    "<pad>",
    "<unk>",
    "<s>",
    "<|bankvn_end|>",
    "<|bankvn_system|>",
    "<|bankvn_user|>",
    "<|bankvn_assistant|>",
    "<|bankvn_tool_call|>",
    "<|bankvn_tool_result|>",
]

TOKENIZER_REQUIRED_FILES = [
    "tokenizer.model",
    "tokenizer.vocab",
    "tokenizer.json",
    "tokenizer_config.json",
]

TOKENIZER_CONFIG_REQUIRED = {
    "add_prefix_space": False,
}

ROLE_TOKEN = {
    "system": "<|bankvn_system|>",
    "user": "<|bankvn_user|>",
    "assistant": "<|bankvn_assistant|>",
    "tool": "<|bankvn_tool_result|>",
}

VI_STOPWORDS = {
    "và", "là", "của", "cho", "trong", "một", "những", "các", "được",
    "với", "không", "này", "đó", "khi", "để", "từ", "theo", "tôi", "anh",
    "chị", "em", "khách", "hàng", "ngân", "vay", "tiền", "tháng", "năm",
}

# Từ viết tắt/tên chuẩn cần giữ nguyên dù corpus tự nhiên được yêu cầu là tiếng Việt.
# Bộ lọc này chỉ đánh giá câu chữ tự nhiên, không dịch tên protocol/tool/API.
VI_ALLOWED_TERMS = {
    "atm", "api", "app", "bankvn", "cic", "csv", "email", "http", "https",
    "iban", "json", "kyc", "llm", "mobile", "nfc", "otp", "pin", "qr",
    "sms", "swift", "token", "url", "visa", "web", "wifi",
}

_FOREIGN_COMMON_WORDS = {
    "a", "about", "and", "are", "as", "at", "be", "by", "can", "for", "from",
    "has", "have", "how", "i", "if", "in", "is", "it", "my", "not", "of", "on",
    "or", "please", "the", "this", "to", "what", "when", "where", "which", "with",
    "you", "your",
}

_CJK_HANGUL = re.compile(
    "[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)
_HTML = re.compile(r"<[^>]+>")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_SPACE = re.compile(r"[ \t\f\v]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_LONG_NUMBER = re.compile(r"(?<!\d)\d{9,19}(?!\d)")
_VI_DIACRITICS = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    "úùủũụứừửữựýỳỷỹỵĂÂĐÊÔƠƯÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊ"
    "ÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = _HTML.sub(" ", text)
    text = _URL.sub(" ", text)
    lines = []
    for line in text.replace("\r", "\n").split("\n"):
        line = _SPACE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def redact_pii(text: str) -> str:
    text = _EMAIL.sub("<EMAIL>", text)
    text = _PHONE.sub("<SO_DIEN_THOAI>", text)
    return _LONG_NUMBER.sub("<SO_NHAY_CAM>", text)


def vietnamese_score(text: str) -> float:
    """Heuristic nhẹ, không phụ thuộc model language-id bên ngoài.

    Corpus mặc định đã gắn nhãn `vi`; heuristic này chủ yếu chặn đoạn ngoại ngữ
    lọt vào, đặc biệt CJK/Hangul, và loại văn bản Latin không có dấu hiệu Việt.
    """
    if not text or _CJK_HANGUL.search(text):
        return 0.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    dia = sum(c in _VI_DIACRITICS for c in letters) / len(letters)
    words = re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)
    if not words:
        return 0.0
    stop = sum(w in VI_STOPWORDS for w in words) / max(1, min(len(words), 80))
    # Một đoạn Việt chuẩn thường có cả dấu và hư từ; cho phép tài liệu kỹ thuật
    # nhiều mã/thuật ngữ bằng cách cộng hai tín hiệu thay vì bắt buộc cả hai.
    return min(1.0, dia * 5.0 + stop * 2.0)


def is_vietnamese(text: str, min_score: float = 0.18, min_chars: int = 80) -> bool:
    text = clean_text(text)
    return len(text) >= min_chars and vietnamese_score(text) >= min_score


def foreign_latin_ratio(text: str) -> float:
    """Tỷ lệ token Latin có dấu hiệu rõ là tiếng Anh, bỏ qua thuật ngữ whitelist."""
    words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ỹ]+", clean_text(text), re.UNICODE)]
    candidates = [w for w in words if w not in VI_ALLOWED_TERMS]
    if not candidates:
        return 0.0
    foreign = sum(w in _FOREIGN_COMMON_WORDS for w in candidates)
    return foreign / len(candidates)


def is_strict_vietnamese(text: str, min_score: float = 0.28, min_chars: int = 8,
                         max_foreign_ratio: float = 0.22) -> bool:
    """Gate chặt cho dữ liệu BankVN: câu tự nhiên phải là tiếng Việt.

    Vẫn cho phép các mã ngân hàng/kỹ thuật chuẩn như OTP, KYC, CIC, JSON, API.
    """
    text = clean_text(text)
    if len(text) < min_chars or has_cjk_hangul(text):
        return False
    if vietnamese_score(text) < min_score:
        return False
    return foreign_latin_ratio(text) <= max_foreign_ratio


def has_cjk_hangul(text: str) -> bool:
    return bool(_CJK_HANGUL.search(text or ""))


def stable_hash(text: str) -> str:
    normalized = _SPACE.sub(" ", unicodedata.normalize("NFC", text).lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def require_bankvn_tokenizer_files(path: str | Path) -> Path:
    """Fail sớm nếu checkpoint/tokenizer thiếu asset SentencePiece bắt buộc."""
    root = Path(path)
    missing = [name for name in TOKENIZER_REQUIRED_FILES
               if not (root / name).is_file()]
    if missing:
        raise RuntimeError(
            f"Tokenizer BankVN thiếu asset bắt buộc tại {root}: {missing}"
        )
    config_path = root / "tokenizer_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RuntimeError(f"tokenizer_config.json BankVN không hợp lệ tại {root}") from exc
    for key, expected in TOKENIZER_CONFIG_REQUIRED.items():
        if config.get(key) is not expected:
            raise RuntimeError(
                f"Tokenizer BankVN thiếu metadata GGUF bắt buộc: {key}={expected!r}; "
                f"actual={config.get(key)!r} tại {config_path}"
            )
    return root


def ensure_bankvn_tokenizer_config(path: str | Path) -> Path:
    """Ghi metadata tokenizer cần để HF, llama.cpp và Ollama tokenize giống nhau."""
    root = Path(path)
    config_path = root / "tokenizer_config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update(TOKENIZER_CONFIG_REQUIRED)
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def save_bankvn_tokenizer(tokenizer, target: str | Path,
                          source: str | Path | None = None) -> Path:
    """Lưu tokenizer HF và giữ asset SentencePiece cần cho llama.cpp/GGUF."""
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(target_path)
    ensure_bankvn_tokenizer_config(target_path)

    if source is not None:
        source_path = Path(source)
        for name in ("tokenizer.model", "tokenizer.vocab"):
            src = source_path / name
            dst = target_path / name
            if src.exists() and src.resolve() != dst.resolve():
                shutil.copy2(src, dst)

    return require_bankvn_tokenizer_files(target_path)


def iter_input_files(paths: Iterable[str | Path]) -> Iterable[Path]:
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix.lower() in {".txt", ".md", ".jsonl", ".json"}:
                    yield f
        elif p.is_file():
            yield p


def read_documents(path: Path) -> Iterable[dict]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Với file dài, tách theo block để một doc lỗi không làm mất cả file.
        blocks = re.split(r"\n\s*\n", text)
        for i, block in enumerate(blocks):
            if block.strip():
                yield {"text": block, "source": str(path), "id": f"{path.name}:{i}"}
        return
    if suffix == ".jsonl":
        with path.open(encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = obj.get("text") or obj.get("content") or obj.get("cau") or ""
                if text:
                    yield {"text": str(text), "source": obj.get("source") or str(path),
                           "id": obj.get("id") or f"{path.name}:{i}"}
        return
    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError):
            return
        rows = data if isinstance(data, list) else [data]
        for i, obj in enumerate(rows):
            if not isinstance(obj, dict):
                continue
            text = obj.get("text") or obj.get("content") or obj.get("cau") or ""
            if text:
                yield {"text": str(text), "source": obj.get("source") or str(path),
                       "id": obj.get("id") or f"{path.name}:{i}"}


def render_messages(tokenizer, messages: list[dict], max_length: int) -> dict:
    """Render chat và chỉ tính loss trên lượt assistant/tool-call."""
    ids: list[int] = [tokenizer.bos_token_id]
    labels: list[int] = [-100]
    end_id = tokenizer.convert_tokens_to_ids("<|bankvn_end|>")
    tool_call_id = tokenizer.convert_tokens_to_ids("<|bankvn_tool_call|>")

    for msg in messages:
        role = msg.get("role", "")
        if role not in ROLE_TOKEN:
            continue
        role_id = tokenizer.convert_tokens_to_ids(ROLE_TOKEN[role])
        ids.append(role_id)
        labels.append(-100)

        if role == "assistant" and msg.get("tool_calls"):
            call = msg["tool_calls"][0]
            function = call.get("function", call)
            payload = {
                "name": function.get("name", ""),
                "arguments": function.get("arguments") or {},
            }
            body_ids = [tool_call_id] + tokenizer.encode(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                add_special_tokens=False,
            )
        else:
            body_ids = tokenizer.encode(str(msg.get("content") or ""), add_special_tokens=False)

        ids.extend(body_ids)
        ids.append(end_id)
        if role == "assistant":
            labels.extend(body_ids)
            labels.append(end_id)
        else:
            labels.extend([-100] * (len(body_ids) + 1))

    ids = ids[:max_length]
    labels = labels[:max_length]
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}
