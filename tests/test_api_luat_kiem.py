"""API luật kiểm chứng: bảng thuộc tính sửa được từ trang quản lý.

`doc_bang` chỉ trả thuộc tính ĐANG BẬT - tắt một cái thì nó biến khỏi danh sách
chứ không hiện ra với cờ tắt. Test dưới đây bám đúng hành vi đó.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import db

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _mo_db(tmp_path_factory):
    """API cần DB đã mở. `TestClient(app)` không chạy lifespan nên phải tự mở.

    Không mở thì `db.connection()` trả None và API trả danh sách RỖNG - xem
    `test_db_chua_mo_thi_tra_rong` bên dưới, đó là hành vi có chủ ý chứ không
    phải chỗ mù.
    """
    p = tmp_path_factory.mktemp("db") / "test.db"
    asyncio.run(db.init_db(str(p)))
    yield
    asyncio.run(db.close_db())


def test_doc_ra_danh_sach_thuoc_tinh():
    r = client.get("/api/luat-kiem/thuoc-tinh")
    assert r.status_code == 200
    ten = [x["ten"] for x in r.json()["thuoc_tinh"]]
    assert "lãi suất" in ten


def test_tat_roi_bat_lai_mot_thuoc_tinh():
    client.post("/api/luat-kiem/thuoc-tinh", json={"ten": "tuổi", "bat": False})
    ten = [x["ten"] for x in client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]]
    assert "tuổi" not in ten
    client.post("/api/luat-kiem/thuoc-tinh", json={"ten": "tuổi", "bat": True})
    ten = [x["ten"] for x in client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]]
    assert "tuổi" in ten


def test_sua_ten_khong_co_thi_bao_loi_chu_khong_im_lang():
    r = client.post("/api/luat-kiem/thuoc-tinh", json={"ten": "khong ton tai", "bat": False})
    assert "error" in r.json()


def test_khoi_phuc_mac_dinh_dua_lai_du_bang():
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    client.post("/api/luat-kiem/thuoc-tinh/khoi-phuc")
    r = client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]
    assert len(r) >= len(THUOC_TINH_MAC_DINH)


def test_db_chua_mo_thi_tra_rong(monkeypatch):
    """DB chưa mở -> danh sách rỗng, không nổ.

    App thật luôn mở DB trong lifespan trước khi phục vụ, nên đường này chỉ chạy
    khi có sự cố. Trả rỗng thay vì nổ là chủ ý: mất trang quản lý còn hơn sập
    cả backend. Ghi lại thành test để lần sau ai đổi thì biết mình đang đổi gì.
    """
    monkeypatch.setattr(db, "connection", lambda: None)
    assert client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"] == []
