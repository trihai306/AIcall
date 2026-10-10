"""Hai lưới TUÂN THỦ, chạy cùng chỗ với `chan_so_sai` - ngay trước khi sang TTS.

Khác với ba lưới số (`chan_so_sai` / `chan_lai_suat_bia` / `chan_tien_sai`): chúng
hỏi "con số này có căn cứ không", còn hai lưới ở đây hỏi "câu này có ĐƯỢC PHÉP nói
không" và "con số này đang gán cho AI". Con số đúng vẫn có thể sai chủ thể - đó
chính là lỗ hổng đã lọt.

Cả hai sinh ra từ bản diễn lại cuộc 08c0d3e0 (07-09-2026). Xem
`tests/test_chan_tuan_thu.py` cho nguyên văn hai câu hỏng và cách truy ra gốc.

VÌ SAO LÀ LƯỚI CHỨ KHÔNG PHẢI PROMPT: dự án đã thử dặn bằng prompt ba kiểu và
hỏng ba kiểu khác nhau (xem chú thích `prefill` trong `llm_service`). Với tư vấn
tài chính thì "phần lớn lượt sẽ đúng" không phải một bảo đảm.
"""
import re
import unicodedata

# --- Lưới 1: chữ không được phép nói -------------------------------------

# Từ mà nhân viên ngân hàng TUYỆT ĐỐI không nói với khách. Không phải danh sách
# từ thô tục - đây là những từ hàm ý làm sai quy trình, và một câu duy nhất lọt
# ra là đủ thành bằng chứng chống lại chính ngân hàng.
#
# Mô hình sinh ra chúng khi tài liệu nói KHÔNG mà nó vẫn muốn giúp khách: cuộc
# 08c0d3e0 khách hỏi nợ xấu, tri thức sản phẩm ghi "Không có nợ xấu tại CIC" là
# điều kiện, và mô hình đáp "bên em vẫn có cách lách để anh/chị vay được".
#
# Khớp theo TỪ (có ranh giới hai đầu) chứ không phải chuỗi con: "lách" nằm trong
# một câu bình thường thì không sao, nhưng chặn theo chuỗi con là chặn oan cả
# những từ chứa nó. Có test canh (`test_khong_bat_nham_tu_chua_chuoi_con`).
TU_CAM: tuple[str, ...] = (
    "lách luật", "lách", "chạy hồ sơ", "chạy điểm", "làm giả", "khai khống",
    "khai gian", "bao đậu", "bao duyệt", "đi cửa sau", "chống lưng", "lo lót",
)

# Câu thay khi dính chữ cấm. Nói THẲNG là còn tuỳ hồ sơ, rồi mời trao đổi tiếp -
# đó là điều đúng và cũng là điều tài liệu thật sự cho phép nói.
CAU_THAY_TU_CAM = ("Dạ trường hợp này còn tuỳ hồ sơ cụ thể, "
                   "em xin phép trao đổi thêm với anh chị ạ.")

_RANH = r"(?:^|[\s,\.\!\?\:\;\"'\(\)])"
_TU_CAM_RE = re.compile(
    _RANH + "(" + "|".join(re.escape(t) for t in TU_CAM) + ")" + r"(?=$|[\s,\.\!\?\:\;\"'\(\)])",
    re.IGNORECASE)


def chan_tu_cam(text: str) -> tuple[str, str | None]:
    """Thay CẢ câu nếu nó chứa chữ cấm. Trả (văn bản, mô tả chỗ chặn hoặc None).

    Thay cả câu chứ không cắt riêng chữ: bỏ mỗi chữ "lách" khỏi "bên em vẫn có
    cách lách để anh chị vay được" ra một câu vẫn hứa hẹn đúng thứ không được
    hứa. Vấn đề nằm ở Ý, không nằm ở chữ.
    """
    m = _TU_CAM_RE.search(text or "")
    if not m:
        return text, None
    return CAU_THAY_TU_CAM, f"chữ cấm {m.group(1)!r}"


# --- Lưới 2: gán thu nhập cho khách khi khách chưa nói --------------------

