"""Inspect wording when the customer requests northern, southern, or neutral speech."""
from __future__ import annotations

import argparse
from pathlib import Path

from evaluate_banking_style import ROOT, SYSTEM, chat
from backend.core.conversation_style import requested_region_note


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    source = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8-sig")
    for region in ("miền Bắc", "miền Nam", "trung tính"):
        messages = [
            {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
            {"role": "user", "content": f"Em nói theo cách {region} giúp tôi nhé. Thẻ Gold có hạn mức bao nhiêu?"},
        ]
        messages[0]["content"] += "\n\n" + requested_region_note(messages[1:])
        print(f"{region}: {chat(args.url, args.model, messages)}", flush=True)


if __name__ == "__main__":
    main()
