"""Thêm lưới tuân thủ vào đầu `_chan_so` KHÔNG được che mất ba lưới số phía sau.

BẪY ĐÃ MẮC 07-09-2026, và bộ test 1267 bài KHÔNG bắt được. Khi nối hai lưới tuân
thủ vào đầu chuỗi, một dòng `return ra` bị thụt 16 dấu cách thay vì 20:

    if not da_chan_thu_nhap:
        ra, sua_tn = chan_gan_thu_nhap(...)
        if sua_tn:
            ...
        return ra              <- THOÁT Ở MỌI LƯỢT, không riêng lượt bị chặn
    if not da_chan_bia:        <- không bao giờ tới

Hậu quả đo trên bản diễn lại: AI đọc 9.5%, 13.5%, 14.5%, 19.5% - không mức nào có
trong `knowledge/` (ở đó chỉ có 7.9%, 6.5%, 0.5%...) - mà `CHẶN LÃI SUẤT BỊA` im
lặng suốt cả cuộc. Không test nào đỏ vì mọi test đều gọi thẳng TỪNG lưới; không
bài nào đi qua chuỗi.

BẢN TEST ĐẦU TIÊN CỦA CHÍNH FILE NÀY CŨNG SAI và vẫn xanh trên bản hỏng: nó đo
thụt lề rồi so với "cấp thân hàm", trong khi dòng hỏng nằm SÂU HƠN một cấp (nó ở
trong `if not da_chan_thu_nhap:`). Bài học: lưới canh phải được thử trên BẢN HỎNG
trước khi tin - đo sai cấp thì test xanh mà lỗi vẫn nguyên.

Bất biến thật sự bị vi phạm, và là thứ file này canh: mọi `return` thoát sớm
trong `_chan_so` phải nằm trong một `if` xét biến báo "lưới VỪA bắn" (`sua_*`).
Trả về khi lưới KHÔNG bắn nghĩa là bỏ qua mọi lưới phía sau.
"""
import ast
import inspect
import textwrap

from backend.pipeline.streaming_pipeline import StreamingPipeline


def _than_chan_so() -> ast.FunctionDef:
    src = textwrap.dedent(inspect.getsource(StreamingPipeline._generate_response))
    for nut in ast.walk(ast.parse(src)):
        if isinstance(nut, ast.FunctionDef) and nut.name == "_chan_so":
            return nut
    raise AssertionError("không tìm thấy `_chan_so` - đổi tên thì sửa test này")


def _ten_trong(nut) -> set[str]:
    return {n.id for n in ast.walk(nut) if isinstance(n, ast.Name)}


def test_moi_return_thoat_som_deu_nam_trong_dieu_kien_luoi_vua_ban():
    ham = _than_chan_so()
    cuoi = ham.body[-1]          # `return` cuối hàm là đường ra bình thường
    xau = []
    for nut in ast.walk(ham):
        if not isinstance(nut, ast.If):
            continue
        # `return` là con TRỰC TIẾP của một `if` -> `if` đó phải xét `sua_*`
        for con in nut.body:
            if isinstance(con, ast.Return) and con is not cuoi:
                if not any(t.startswith("sua") for t in _ten_trong(nut.test)):
                    xau.append((con.lineno, ast.unparse(nut.test)[:60]))
    assert not xau, (
        "có `return` thoát sớm trong `_chan_so` KHÔNG gắn với điều kiện 'lưới "
        "vừa bắn' - mọi lưới phía sau bị bỏ qua ở MỌI lượt:\n"
        + "\n".join(f"  dòng {ln} trong `if {t}`" for ln, t in xau))


def test_ba_luoi_so_van_con_trong_chuoi():
    """Chốt chặn thô: ba lưới số phải còn được GỌI trong `_chan_so`."""
    goi = {n.func.id for n in ast.walk(_than_chan_so())
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for ten in ("chan_lai_suat_bia", "chan_so_sai", "chan_tien_sai"):
        assert ten in goi, f"{ten} không còn được gọi trong `_chan_so`"