# Câu KHẲNG ĐỊNH thu nhập của khách. Bắt theo chủ thể "anh/chị/mình" đứng cạnh
# từ chỉ thu nhập, kèm một con số.
#
# CỐ Ý KHÔNG bắt câu nói về ĐIỀU KIỆN sản phẩm ("điều kiện là có lương từ 5
# triệu trở lên") - câu đó không gán cho ai, và nó là thứ tài liệu cho phép nói.
# Phân biệt bằng chính chủ thể: có "anh/chị/mình" thì mới là gán.
_CHU_THE = r"(?:anh|chị|anh/chị|anh chị|mình)"
_THU_NHAP = r"(?:lương|thu nhập)"
_SO = r"\d+(?:[.,]\d+)?"
_GAN_RE = re.compile(
    # "anh/chị có lương ... 3.4"  |  "lương của anh/chị là 3.4"
    rf"(?:{_CHU_THE}\s+(?:có\s+)?{_THU_NHAP}[^.?!]{{0,30}}?{_SO}"
    rf"|{_THU_NHAP}\s+(?:của\s+)?{_CHU_THE}[^.?!]{{0,30}}?{_SO}"
    # "Với thu nhập 5 triệu ..., hồ sơ của anh đã đáp ứng": chủ thể đứng SAU.
    # Bộ thử 08-10-2026: khách nói lương 20 triệu, Qwen đáp "với thu nhập 5
    # triệu" (con số của điều kiện sản phẩm) rồi kết luận thay khách. Không bắt
    # "với thu nhập TỪ 5 triệu" - đó là câu nêu điều kiện, không gán cho ai.
    rf"|với\s+(?:mức\s+)?{_THU_NHAP}\s+(?!từ\b)(?:khoảng\s+|là\s+)?{_SO})",
    re.IGNORECASE)

CAU_HOI_THU_NHAP = ("Dạ anh chị cho em xin mức thu nhập hàng tháng "
                    "để em tư vấn hạn mức chính xác ạ?")


CAU_GHI_NHAN_THU_NHAP = "Dạ em ghi nhận mức thu nhập anh chị vừa cho biết ạ."
CAU_GHI_NHAN_THU_NHAP_GIA_DINH = (
    "Dạ em ghi nhận thông tin thu nhập gia đình anh chị vừa cho biết ạ.")


def chan_gan_thu_nhap(text: str, khach_da_noi: str = "",
                      khach_da_noi_thu_nhap: bool = False, facts=None) -> tuple[str, str | None]:
    """Chặn AI KHẲNG ĐỊNH thu nhập của khách khi khách chưa từng nêu con số đó.

    `khach_da_noi` là toàn bộ lời khách trong cuộc (nối lại), KHÔNG phải ngữ cảnh
    tài liệu. Đây là điểm mấu chốt: con số 3.4 CÓ trong tài liệu nên mọi lưới đối
    chiếu tài liệu đều cho qua. Thứ duy nhất bảo chứng được cho một câu về thu
    nhập của khách là chính lời khách.

    Ba trường hợp KHÔNG chặn, đều có test canh:
      - khách đã tự nêu đúng con số đó  (AI nhắc lại là đúng)
      - câu nói về ĐIỀU KIỆN sản phẩm, không gán cho ai
      - câu HỎI thu nhập (hỏi thì được, khẳng định thay khách mới là lỗi)

    Khi đã có dữ kiện typed nhưng mô hình nhắc sai số, thay bằng lời ghi nhận
    trung tính và không lặp lại số sai. Chỉ hỏi lại khi chưa có thu nhập đúng
    chủ thể; thu nhập hộ gia đình dùng một lời ghi nhận riêng.
    """
    t = text or ""
    m = _GAN_RE.search(t)
    if not m:
        return text, None
    # Chỉ CÂU chứa lời gán mới quyết định: câu đó là câu hỏi thì cho qua. Trước
    # đây cả mảnh có một dấu "?" ở bất kỳ đâu là cho qua, nên "Với thu nhập 10
    # triệu, hồ sơ đáp ứng ạ. Chị có cần em tính không?" lọt (khách nói 40 triệu).
    cuoi_cau = re.search(r"[.?!]", t[m.end():])
    if cuoi_cau and cuoi_cau.group() == "?":
        return text, None
    from backend.pipeline.du_kien_khoan_vay import fold, resolve
    facts = facts if facts is not None else resolve(text=khach_da_noi)
    household_echo = bool(re.search(
        r"\b(?:tong thu nhap|thu nhap.{0,25}(?:vo chong|gia dinh|ca nha))\b", fold(t)))
    reply_income = resolve(text=t).income
    da_noi = _gia_tri_khach_noi(khach_da_noi, facts, household_echo)
    if reply_income.value is not None and float(reply_income.value) / 1e6 in da_noi:
        return text, None
    # Chọn câu thay theo provenance đã chiếu từ lời khách. Boolean cũ chỉ là
    # dấu hiệu tầng gọi từng phát hiện chữ "thu nhập", không chứng minh được
    # con số thuộc về ai nên tuyệt đối không dùng làm quyền cho qua / ghi nhận.
    if facts.income.owner == "self" and facts.income.status == "known":
        thay = CAU_GHI_NHAN_THU_NHAP
    elif facts.income.owner == "household" and facts.income.status == "known":
        thay = CAU_GHI_NHAN_THU_NHAP_GIA_DINH
    else:
        thay = CAU_HOI_THU_NHAP
    return thay, f"gán thu nhập cho khách ({m.group(0)[:40]!r})"


