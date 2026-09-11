"""Câu đệm đã nêu chủ đề thì câu trả lời không được nêu lại ở ngay chữ đầu.

VÌ SAO CÓ FILE NÀY. Diễn lại cuộc gọi `08c0d3e0` (11-09-2026), lượt khách hỏi
"lãi suất vay tín chấp bao nhiêu":

    câu đệm : "Dạ lãi suất bên em thì,"
    trả lời : "Lãi suất vay tín chấp là từ 7.9%/năm ạ."
    log     : "LLM: dùng bản đã nghĩ sẵn, bỏ qua sinh mới"

Khách nghe "lãi suất ... lãi suất" liền nhau. Gốc không nằm ở mô hình mà ở ĐƯỜNG
câu trả lời đi: bản NGHĨ SẴN sinh lúc khách còn đang nói, khi chưa có câu đệm
nào, nên nó KHÔNG có `prefill` và mở đầu bằng cả câu như thể chưa ai nói gì.
Đường sinh mới (có prefill) thì hầu như không lặp: đo 11-09 trên Win, 6 tình
huống × 3 câu mở đầu × 8 lần, chỉ 1-2/24 lượt nêu lại.

Bỏ bản nghĩ sẵn thì mất ~220ms mỗi lượt. Nên cắt ở tầng chữ: đầu lượt, nếu câu
trả lời mở bằng đúng cụm chủ đề câu đệm vừa đọc thì bỏ cụm đó.
"""
from backend.pipeline.text_normalizer import BotLichSu


def dau_luot(cau_dem: str, *manh: str) -> list[str]:
    bo = BotLichSu(bo_da=True, cau_dem=cau_dem)
    return [bo(m) for m in manh]


# --- Cắt cụm chủ đề câu đệm vừa đọc ------------------------------------------

def test_ban_nghi_san_nhac_lai_chu_de_thi_bo_cum_do():
    """Đúng câu trong bản diễn lại."""
    ra = dau_luot("Dạ lãi suất bên em thì,",
                  "Lãi suất vay tín chấp là từ 7.9%/năm ạ.")[0]
    assert not ra.lower().startswith("lãi suất"), ra
    assert "vay tín chấp là từ 7.9%/năm" in ra.lower()


def test_bo_ca_chu_la_con_treo_sau_cum_chu_de():
    """"Dạ về lãi suất thì, là từ 7.9%" - chữ "là" treo đầu câu nghe cụt."""
    ra = dau_luot("Dạ về lãi suất thì,", "Lãi suất là từ 7.9%/năm ạ.")[0]
    assert ra.lower().startswith("từ 7.9%"), ra


def test_cum_chu_de_dai_hon_hai_tu():
    ra = dau_luot("Dạ về hồ sơ cần chuẩn bị thì,",
                  "Hồ sơ cần CMND và sao kê lương ba tháng ạ.")[0]
    assert ra.startswith("CMND"), ra


def test_da_o_dau_van_bo_duoc_roi_moi_cat_chu_de():
    ra = dau_luot("Dạ hạn mức bên em thì,",
                  "Dạ hạn mức vay tín chấp tối đa 500 triệu đồng ạ.")[0]
    assert not ra.lower().startswith(("dạ", "hạn mức")), ra
    assert "500 triệu" in ra


# --- KHÔNG cắt ------------------------------------------------------------

def test_nhac_chu_de_trong_dieu_kien_la_noi_dung_khong_phai_lap():
    """"Dạ về trường hợp có nợ xấu thì, nếu nợ xấu nhóm 3..." - "nếu" đứng
    trước nên đây là mệnh đề điều kiện, bỏ đi là mất nội dung."""
    ra = dau_luot("Dạ về trường hợp có nợ xấu thì,",
                  "Nếu nợ xấu nhóm 3 trở lên tại CIC, hồ sơ khó duyệt ạ.")[0]
    assert ra.lower().startswith("nếu nợ xấu nhóm 3"), ra


def test_khong_cat_dai_tu_xung_ho():
    """"anh chị" có trong câu đệm nhưng là chủ ngữ, không phải chủ đề."""
    ra = dau_luot("Dạ em thông tin ngay cho anh chị,",
                  "Anh chị cần chuẩn bị căn cước công dân ạ.")[0]
    assert ra.lower().startswith("anh chị cần"), ra


