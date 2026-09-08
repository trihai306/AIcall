"""Câu đệm do LLM sinh không được đọc lại chữ mà máy nghe SAI.

Cuộc gọi thật 1e8bd9de (07-09-2026, 17:42), lượt đầu:

    khách nói : "cho anh thông tin về KHOẢN VAY bên mình"
    STT nghe  : "ờ cho anh thông tin về KHOẢNG TAY bên mình"   (logprob -0.06, rất chắc)
    câu đệm   : "Dạ về KHOẢNG TAY bên em,"                     <- đọc thẳng cho khách
    AI        : "Anh/chị quan tâm về KHOẢNG TAY là về khoản vay đúng không ạ?"

Khách nghe máy đọc lại nguyên chữ vô nghĩa. Rất lộ.

VÌ SAO ĐỘ TIN CỦA STT KHÔNG CỨU ĐƯỢC: logprob -0.06 là mức RẤT CHẮC. Máy nghe
sai một cách tự tin, nên lọc theo độ tin không bắt được ca này.

Thứ phân biệt được: "khoản vay" có trong tài liệu nghiệp vụ, "khoảng tay" thì
không. Lời nhắc sinh câu đệm (`_NHAC_CAU_DEM`) bảo mô hình "Nhắc lại CHỦ ĐỀ khách
hỏi", nên nó trung thành chép lại - kể cả khi chủ đề đó là chữ rác.

Bộ lọc `loc_cau_dem_llm` đang có bốn luật (chữ số, quá dài, dấu cuối, rỗng) và
không luật nào hỏi "chữ này có thật trong nghiệp vụ không". Đây là luật thứ năm.

Vốn từ truyền TỪ NGOÀI VÀO chứ không dựng trong hàm: `filler_pick` cố ý không
import torch để test được trên máy không GPU - xem chú thích đầu module.
"""
from backend.services.filler_pick import loc_cau_dem_llm, tu_vung_tu_kho

# Vốn từ nghiệp vụ rút từ tài liệu thật (rất nhỏ, đủ cho test).
VON_TU = tu_vung_tu_kho([
    "Vay Tín Chấp Cá Nhân. Lãi suất từ 7.9%/năm. Hạn mức lên đến 500 triệu đồng.",
    "Thời gian giải ngân trong vòng 24 giờ sau khi phê duyệt.",
    "Hồ sơ cần căn cước công dân và sao kê lương ba tháng gần nhất.",
])


def test_bo_cau_dem_chua_chu_KHONG_co_trong_nghiep_vu():
    assert loc_cau_dem_llm("Dạ về khoảng tay bên em,", tu_vung=VON_TU) is None


def test_giu_cau_dem_toan_chu_co_that():
    ra = loc_cau_dem_llm("Dạ về thời gian giải ngân thì", tu_vung=VON_TU)
    assert ra == "Dạ về thời gian giải ngân thì,"


def test_tu_chuc_nang_khong_bi_tinh_la_la():
    """"Dạ", "về", "bên em", "thì" không có trong tài liệu nhưng là từ thường."""
    assert loc_cau_dem_llm("Dạ về hạn mức bên em thì", tu_vung=VON_TU) is not None


def test_khong_truyen_von_tu_thi_giu_nguyen_hanh_vi_cu():
    """Đường gọi chưa có vốn từ trong tay vẫn phải chạy như trước."""
    assert loc_cau_dem_llm("Dạ về khoảng tay bên em,") == "Dạ về khoảng tay bên em,"


def test_bon_luat_cu_van_nguyen():
    assert loc_cau_dem_llm("Dạ lãi suất 7.9% thì,", tu_vung=VON_TU) is None   # có số
    assert loc_cau_dem_llm("", tu_vung=VON_TU) is None                        # rỗng
    dai = "Dạ " + " ".join(["lãi"] * 30)
    assert loc_cau_dem_llm(dai, tu_vung=VON_TU) is None                       # quá dài


def test_von_tu_bo_dau_cau_va_chu_so():
    v = tu_vung_tu_kho(["Lãi suất: từ 7.9%/năm!"])
    assert "lãi" in v and "suất" in v and "năm" in v
    assert "7.9" not in v
