"""Correctly decoded procedure questions must not be swallowed by loan amount."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.pipeline.tra_loi_khoan_vay import tra_loi

DOC = """# Vay tín chấp
## Thông tin sản phẩm
- Hạn mức: lên đến 500 triệu đồng
## Hồ sơ cần thiết
- CCCD
- Sao kê lương 3 tháng gần nhất
"""


@pytest.mark.parametrize("text", [
    "em muốn vay bốn trăm triệu thì thủ tục như thế nào",
    "anh muốn vay 400 triệu thì thủ tục ra sao",
    "hồ sơ vay như thế nào",
    "thủ tục cần những gì",
])
def test_procedure_intent_before_principal_acknowledgement(text):
    answer = tra_loi(text, DOC)
    assert answer and answer[0] == "ho_so_can_thiet"
    assert "căn cước" in answer[1] and "sao kê" in answer[1]
    assert "nằm trong trần" not in answer[1]


def test_no_procedure_source_does_not_invent_or_change_the_question():
    assert tra_loi("muốn vay 400 triệu thì thủ tục như thế nào",
                   DOC.split("## Hồ sơ")[0]) is None


def test_mentioning_procedure_is_not_automatically_a_procedure_question():
    answer = tra_loi("chưa hỏi thủ tục, anh muốn vay 400 triệu được không", DOC)
    assert answer and answer[0] == "nhu_cau_vay"