_CHU_THE_THU_NHAP_CUC_BO = re.compile(
    r"(?P<spouse>\b(?:vo|chong) (?:anh|chi|toi|em)\b)|"
    r"(?P<self>\b(?:luong|thu nhap)(?: cua)? (?:anh|chi|toi|em)\b|"
    r"\b(?:anh|chi|toi|em)(?: co)? (?:luong|thu nhap)\b)")


def _cap_thu_nhap_rieng(khach_da_noi: str, facts) -> list[float]:
    """Return exactly a qualified caller/spouse pair, otherwise no pair.

    Role and ownership come from the same typed projection helpers as the
    reducer. The local subject is still required because an implicit salary is
    valid personal input but cannot participate in an inferred household sum.
    """
    from backend.pipeline.du_kien_khoan_vay import (
        _income_owner, _menh_de_chua_so, _role, _suy_don_vi, fold, quantities,
    )

    normal = fold(khach_da_noi)
    if re.search(r"\b(?:hay|hoac)\b", normal):
        return []
    qualified: list[tuple[str, float]] = []
    for q in quantities(khach_da_noi):
        if _role(khach_da_noi, q, False) != "income":
            continue
        owner = _income_owner(khach_da_noi, q)
        if owner not in ("self", "") or q.value is None:
            continue
        clause, local_start = _menh_de_chua_so(khach_da_noi, q)
        before = clause[:local_start]
        before = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", before)
        subjects = list(_CHU_THE_THU_NHAP_CUC_BO.finditer(before))
        if not subjects:
            continue
        subject = subjects[-1].lastgroup
        # The reducer deliberately ignores spouse income (`owner == ""`). A
        # self marker must agree with its typed owner; this rejects bank quotes.
        if (subject == "self") != (owner == "self"):
            continue
        if q.kind == "money":
            value = float(q.value) / 1e6
        elif q.kind == "bare" and _suy_don_vi():
            value = float(q.value)
        else:
            continue
        qualified.append((subject, value))
    if len(qualified) != 2 or {subject for subject, _ in qualified} != {"self", "spouse"}:
        return []
    own = next(value for subject, value in qualified if subject == "self")
    if (facts.income.owner != "self" or facts.income.value is None
            or abs(own - float(facts.income.value) / 1e6) >= 1e-6):
        return []
    return [value for _, value in qualified]


def _gia_tri_khach_noi(khach_da_noi: str, facts=None, household: bool = False) -> set[float]:
    """Chỉ thu nhập có đúng chủ thể; tiền vay/giá nhà/điều kiện không bảo chứng."""
    from backend.pipeline.du_kien_khoan_vay import resolve
    facts = facts if facts is not None else resolve(text=khach_da_noi)
    income = facts.income
    if not household and income.owner == "self" and income.value is not None:
        return {float(income.value) / 1e6}
    if household and income.owner == "household" and income.value is not None:
        return {float(income.value) / 1e6}
    if household:
        pair = _cap_thu_nhap_rieng(khach_da_noi, facts)
        if pair:
            return {sum(pair)}
    return set()


def _la_so_da_noi(so: str, da_noi: set[float]) -> bool:
    try:
        v = float(so.replace(",", "."))
    except ValueError:
        return False
    return any(abs(v - x) < 1e-6 for x in da_noi)


# --- Lưới 3: mô hình TỰ TÍNH số tiền phải trả ------------------------------

