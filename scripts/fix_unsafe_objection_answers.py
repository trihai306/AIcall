"""Replace only old unsupported market-ranking answers in an existing DB."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings


OLD = {
    "che_lai_cao": (
        "Lãi này bên em đã là ưu đãi thuộc tốp tốt nhất thị trường rồi ạ, do vay "
        "không tài sản thế chấp nên lãi sẽ hơi cao chút."
    ),
    "che_han_muc_thap": (
        "Hạn mức này bên em thuộc tốp cao trên thị trường rồi đó ạ, vay tín "
        "chấp nên không ngân hàng nào dám cho vay quá nhiều ạ."
    ),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    seed = json.loads(Path("data/hoi_dap_seed.json").read_text(encoding="utf-8"))
    new = {item["id"]: item["tra_loi"] for item in seed["hoi_dap"]
           if item["id"] in OLD}
    with sqlite3.connect(settings.db_path) as conn:
        for ma, old in OLD.items():
            row = conn.execute("SELECT tra_loi FROM hoi_dap WHERE id = ?",
                               (ma,)).fetchone()
            if row is None:
                print(f"{ma}: không có trong DB")
            elif row[0] == old:
                conn.execute("UPDATE hoi_dap SET tra_loi = ? WHERE id = ?",
                             (new[ma], ma))
                print(f"{ma}: đã thay câu khẳng định không có nguồn")
            elif row[0] == new[ma]:
                print(f"{ma}: đã cập nhật trước đó")
            else:
                print(f"{ma}: câu trả lời đã được tùy chỉnh, giữ nguyên")


if __name__ == "__main__":
    main()