def test_mot_tu_trung_thi_khong_cat():
    """"vay" có trong "Dạ về hạn mức vay thì," nhưng một chữ chưa phải cụm chủ đề."""
    ra = dau_luot("Dạ về hạn mức vay thì,",
                  "Vay tín chấp lên đến 500 triệu đồng ạ.")[0]
    assert ra.lower().startswith("vay tín chấp lên đến"), ra


def test_chi_cat_o_manh_dau_luot():
    ra = dau_luot("Dạ lãi suất bên em thì,",
                  "Từ 7.9%/năm ạ.", "Lãi suất ưu đãi áp dụng 6 tháng đầu.")
    assert ra[1].startswith("Lãi suất ưu đãi"), ra


def test_khong_co_cau_dem_giu_nguyen_hanh_vi_cu():
    bo = BotLichSu(bo_da=True)
    assert bo("Lãi suất vay tín chấp là từ 7.9%/năm ạ.").startswith("Lãi suất vay")


# --- Nơi gọi: CHỈ câu trả lời của mô hình ------------------------------------

def test_cau_nguyen_van_khong_bi_cat():
    """Câu bảng hỏi-đáp và lượt thường gặp phát bằng TIẾNG DỰNG SẴN, chữ và tiếng
    phải khớp nhau từng chữ - cắt chữ ở đó là chữ một đằng tiếng một nẻo, lại
    còn sửa câu kịch bản đã duyệt. Chỉ câu mô hình viết mới được cắt."""
    import inspect
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    src = inspect.getsource(StreamingPipeline._generate_response)
    goi = src[src.index("bot_lich_su = BotLichSu("):]
    goi = goi[:goi.index("\n\n")]
    assert "cau_dem=" in goi, "BotLichSu chưa nhận câu đệm"
    dong = next(l for l in src.splitlines() if "cau_dem_mo_hinh =" in l)
    assert "dap_san" in dong and "doc_nguyen_van" in dong, dong


# --- Hâm cache TTS phải hâm ĐÚNG chữ sẽ phát --------------------------------
#
# Bản nghĩ sẵn được dựng tiếng trước mảnh đầu (`_manh_dau_ham_cache`) để lượt thật
# khỏi chờ F5: bản diễn lại ghi "TTS_mảnh_đầu 0ms" đúng ở lượt lặp chủ đề. Cache
# khoá theo NGUYÊN VĂN chữ, nên cắt chủ đề mà vẫn hâm chữ cũ là trượt cache và
# khách chờ thêm một mảnh F5 (~450ms) đúng ở những lượt được sửa.

TRA_LOI = "Lãi suất vay tín chấp là từ 7.9%/năm ạ. Anh chị cần tư vấn thêm không ạ?"
MO_DAU_LAI = ("Dạ về lãi suất thì,", "Dạ lãi suất bên em thì,", "Dạ mức lãi hiện tại,")


def _manh_phat_that(cau_dem: str) -> str:
    from backend.pipeline.text_chunker import chia_ca_luot
    return BotLichSu(bo_da=True, cau_dem=cau_dem)(chia_ca_luot(TRA_LOI)[0].strip())


def test_ham_cache_dung_ban_da_cat_chu_de():
    """Hai trên ba mẩu mở đầu của hoi_lai_suat làm mảnh đầu bị cắt - hâm bản đó."""
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    ham = StreamingPipeline._manh_dau_ham_cache(TRA_LOI, mo_dau=MO_DAU_LAI)
    assert ham == _manh_phat_that("Dạ lãi suất bên em thì,")
    assert ham == _manh_phat_that("Dạ về lãi suất thì,")


def test_ham_cache_tinh_huong_khong_neu_chu_de_thi_nhu_cu():
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    ham = StreamingPipeline._manh_dau_ham_cache(TRA_LOI, mo_dau=("Dạ vâng ạ,",))
    assert ham == StreamingPipeline._manh_dau_ham_cache(TRA_LOI)
    assert ham == _manh_phat_that("Dạ vâng ạ,")