# Khoản trả hàng tháng / tiền lãi là PHÉP TÍNH, và chỉ `tra_loi_khoan_vay` (luật
# `tinh_tra_gop`) được làm phép tính đó - nó lấy lãi suất từ tài liệu và số
# tiền, kỳ hạn từ chính lời khách. Mô hình mà tự tính thì bịa: bộ thử 304 lượt
# (08-10-2026) khách mới nói "mười hai tháng", CHƯA nói số tiền, Qwen đáp "khoản
# trả góp khoảng 3,4 triệu mỗi tháng"; khách nói "một tỷ đến hai tỷ" thì ra
# "hàng tháng trả khoảng 9,5-16,5 triệu". Mấy con số đó tình cờ CÓ ở chỗ khác
# trong tài liệu nên ba lưới số đều cho qua - phải bắt theo Ý chứ không theo số.
_TIEN = r"\d+(?:[.,]\d+)?(?:\s*(?:-|đến|tới)\s*\d+(?:[.,]\d+)?)?\s*(?:triệu|tr\b|nghìn|ngàn|tỷ|tỉ|đồng)"
_KY = r"(?:mỗi tháng|hàng tháng|hằng tháng|một tháng|/\s*tháng|tháng đầu|mỗi kỳ|mỗi triệu vay)"
_TRA = r"(?:trả|góp|đóng|thanh toán|gốc)"
_TU_TINH_RE = re.compile(
    rf"(?:{_TRA}[^.?!]{{0,40}}?{_TIEN}[^.?!]{{0,25}}?{_KY}"
    rf"|{_TRA}[^.?!]{{0,25}}?{_KY}[^.?!]{{0,30}}?{_TIEN}"
    rf"|{_KY}[^.?!]{{0,25}}?{_TRA}[^.?!]{{0,30}}?{_TIEN}"
    rf"|(?:khoản trả góp|tiền trả góp|số tiền trả góp)[^.?!]{{0,40}}?{_TIEN}"
    rf"|(?:tiền lãi|số lãi|tổng lãi|lãi phải trả)[^.?!]{{0,30}}?{_TIEN})",
    re.IGNORECASE)

CAU_THAY_TU_TINH = ("Dạ số tiền trả hàng tháng phải tính theo số tiền và thời hạn "
                    "vay cụ thể, anh chị cho em xin hai thông tin đó để em tính ạ.")


def chan_tu_tinh_tien(text: str) -> tuple[str, str | None]:
    """Chặn câu mô hình TỰ NÊU số tiền phải trả theo kỳ hoặc tiền lãi.

    Không chặn câu HỎI, không chặn phần trăm ("trả tối thiểu 5% dư nợ mỗi
    tháng" là dữ kiện của tài liệu), không chặn mức thu nhập/điều kiện ("thu
    nhập từ 5 triệu mỗi tháng" không có động từ trả/góp/đóng).
    """
    t = text or ""
    from backend.pipeline.du_kien_khoan_vay import quantities
    # Model đôi khi viết tiền bằng chữ. Dùng cùng bộ đọc số của khách để xét
    # ý tính tiền; không sửa câu trả lời bình thường chỉ vì nó chứa một số tiền.
    for quantity in reversed(quantities(t)):
        if (quantity.kind == "money" and quantity.value is not None
                and not quantity.raw[:1].isdigit()):
            t = t[:quantity.start] + f"{quantity.value} đồng" + t[quantity.end:]
    # Một câu hỏi nối đuôi không miễn trừ lời khẳng định ở câu trước. Giữ dấu
    # chấm/phẩy nằm giữa các chữ số để 3.4 triệu không bị chẻ mất.
    for sentence in re.split(r"(?<=[.!?])\s+", t):
        m = _TU_TINH_RE.search(sentence)
        if not m:
            continue
        # Chỉ miễn câu hỏi về khoản khách ĐANG/MUỐN trả, không miễn câu hỏi
        # xác nhận số tiền do mô hình vừa tự tính ("khoản trả là X đúng không?").
        if sentence.rstrip().endswith("?") and re.search(
                r"\b(?:anh|chị|anh chị|anh/chị)\s+(?:đang|muốn|dự định)\s+(?:trả|đóng)\b",
                sentence, re.I):
            continue
        return CAU_THAY_TU_TINH, f"tự tính tiền ({m.group(0)[:50]!r})"
    return text, None


def chan_gan_nhu_cau(text: str, facts) -> tuple[str, str | None]:
    """Lời model không được biến con số đang mơ hồ thành nhu cầu đã chốt."""
    if facts is None:
        return text, None
    from backend.pipeline.du_kien_khoan_vay import fold, quantities

    normal = fold(text or "")
    for quantity in quantities(text or ""):
        if quantity.kind != "money" or quantity.value is None:
            continue
        prefix = normal[max(0, quantity.start - 100):quantity.start]
        person = r"(?:anh|chi|anh chi|anh/chi)"
        assignment = (
            rf"\b{person}\b.{{0,55}}\b(?:muon|can|du dinh|dang can nhac)\b.{{0,30}}\bvay\b"
            r"(?:\s+(?:khoang|tam|chung|so tien|la))*\s*$"
            rf"|\b(?:khoan vay|nhu cau(?: vay)?|so tien vay)\b.{{0,25}}\b{person}\b"
            r"(?:\s+(?:can|muon|la|khoang|tam|chung))*\s*$"
            rf"|\b{person}\b\s+dang vay(?:\s+(?:so tien|la|khoang|tam|chung))*\s*$")
        if not re.search(assignment, prefix):
            continue
        # Một ví dụ giả định không phải lời gán nhu cầu cho khách; phép tính
        # trong ví dụ vẫn phải qua chan_tu_tinh_tien ở tầng trước.
        if re.search(r"\b(?:neu|gia su)\b", prefix):
            continue
        if facts.amount.value is None or facts.amount.value != quantity.value:
            return ("Dạ anh chị chốt giúp em số tiền cụ thể muốn vay, kèm đơn vị triệu hoặc tỷ đồng ạ?",
                    "gán số tiền vay chưa được khách xác nhận")
    return text, None


