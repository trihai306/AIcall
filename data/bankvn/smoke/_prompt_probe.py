import json
import sys
from pathlib import Path

from transformers import TokenizersBackend


model_dir = Path(sys.argv[1])
data_path = Path(sys.argv[2])
tok = TokenizersBackend.from_pretrained(model_dir)

end_id = tok.convert_tokens_to_ids("<|bankvn_end|>")
assistant_id = tok.convert_tokens_to_ids("<|bankvn_assistant|>")
role_tokens = {
    "system": "<|bankvn_system|>",
    "user": "<|bankvn_user|>",
    "tool": "<|bankvn_tool_result|>",
}

rows = [
    json.loads(line)
    for line in data_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

results = []
for row_no, obj in enumerate(rows, 1):
    segmented = [tok.bos_token_id]
    prompt_parts = []
    for msg in obj["messages"]:
        if msg["role"] == "assistant":
            break
        marker = role_tokens[msg["role"]]
        content = str(msg.get("content") or "")
        segmented.append(tok.convert_tokens_to_ids(marker))
        segmented.extend(tok.encode(content, add_special_tokens=False))
        segmented.append(end_id)
        prompt_parts.extend([marker, content, "<|bankvn_end|>"])
    segmented.append(assistant_id)
    prompt_parts.append("<|bankvn_assistant|>")

    raw_prompt = "".join(prompt_parts)
    whole = [tok.bos_token_id] + tok.encode(raw_prompt, add_special_tokens=False)
    mismatch = next(
        (i for i, (a, b) in enumerate(zip(segmented, whole)) if a != b),
        None,
    )
    if mismatch is None and len(segmented) != len(whole):
        mismatch = min(len(segmented), len(whole))

    results.append(
        {
            "row": row_no,
            "segmented_len": len(segmented),
            "whole_len": len(whole),
            "same": segmented == whole,
            "first_mismatch": mismatch,
            "segmented_at_mismatch": (
                segmented[max(0, mismatch - 4): mismatch + 5]
                if mismatch is not None
                else []
            ),
            "whole_at_mismatch": (
                whole[max(0, mismatch - 4): mismatch + 5]
                if mismatch is not None
                else []
            ),
            "raw_prompt": raw_prompt,
        }
    )

print(json.dumps(results, ensure_ascii=False, indent=2))
