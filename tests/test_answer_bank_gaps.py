"""Sổ lựa chọn đã nhớ, sổ câu chưa có đáp án và thống kê đường trả lời."""
import sqlite3
import threading

import pytest

from backend.models import db
from backend.services import answer_bank_gaps as gaps
from backend.services import answer_bank_selector as selector


@pytest.fixture
def so(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE TABLE hoi_dap (id TEXT PRIMARY KEY, tra_loi TEXT, bat INTEGER)")
    monkeypatch.setattr(db, "connection", lambda: conn)
    monkeypatch.setattr(db, "write_lock", threading.RLock())
    monkeypatch.setattr(gaps, "_prepared_conn", None)
    selector.quen_lua_chon()
    yield conn
    selector.quen_lua_chon()
    conn.close()


BANK = {"ab_1": {"id": "ab_1", "cau_hoi": ["lãi suất vay tín chấp bao nhiêu"],
                 "tra_loi": "Dạ lãi suất vay tín chấp từ 7.9% một năm ạ.", "san_pham": ""}}


def test_lua_chon_song_qua_lan_nap_lai_kho(so):
    words = selector.khoa_cau_hoi("vay tín chấp thì lãi tính sao em")
    gaps.ghi_lua_chon("", "", words, "vay tín chấp thì lãi tính sao em", "ab_1",
                      BANK["ab_1"]["tra_loi"])
    # Kho được THAY nguyên chiếc (khởi động lại, bộ học đẩy bản mới): bản RAM mất,
    # nhưng lượt đầu tiên vẫn đọc thẳng nhờ sổ trên đĩa - không phải hỏi lại Qwen.
    moi = {k: dict(v) for k, v in BANK.items()}
    row = selector.fast_direct("vay tín chấp thì lãi tính sao em", moi)
    assert row is not None and row["id"] == "ab_1" and row["tu_bo_nho"]


def test_lua_chon_het_hieu_luc_khi_dap_an_bi_sua(so):
    words = selector.khoa_cau_hoi("vay tín chấp thì lãi tính sao em")
    gaps.ghi_lua_chon("", "", words, "vay tín chấp thì lãi tính sao em", "ab_1",
                      BANK["ab_1"]["tra_loi"])
    sua = {"ab_1": {**BANK["ab_1"], "tra_loi": "Dạ lãi suất hiện là 8.5% một năm ạ."}}
    assert selector.fast_direct("vay tín chấp thì lãi tính sao em", sua) is None
    assert gaps.nap_lua_chon(sua) == {}


def test_xoa_lua_chon_thi_bo_chon_quen_luon(so):
    words = selector.khoa_cau_hoi("vay tín chấp thì lãi tính sao em")
    gaps.ghi_lua_chon("", "", words, "vay tín chấp thì lãi tính sao em", "ab_1",
                      BANK["ab_1"]["tra_loi"])
    bank = dict(BANK)
    assert selector.fast_direct("vay tín chấp thì lãi tính sao em", bank) is not None
    key = gaps.danh_sach_lua_chon()[0]["key"]
    assert gaps.xoa_lua_chon(key)
    assert selector.fast_direct("vay tín chấp thì lãi tính sao em", bank) is None


def test_cau_co_thong_tin_rieng_khong_duoc_ghi(so):
    cau = "số điện thoại của tôi là 0912345678 thì vay được không"
    gaps.ghi_lua_chon("", "", selector.khoa_cau_hoi(cau), cau, "ab_1", "x")
    gaps.ghi_luot(cau, "", {"mode": "generated"}, "Dạ được ạ.")
    assert gaps.danh_sach_lua_chon() == [] and gaps.danh_sach_thieu() == []
    # Thống kê thì vẫn đếm: nó không giữ chữ nào của khách.
    assert gaps.thong_ke()["so_luot"] == 1


def test_luot_mo_hinh_sinh_vao_so_va_cong_don(so):
    gaps.ghi_luot("em có người yêu chưa", "vay_tin_chap", {"mode": "generated"}, "Dạ em cảm ơn ạ.")
    # Cùng tập từ mang nghĩa, khác thứ tự và từ đệm -> cùng một dòng.
    gaps.ghi_luot("có người yêu chưa em", "vay_tin_chap", {"mode": "generated"}, "Dạ chưa ạ.")
    gaps.ghi_luot("lãi suất bao nhiêu", "vay_tin_chap", {"mode": "rule"}, "Dạ 7.9% ạ.")
    rows = gaps.danh_sach_thieu()
    assert len(rows) == 1 and rows[0]["so_lan"] == 2 and rows[0]["cau_mo_hinh"] == "Dạ chưa ạ."
    tk = gaps.thong_ke()
    assert tk["so_luot"] == 3 and tk["tong"] == {"generated": 2, "rule": 1}
    assert tk["ty_le_sinh"] == pytest.approx(0.667, abs=0.001) and tk["cau_thieu"] == 1


def test_trung_kho_thi_cau_thieu_tu_dong_dong_va_mo_lai_khi_truot(so):
    gaps.ghi_luot("em có người yêu chưa", "", {"mode": "generated"}, "Dạ em cảm ơn ạ.")
    gaps.ghi_luot("em có người yêu chưa", "", {"mode": "answer_bank", "answer_id": "ab_9"})
    assert gaps.danh_sach_thieu() == []
    assert gaps.danh_sach_thieu("answered")[0]["answer_id"] == "ab_9"
    # Đáp án đó bị tắt, câu lại rơi về mô hình -> phải hiện lại trong sổ.
    gaps.ghi_luot("em có người yêu chưa", "", {"mode": "generated"}, "Dạ em cảm ơn ạ.")
    assert gaps.danh_sach_thieu()[0]["so_lan"] == 2


def test_bo_qua_thi_khong_tu_mo_lai(so):
    gaps.ghi_luot("em có người yêu chưa", "", {"mode": "generated"}, "x")
    key = gaps.danh_sach_thieu()[0]["key"]
    assert gaps.dat_trang_thai(key, "ignored")
    gaps.ghi_luot("em có người yêu chưa", "", {"mode": "generated"}, "x")
    assert gaps.danh_sach_thieu() == [] and gaps.danh_sach_thieu("ignored")[0]["so_lan"] == 2


def test_khong_co_db_thi_im_lang(monkeypatch):
    monkeypatch.setattr(db, "connection", lambda: None)
    gaps.ghi_luot("lãi suất bao nhiêu", "", {"mode": "generated"}, "x")
    gaps.ghi_lua_chon("", "", frozenset({"a", "b", "c"}), "a b c", "ab_1", "x")
    assert gaps.nap_lua_chon({}) == {} and gaps.thong_ke()["so_luot"] == 0


def test_lua_chon_da_nho_khong_bi_cong_nhieu_y_chan(so):
    # "với" làm câu bị coi là hai yêu cầu; Qwen đã phân xử rồi thì không hỏi lại.
    cau = "anh phải bàn lại với bà xã đã"
    bank = {"ab_2": {"id": "ab_2", "cau_hoi": ["để anh hỏi ý vợ đã"],
                     "tra_loi": "Dạ vâng ạ, anh chị bàn thêm với gia đình ạ.", "san_pham": ""}}
    assert selector.fast_direct(cau, bank) is None
    gaps.ghi_lua_chon("", "", selector.khoa_cau_hoi(cau), cau, "ab_2", bank["ab_2"]["tra_loi"])
    selector.quen_lua_chon()
    row = selector.fast_direct(cau, bank)
    assert row is not None and row["id"] == "ab_2"


def test_cau_mau_trung_nguyen_chu_vuot_cong_phu_dinh(so):
    bank = {"ab_3": {"id": "ab_3", "cau_hoi": ["sao biết bên em không phải lừa đảo"],
                     "tra_loi": "Dạ anh chị cẩn thận như vậy là đúng ạ.", "san_pham": ""}}
    row = selector.fast_direct("Sao biết bên em không phải lừa đảo?", bank)
    assert row is not None and row["id"] == "ab_3"
    # Chỉ trùng tập từ (đảo thứ tự) thì cổng phủ định vẫn chặn như cũ.
    assert selector.fast_direct("bên em không phải lừa đảo sao biết", bank) is None


def test_luot_hen_lien_he_sau_cung_la_cau_kho_con_thieu(so):
    gaps.ghi_luot("nhà anh ở xa chi nhánh thì sao", "", {"mode": "kho_khong_co",
                  "reason": "kho_khong_co_1"}, "Dạ em xin ghi nhận ạ.")
    rows = gaps.danh_sach_thieu()
    # Câu hẹn lại không phải bản nháp đáp án, không điền sẵn vào ô soạn.
    assert len(rows) == 1 and rows[0]["cau_mo_hinh"] == ""
    assert gaps.thong_ke()["ty_le_sinh"] == 1.0


def test_cau_qwen_tu_hoi_vao_so_ma_khong_tinh_la_khach_hoi(so):
    gaps.ghi_thieu_tu_hoi("làm nghề tự do có vay được không", "vay_tin_chap")
    gaps.ghi_thieu_tu_hoi("làm nghề tự do có vay được không", "vay_tin_chap")
    rows = gaps.danh_sach_thieu()
    assert len(rows) == 1 and rows[0]["so_lan"] == 0 and rows[0]["che_do"] == "tu_hoi"
    # Khách thật hỏi đúng câu đó thì mới bắt đầu đếm.
    gaps.ghi_luot("làm nghề tự do có vay được không", "vay_tin_chap",
                  {"mode": "kho_khong_co", "reason": "kho_khong_co_0"})
    assert gaps.danh_sach_thieu()[0]["so_lan"] == 1


def test_dap_an_tu_soan_cho_duyet_roi_moi_bat(so):
    so.execute("ALTER TABLE hoi_dap ADD COLUMN cau_hoi TEXT")
    so.execute("ALTER TABLE hoi_dap ADD COLUMN san_pham TEXT")
    so.execute("ALTER TABLE hoi_dap ADD COLUMN updated_at REAL")
    so.execute("CREATE TABLE answer_bank_entries (hoi_dap_id TEXT PRIMARY KEY, source_path TEXT, evidence TEXT)")
    for i in ("ab_a", "ab_b"):
        so.execute("INSERT INTO hoi_dap (id,tra_loi,bat,cau_hoi,san_pham) VALUES (?,?,1,?,'')",
                   (i, "Dạ được ạ.", '["hồ sơ cần gì"]'))
        so.execute("INSERT INTO answer_bank_entries VALUES (?,?,?)", (i, "faq/x.md", "căn cứ"))
    gaps.cho_duyet(["ab_a", "ab_b"])
    assert [r[0] for r in so.execute("SELECT bat FROM hoi_dap")] == [0, 0]
    assert gaps.so_cho_duyet() == 2 and gaps.cau_hoi_cho_duyet() == ["hồ sơ cần gì"] * 2
    assert gaps.duyet(["ab_a"], True) == ["ab_a"]
    assert gaps.duyet(["ab_b"], False) == []
    assert so.execute("SELECT id,bat FROM hoi_dap").fetchall() == [("ab_a", 1)]
    assert so.execute("SELECT hoi_dap_id FROM answer_bank_entries").fetchall() == [("ab_a",)]
    # Id không nằm trong hàng chờ thì không được bật/xoá qua đường này.
    assert gaps.duyet(["ab_a"], False) == [] and gaps.so_cho_duyet() == 0


def test_nhom_tinh_huong_gan_doc_va_gom(so):
    so.execute("ALTER TABLE hoi_dap ADD COLUMN cau_hoi TEXT")
    so.execute("ALTER TABLE hoi_dap ADD COLUMN created_at REAL")
    so.execute("INSERT INTO hoi_dap (id,tra_loi,bat,cau_hoi) VALUES ('ab_x','Dạ vâng ạ.',1,'[\"anh đang họp\",\"chị đang bận\"]')")
    so.execute("INSERT INTO hoi_dap (id,tra_loi,bat,cau_hoi) VALUES ('ab_y','Dạ em chào ạ.',0,'[\"thế nhé em\"]')")
    gaps.dat_nhom("ab_x", "Khách bận")
    gaps.dat_nhom("ab_y", "Kết thúc cuộc gọi")
    assert gaps.nhom_cua("ab_x") == "Khách bận" and gaps.nhom_cua("khong_co") == ""
    nhom = {n["nhom"]: n for n in gaps.theo_nhom()}
    assert nhom["Khách bận"]["so_dap_an"] == 1 and nhom["Khách bận"]["so_cach_hoi"] == 2
    assert nhom["Kết thúc cuộc gọi"]["items"][0]["bat"] is False
    # Bộ chọn đưa nhãn này cho Qwen.
    assert '"situation":"Khách bận"' in selector._prompt(
        "anh đang bận", "", "", [], [("C1", {"id": "ab_x", "tra_loi": "Dạ vâng ạ.", "cau_hoi": []})])
    gaps.dat_nhom("ab_x", "")
    assert gaps.nhom_cua("ab_x") == ""


def test_cau_chao_ket_thuc_mo_bang_the_vay_doc_thang_cau_mau(so):
    bank = {"ab_k": {"id": "ab_k", "cau_hoi": ["thế nhé em", "vậy thôi nhé em"],
                     "tra_loi": "Dạ vâng ạ. Em chào anh chị ạ.", "san_pham": ""},
            "ab_d": {"id": "ab_d", "cau_hoi": ["anh muốn đăng ký"],
                     "tra_loi": "Dạ em xin ghi nhận nhu cầu ạ.", "san_pham": ""}}
    for cau in ("thế nhé em", "Vậy thôi nhé em."):
        row = selector.fast_direct(cau, bank)
        assert row is not None and row["id"] == "ab_k"
    # Câu nối tiếp thật, không trùng câu mẫu nào: vẫn phải đi đường neo lượt trước.
    assert selector.fast_direct("thế phí thì sao", bank) is None