# --- Lưới 4: mô hình TỰ KẾT LUẬN khách không được vay ----------------------

# Duyệt hay không là việc của thẩm định, không phải của tư vấn viên - càng không
# phải của mô hình. Bộ thử 304 lượt (08-10-2026): khách nói "anh chưa có nhà anh
# đang thuê", Qwen đáp "hồ sơ vay mua nhà sẽ không được xét duyệt" (tài liệu cho
# dùng chính căn nhà mua làm tài sản đảm bảo); khách nói "đang còn nợ bên kia",
# Qwen đáp "sẽ ảnh hưởng đến hồ sơ vay mới" (tài liệu không nói vậy). Một câu như
# thế làm khách bỏ cuộc dù có thể đủ điều kiện.
#
# Chỉ áp cho câu MÔ HÌNH SINH. Câu của luật/kho ("hiện bên em chưa có sản phẩm
# bảo hiểm") không đi qua lưới này.
_TU_CHOI_RE = re.compile(
    r"(?:không|chưa|khó)\s+(?:được\s+|thể\s+)?(?:xét\s+duyệt|duyệt|phê\s+duyệt)"
    r"|(?:không|chưa)\s+đủ\s+điều\s+kiện"
    r"|không\s+(?:thể\s+)?vay\s+được|không\s+được\s+vay"
    r"|sẽ\s+(?:bị\s+từ\s+chối|ảnh\s+hưởng\s+(?:đến|tới)\s+hồ\s+sơ)"
    r"|(?:chưa|không)\s+(?:có\s+gói\s+)?hỗ\s+trợ",
    re.IGNORECASE)

CAU_THAY_TU_CHOI = ("Dạ trường hợp này còn tuỳ hồ sơ cụ thể, em xin ghi nhận để "
                    "chuyên viên kiểm tra kỹ giúp anh chị ạ.")


def chan_ket_luan_tu_choi(text: str) -> tuple[str, str | None]:
    """Chặn câu mô hình tự phán khách không vay được / không được duyệt.

    Không chặn câu HỎI và câu nói "em chưa có thông tin" (đó là nói thật, không
    phải phán quyết).
    """
    t = text or ""
    if "?" in t:
        return text, None
    m = _TU_CHOI_RE.search(t)
    if not m:
        return text, None
    return CAU_THAY_TU_CHOI, f"tự kết luận từ chối ({m.group(0)[:40]!r})"


# Mô hình trộn hai cụm đứng cạnh nhau trong tài liệu ("hợp đồng lao động hoặc
# giấy phép kinh doanh") thành một cụm không có thật. Đo 09-10-2026: khách chạy
# xe ôm công nghệ hỏi vay, câu sinh ra đòi "hợp đồng kinh doanh".
_THUAT_NGU_LAI = (("hợp đồng kinh doanh", "giấy phép kinh doanh"),)


def sua_thuat_ngu_lai(text: str, tai_lieu: str) -> tuple[str, str | None]:
    """Đổi cụm lai về đúng cụm của tài liệu.

    Chỉ đổi khi tài liệu KHÔNG có cụm lai và CÓ cụm đúng: tài liệu nào thật sự
    nói "hợp đồng kinh doanh" thì câu được để nguyên.
    """
    tl = unicodedata.normalize("NFC", tai_lieu or "").casefold()
    ra, sua = unicodedata.normalize("NFC", text or ""), []
    for lai, dung in _THUAT_NGU_LAI:
        if lai in tl or dung not in tl:
            continue
        moi = re.sub(re.escape(lai),
                     lambda m: dung.capitalize() if m.group(0)[:1].isupper() else dung,
                     ra, flags=re.IGNORECASE)
        if moi != ra:
            ra = moi
            sua.append(f"{lai!r} -> {dung!r}")
    return (ra, ", ".join(sua)) if sua else (text, None)
