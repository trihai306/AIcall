"""Chỉ nhúng lại ĐÚNG THỨ VỪA ĐỔI, đừng nhúng cả kho.

Đo trên máy Win 06-09-2026:
    nhúng CẢ KHO (34 tình huống) : 2891ms
    nhúng MỘT tình huống         :   84ms   -> 34 lần

Mà mọi lần lưu/xoá đều nhúng cả kho, kể cả khi chỉ sửa CÂU ĐUÔI - thứ không hề
nằm trong vector tình huống. GPU đó dùng chung với F5, nên mỗi giây phí ở đây là
một giây tiếng của cuộc gọi phải xếp hàng.
"""
import backend.api.fillers as fillers


class RagGia:
    def __init__(self):
        self.lan = 0

    def embed(self, ds):
        self.lan += 1
        return [[1.0, 0.0, 0.0] for _ in ds]


class TH:
    def __init__(self, i):
        self.id, self.vi_du = i, ("a", "b")


class KhoGia:
    tinh_huong = (TH("x"), TH("y"), TH("z"))


class StateGia:
    def __init__(self):
        self.rag = RagGia()
        self.kho_vector = {}


def _dung(monkeypatch):
    st = StateGia()
    import backend.main as main
    monkeypatch.setattr(main, "app_state", st, raising=False)
    monkeypatch.setattr(fillers, "lay_kho_cho_nhung", lambda: KhoGia(), raising=False)
    return st


def test_nhung_ca_kho_cham_bao_nhieu_lan(monkeypatch):
    st = _dung(monkeypatch)
    fillers._nhung_lai_vi_du()
    assert st.rag.lan == 3, "mốc đối chứng: cả kho thì gọi embed mỗi tình huống một lần"
    assert set(st.kho_vector) == {"x", "y", "z"}


def test_luu_mot_tinh_huong_chi_nhung_mot(monkeypatch):
    st = _dung(monkeypatch)
    fillers._nhung_lai_vi_du()
    st.rag.lan = 0
    fillers._nhung_mot("y")
    assert st.rag.lan == 1, "sửa một tình huống mà nhúng lại cả kho"
    assert set(st.kho_vector) == {"x", "y", "z"}


def test_xoa_tinh_huong_khong_can_nhung(monkeypatch):
    st = _dung(monkeypatch)
    fillers._nhung_lai_vi_du()
    st.rag.lan = 0
    fillers._bo_mot("y")
    assert st.rag.lan == 0, "xoá thì chỉ cần bỏ khỏi sổ, không phải nhúng lại"
    assert set(st.kho_vector) == {"x", "z"}


def test_bo_tinh_huong_khong_co_thi_im_lang(monkeypatch):
    st = _dung(monkeypatch)
    fillers._nhung_lai_vi_du()
    fillers._bo_mot("khong-co")          # không được nổ
    assert set(st.kho_vector) == {"x", "y", "z"}
