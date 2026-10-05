import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from training.bankvn.common import ensure_bankvn_tokenizer_config


PATHS = [
    Path("models/bankvn/tokenizer-sp-smoke6"),
    Path("models/bankvn/pretrain/sp-smoke6-final/final"),
    Path("models/bankvn/sft/bankvn-smoke6-final/final"),
    Path("models/bankvn/sft/bankvn-smoke6-overfit/final"),
]

for path in PATHS:
    config_path = ensure_bankvn_tokenizer_config(path)
    print(config_path)
