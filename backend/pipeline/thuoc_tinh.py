"""Trích cặp (thuộc tính, giá trị) từ câu, để đối chiếu với tài liệu.

Bảng thuộc tính ở đây là MẶC ĐỊNH gieo vào DB lần đầu; đường chạy thật đọc bảng
`thuoc_tinh_kiem`. Giữ bản gốc trong code để mất DB vẫn còn.
"""
import re

THUOC_TINH_MAC_DINH: dict[str, dict] = {
    "lãi suất":  {"khoa": ("lãi suất", "lãi xuất"), "dvi": ("%",)},
    "hạn mức":   {"khoa": ("hạn mức", "vay tối đa", "lên đến", "tối đa"), "dvi": ("triệu", "tỷ")},
    "thời hạn":  {"khoa": ("thời hạn", "kỳ hạn", "vay trong"), "dvi": ("tháng", "năm")},
    "giải ngân": {"khoa": ("giải ngân",), "dvi": ("giờ", "ngày")},
    "tuổi":      {"khoa": ("tuổi",), "dvi": ("tuổi",)},
    "thu nhập":  {"khoa": ("thu nhập", "lương từ"), "dvi": ("triệu",)},
    "sao kê":    {"khoa": ("sao kê",), "dvi": ("tháng",)},
    "miễn lãi":  {"khoa": ("miễn lãi",), "dvi": ("ngày",)},
    # --- PHÍ. Thêm 09-09-2026 sau khi nghe AI bịa ba lần trên máy thật:
    # "phí rút tiền mặt tại ATM là 2.000 đồng", "phí thường niên là 2% của hạn
    # mức thẻ", "phí phạt trả trước hạn là 1%". Không thuộc tính nào nhận được
    # những con số đó nên lưới im hoàn toàn.
    #
    # Tách BA loại phí thay vì một "phí" chung: tài liệu ghi ba mức khác nhau
    # (thường niên 200/400/800 nghìn, trả trước hạn miễn phí, rút tiền không
    # có), gộp một chỗ là mọi mức đều "có trong tài liệu" và lưới lại mù.
    "phí thường niên": {"khoa": ("phí thường niên", "phí duy trì"),
                        "dvi": ("%", "đồng", "đ", "nghìn", "triệu")},
    "phí trả trước":   {"khoa": ("phí phạt", "trả trước hạn", "trả nợ trước hạn"),
                        "dvi": ("%", "đồng", "đ", "nghìn", "triệu")},
    "phí rút tiền":    {"khoa": ("phí rút", "rút tiền mặt"),
                        "dvi": ("%", "đồng", "đ", "nghìn", "triệu")},
    "hoàn tiền":       {"khoa": ("hoàn tiền", "cashback"), "dvi": ("%",)},
}

_SO = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*(%|(?:triệu|tỷ|tháng|năm|giờ|ngày|tuổi|đồng|nghìn|đ)\b)",
    re.I,
)
# Bắt dải số dạng "N - M đơn_vị" hoặc "N đến M đơn_vị": số đầu không có đơn vị ngay sau.
_DAI = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*(?:-|–|đến)\s*(\d+(?:[.,]\d+)*)\s*"
    r"(%|(?:triệu|tỷ|tháng|năm|giờ|ngày|tuổi|đồng|nghìn|đ)\b)",
    re.I,
)
_RADIUS = 85  # ký tự tối đa giữa từ khoá và số

# Phần trăm đứng cạnh những cụm này KHÔNG phải lãi suất. Cả hai đều bắt được
# trên câu thật (09-09-2026): "vay tối đa 80% giá trị bất động sản" là tỷ lệ cho
# vay, "hoàn tiền 3% cho mọi giao dịch" là ưu đãi - báo cả hai thành lãi suất
# lệch là chặn oan hai lượt đúng.
#
# CỐ Ý không bắt chữ "giảm" trơn: tài liệu vay tín chấp có dòng "Giảm 0.5% lãi
# suất cho khách hàng có lương qua ngân hàng", ở đó 0.5% ĐÚNG là nói về lãi suất.
#
# "hoàn tiền"/"cashback" ĐÃ RỜI danh sách này 09-09-2026: nay chúng có thuộc
# tính riêng nên đối chiếu được với tài liệu thật, không phải né bằng cách vứt
# con số đi. Vứt là mất luôn khả năng bắt "hoàn tiền 10%" khi tài liệu ghi 1-3%.
_PT_SAU = re.compile(r"^\s*(?:giá\s*trị|trên\s*tổng|tổng\s*giá)")
_PT_TRUOC = re.compile(r"(?:chiết\s*khấu|giảm\s*giá)\s*$")


# Đơn vị TIỀN. Trong số tiền tiếng Việt, dấu chấm là PHÂN CÁCH NGHÌN chứ không
# phải dấu thập phân - "200.000 đồng" là hai trăm nghìn.
_DVI_TIEN = ("đồng", "đ", "nghìn", "nghin")


def chuan_so(s: str, dvi: str = "") -> str:
    """Chỉ bỏ số 0 thừa SAU dấu thập phân. `"500".rstrip("0")` cho "5" - đã mắc.

    `dvi` là ĐƠN VỊ đi kèm, vì dấu chấm đọc khác nhau tuỳ đơn vị:
        "7.9"   + "%"    -> 7.9      (thập phân)
        "200.000" + "đồng" -> 200000 (phân cách nghìn)

    Không có tham số này thì thêm đơn vị "đồng" vào lưới là hỏng ngay:
    `chuan_so("1.500.000")` cho `"1.500"` - sai hơn một nghìn lần.
    """
    if dvi.lower() in _DVI_TIEN:
        return re.sub(r"[.,]", "", s) or "0"
    s = s.replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _cum_so(t: str) -> list[tuple[int, list[str], str]]:
    """[(vị_trí, [số...], đơn_vị)] - một DẢI là MỘT cụm mang hai giá trị.

    Giữ dải nguyên cụm chứ không tách đôi vì hai đầu dải luôn nói về CÙNG một
    thuộc tính. Tách ra rồi xét riêng từng đầu thì đầu này vào đúng chỗ còn đầu
    kia trôi sang thuộc tính khác - đo được trên câu thật "Hạn mức thẻ Gold là
    từ 30 đến 200 triệu đồng, phù hợp với thu nhập của anh": 30 vào hạn mức còn
    200 sang thu nhập, rồi báo lệch một câu vốn đúng.
    """
    cum: list[tuple[int, list[str], str]] = []
    da_co: set[int] = set()

    # _DAI chạy trước _SO để cụm dải chiếm chỗ, không bị đọc thành hai số lẻ.
    for m in _DAI.finditer(t):
        p1, p2 = m.start(1), m.start(2)
        if p1 in da_co or p2 in da_co:
            continue
        da_co |= {p1, p2}
        dvi = m.group(3).lower()
        cum.append((p1, [chuan_so(m.group(1), dvi), chuan_so(m.group(2), dvi)], dvi))

    for m in _SO.finditer(t):
        p = m.start(1)
        if p in da_co:
            continue
        da_co.add(p)
        dvi = m.group(2).lower()
        cum.append((p, [chuan_so(m.group(1), dvi)], dvi))

    # Phần trăm nằm trong ngữ cảnh "không phải lãi suất" thì bỏ hẳn, đừng để nó
    # đi tìm thuộc tính - "%" chỉ có lãi suất nhận nên nó chắc chắn vào nhầm.
    giu = []
    for pos, sos, dvi in cum:
        if dvi == "%":
            het = t.find("%", pos)
            het = het + 1 if het >= 0 else pos
            if _PT_SAU.search(t[het:het + 24]) or _PT_TRUOC.search(t[max(0, pos - 24):pos]):
                continue
        giu.append((pos, sos, dvi))
    giu.sort()
    return giu


def _lan_tu_khoa(t: str, bang: dict) -> dict[str, list[tuple[int, int]]]:
    """{thuộc tính: [(đầu, cuối)]} - các LẦN XUẤT HIỆN của từ khoá, đã gộp chồng.

    Gộp các lần chồng nhau của CÙNG thuộc tính làm một: "vay tối đa" và "tối đa"
    đều là từ khoá của hạn mức và chồng lên nhau trong cùng một cụm chữ. Không
    gộp thì luật "mỗi lần xuất hiện nhận một cụm số" đếm thành hai lần và vẫn vơ
    được hai con số.
    """
    ra: dict[str, list[tuple[int, int]]] = {}
    for ten, d in bang.items():
        cac: list[tuple[int, int]] = []
        for k in d["khoa"]:
            cac += [(m.start(), m.end()) for m in re.finditer(re.escape(k), t)]
        cac.sort()
        gop: list[tuple[int, int]] = []
        for dau, cuoi in cac:
            if gop and dau <= gop[-1][1]:
                gop[-1] = (gop[-1][0], max(gop[-1][1], cuoi))
            else:
                gop.append((dau, cuoi))
        if gop:
            ra[ten] = gop
    return ra


def _cum_gan_thuoc_tinh(cau: str, bang: dict) -> list[tuple[str, list[str], str]]:
    """[(thuộc tính, [số...], đơn vị)] - ghép cụm số với thuộc tính của nó.

    Mỗi LẦN XUẤT HIỆN của từ khoá chỉ nhận MỘT cụm số, cụm gần nó nhất. Ghép
    tham lam từ cặp gần nhau nhất trở đi.

    Vì sao cần luật đó: chọn "từ khoá gần nhất" cho từng số một cách độc lập thì
    một từ khoá đơn độc trong câu sẽ vơ hết mọi con số quanh nó. Câu thật, hoàn
    toàn đúng tài liệu, vẫn bị chặn: "Với thu nhập ổn định từ 5 triệu đồng/tháng
    trở lên, anh/chị có thể xin vay đến 500 triệu đồng." Ở đây "thu nhập" là từ
    khoá duy nhất, nên nó nhận cả 500 triệu - vốn là hạn mức - và lưới báo "thu
    nhập 500 triệu, tài liệu ghi 5 triệu".

    Cụm không tìm được thuộc tính thì BỎ QUA chứ không đoán. Chỗ này cố ý đánh
    đổi: mất khả năng bắt lỗi ở câu kiểu "hạn mức 500 triệu, lên 700 triệu nữa"
    (chỉ một từ khoá cho hai số), đổi lấy việc không chặn oan câu đúng. Với lưới
    sắp được bật chặn thật thì chặn oan đắt hơn nhiều.
    """
    t = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", (cau or "").lower())
    cum = _cum_so(t)
    lan = _lan_tu_khoa(t, bang)

    ung: list[tuple[int, int, str, int]] = []   # (khoảng cách, chỉ số cụm, tên, chỉ số lần)
    for i, (pos, _sos, dvi) in enumerate(cum):
        for ten, cac in lan.items():
            if dvi not in bang[ten]["dvi"]:
                continue
            for j, (dau, cuoi) in enumerate(cac):
                kc = 0 if dau <= pos <= cuoi else min(abs(dau - pos), abs(cuoi - pos))
                if kc <= _RADIUS:
                    ung.append((kc, i, ten, j))
    # sắp xếp toàn phần để kết quả KHÔNG phụ thuộc thứ tự khoá của dict
    ung.sort()

    gan: dict[int, str] = {}
    da_dung: set[tuple[str, int]] = set()
    for kc, i, ten, j in ung:
        if i in gan or (ten, j) in da_dung:
            continue
        gan[i] = ten
        da_dung.add((ten, j))

    return [(gan[i], sos, dvi) for i, (_p, sos, dvi) in enumerate(cum) if i in gan]


def cap_trong(cau: str, bang: dict) -> list[tuple[str, str, str]]:
    """[(thuộc tính, số, đơn vị)] tìm được trong câu."""
    return [(ten, so, dvi)
            for ten, sos, dvi in _cum_gan_thuoc_tinh(cau, bang)
            for so in sos]


def gia_tri_tai_lieu(tai_lieu: str, bang: dict) -> dict[str, set[tuple[str, str]]]:
    """{thuộc tính: {(số, đơn vị)}} đọc được từ tài liệu.

    Đọc TỪNG DÒNG chứ không cả khối: từ khoá của thuộc tính này không được vơ
    lấy con số của dòng khác.
    """
    kho: dict[str, set[tuple[str, str]]] = {}
    for dong in (tai_lieu or "").splitlines():
        for ten, so, dvi in cap_trong(dong, bang):
            kho.setdefault(ten, set()).add((so, dvi))
    return kho


def khoang_tai_lieu(tai_lieu: str, bang: dict) -> dict[str, list[tuple[float, float, str]]]:
    """{thuộc tính: [(thấp, cao, đơn vị)]} - các DẢI tài liệu ghi.

    Tách khỏi `gia_tri_tai_lieu` thay vì đổi kiểu trả về của nó: hàm kia có sẵn
    người dùng và có sẵn test, đổi hợp đồng của nó là việc riêng không thuộc
    phạm vi bản sửa này.

    Vì sao cần: tài liệu ghi "Thời hạn: 12 - 60 tháng" nghĩa là MỌI giá trị từ
    12 đến 60 đều đúng, nhưng `gia_tri_tai_lieu` chỉ giữ được hai đầu {12, 60}.
    Nên câu "vay 300 triệu trong 36 tháng" - đúng tài liệu - bị báo lệch. Đây là
    nguồn chặn oan nhiều nhất trong 60 câu đo 09-09-2026, dính ở cả bốn cấu hình
    nạp ngữ cảnh đã thử.
    """
    ra: dict[str, list[tuple[float, float, str]]] = {}
    for dong in (tai_lieu or "").splitlines():
        for ten, sos, dvi in _cum_gan_thuoc_tinh(dong, bang):
            if len(sos) != 2:
                continue
            try:
                a, b = float(sos[0]), float(sos[1])
            except ValueError:      # số quá dài hoặc dạng lạ -> bỏ, đừng nổ
                continue
            ra.setdefault(ten, []).append((min(a, b), max(a, b), dvi))
    return ra


def _trong_khoang(so: str, dvi: str, cac_khoang: list[tuple[float, float, str]]) -> bool:
    """Giá trị có nằm trong một dải nào của tài liệu không (kể cả sau quy đổi)."""
    for c_so, c_dvi in _quy_doi(so, dvi):
        try:
            v = float(c_so)
        except ValueError:
            continue
        if any(lo <= v <= hi for lo, hi, d in cac_khoang if d == c_dvi):
            return True
    return False


def _quy_doi(so: str, dvi: str) -> list[tuple[str, str]]:
    """Các cách viết tương đương của cùng một lượng."""
    ra = [(so, dvi)]
    try:
        v = float(so)
    except ValueError:
        return ra
    if dvi == "tỷ":
        ra.append((chuan_so(str(v * 1000)), "triệu"))
    elif dvi == "triệu":
        ra.append((chuan_so(str(v / 1000)), "tỷ"))
        ra.append((chuan_so(str(int(v * 1_000_000)), "đồng"), "đồng"))
    elif dvi in ("nghìn", "nghin"):
        # "200 nghìn" và "200.000 đồng" là cùng một số tiền - tài liệu viết cách
        # này, AI nói cách kia thì không được coi là lệch.
        ra.append((chuan_so(str(int(v * 1000)), "đồng"), "đồng"))
    elif dvi in ("đồng", "đ"):
        ra.append((so, "đ"))
        ra.append((so, "đồng"))
        if v >= 1000 and v % 1000 == 0:
            ra.append((chuan_so(str(int(v / 1000)), "nghìn"), "nghìn"))
    return ra


def chan_thuoc_tinh_sai(text: str, tai_lieu: str, bang: dict,
                        khach_noi: str = "") -> tuple[str, str | None]:
    """Con số gán cho một thuộc tính có đúng như tài liệu không?

    Trả `(văn bản nguyên vẹn, mô tả chỗ lệch hoặc None)` - CÙNG DẠNG với
    `chan_so_sai` để chỗ gọi xử lý thống nhất. Hàm này KHÔNG tự thay câu.

    Ba trường hợp im lặng, đều có chủ ý:
      - thuộc tính không có trong tài liệu -> việc của lưới NLI, không phải của đây
      - con số do chính KHÁCH nêu -> AI nhắc lại là đúng
      - không trích được cặp nào -> không có gì để phán
    """
    kho = gia_tri_tai_lieu(tai_lieu, bang)
    if not kho:
        return text, None
    khoang = khoang_tai_lieu(tai_lieu, bang)
    # `cap_trong` trả BỘ BA (tên, số, đơn vị). Đọc thành bộ đôi là nổ giữa
    # cuộc gọi - đã lọt qua test một lần vì câu thử không trích được cặp nào.
    so_khach = {so for _, so, _ in cap_trong(khach_noi, bang)} | set(
        re.findall(r"\d+(?:[.,]\d+)?", (khach_noi or "")))
    lech = []
    for ten, so, dvi in cap_trong(text, bang):
        if so in so_khach:
            continue
        if ten not in kho:
            # Tài liệu KHÔNG nói gì về thuộc tính này -> mọi giá trị AI gán cho
            # nó đều là bịa. Trước 09-09 chỗ này `continue`, hoãn sang lưới NLI.
            #
            # Vì sao đổi: đo trên 250 lượt lịch sử, đối chiếu với TRỌN tài liệu
            # sản phẩm + FAQ, bịt lỗ này thêm ĐÚNG MỘT lượt (14 -> 15) và lượt
            # đó là bịa thật - "phí rút tiền mặt tại ATM là 2.000 đồng/giao
            # dịch", trong khi không tài liệu nào có phí rút tiền. Không thêm
            # chặn oan nào.
            #
            # Sáng cùng ngày đo lần đầu cho +0 và tôi để nguyên; khác biệt là
            # lúc đó bảng chưa có thuộc tính phí nên con số ấy không được trích
            # ra để mà xét.
            lech.append(f"{ten} {so}{dvi} (tài liệu không nói gì về {ten})")
            continue
        if any(c in kho[ten] for c in _quy_doi(so, dvi)):
            continue
        # Tài liệu ghi một DẢI thì mọi giá trị trong dải đều đúng, không riêng
        # hai đầu - xem `khoang_tai_lieu`.
        if _trong_khoang(so, dvi, khoang.get(ten, [])):
            continue
        dung = ", ".join(f"{a}{b}" for a, b in sorted(kho[ten]))
        lech.append(f"{ten} {so}{dvi} (tài liệu: {dung})")
    return text, ("; ".join(lech) if lech else None)


# Ranh giới MỆNH ĐỀ để bỏ đúng phần sai mà giữ phần đúng. Cắt ở dấu phẩy và
# dấu kết câu - đủ thô để không cần phân tích cú pháp, đủ tinh để "giải ngân
# trong 24 giờ, phí rút tiền là 2.500 đồng" chỉ mất vế sau.
_RANH_MENH_DE = re.compile(r"(?<=[,.;!?])\s+")


def sua_theo_tai_lieu(text: str, tai_lieu: str, bang: dict,
                      khach_noi: str = "") -> tuple[str, str | None]:
    """Sửa câu cho khớp tài liệu. Trả `(câu đã sửa, mô tả)`; `mô tả=None` là câu sạch.

    Thang xử lý, rẻ trước đắt sau - và KHÔNG BAO GIỜ im lặng:

      1. THAY SỐ khi tài liệu có ĐÚNG MỘT giá trị cho thuộc tính đó. Giữ nguyên
         câu, nghe tự nhiên nhất.
      2. BỎ MỆNH ĐỀ chứa số sai khi không thay được. Giữ phần còn lại của câu.
      3. Trả "" khi bỏ xong không còn gì - chỗ gọi tự quyết (thường là
         `CAU_KIEM_TRA_LAI`).

    VÌ SAO KHÔNG thay cả câu bằng câu mẫu ngay: đó chính là cách đã đẻ ra lời
    than "trả lời 1 kiểu" - lưới thay hai câu khác nhau bằng cùng một câu.

    VÌ SAO chỉ thay số khi tài liệu có ĐÚNG MỘT giá trị: tài liệu vay tín chấp
    có cả "7.9%/năm" lẫn "Giảm 0.5% lãi suất", nên "lãi suất" có hai giá trị.
    Đoán bừa một trong hai rồi đọc cho khách nghe còn tệ hơn bỏ hẳn mệnh đề.

    Cùng ba trường hợp im lặng với `chan_thuoc_tinh_sai` (số của khách, giá trị
    khớp, nằm trong dải) - hàm này chỉ khác ở chỗ nó SỬA thay vì chỉ mô tả.
    """
    if not (text or "").strip():
        return text, None
    kho = gia_tri_tai_lieu(tai_lieu, bang)
    if not kho:
        return text, None
    khoang = khoang_tai_lieu(tai_lieu, bang)
    so_khach = {so for _, so, _ in cap_trong(khach_noi, bang)} | set(
        re.findall(r"\d+(?:[.,]\d+)*", (khach_noi or "")))

    sai: list[tuple[str, str, str]] = []
    for ten, so, dvi in cap_trong(text, bang):
        if so in so_khach:
            continue
        if ten in kho and any(c in kho[ten] for c in _quy_doi(so, dvi)):
            continue
        if _trong_khoang(so, dvi, khoang.get(ten, [])):
            continue
        sai.append((ten, so, dvi))
    if not sai:
        return text, None

    ra, ghi = text, []
    con_lai: list[tuple[str, str, str]] = []
    for ten, so, dvi in sai:
        dung = kho.get(ten, set())
        if len(dung) == 1:
            so_dung, dvi_dung = next(iter(dung))
            # Thay ĐÚNG chữ số như nó xuất hiện trong câu, kể cả dạng có dấu
            # phân cách nghìn ("2.500" chứ không phải "2500").
            moi, n = re.subn(
                r"\b" + re.escape(_dang_trong_cau(ra, so)) + r"\b(\s*" +
                re.escape(dvi) + r")?",
                f"{so_dung} {dvi_dung}", ra, count=1)
            if n:
                ra = moi
                ghi.append(f"{ten} {so}{dvi} -> {so_dung}{dvi_dung}")
                continue
        con_lai.append((ten, so, dvi))

    if con_lai:
        giu = []
        for md in _RANH_MENH_DE.split(ra):
            co_sai = any(_dang_trong_cau(md, so) and
                         re.search(r"\b" + re.escape(_dang_trong_cau(md, so)) + r"\b", md)
                         for _t, so, _d in con_lai)
            if co_sai:
                continue
            giu.append(md)
        ra = " ".join(x.strip() for x in giu if x.strip()).strip()
        ghi += [f"bỏ mệnh đề có {t} {s}{d}" for t, s, d in con_lai]

    return ra, "; ".join(ghi) if ghi else None


def _dang_trong_cau(cau: str, so: str) -> str:
    """Dạng chữ của `so` như nó nằm trong câu ("2500" -> "2.500" nếu câu ghi thế).

    `chuan_so` đã bỏ dấu phân cách nghìn, nên tìm-thay theo chuỗi đã chuẩn hoá
    sẽ trượt hết số tiền. Dò lại dạng gốc thay vì đoán.
    """
    if re.search(r"\b" + re.escape(so) + r"\b", cau):
        return so
    for m in re.finditer(r"\d+(?:[.,]\d+)*", cau):
        if re.sub(r"[.,]", "", m.group(0)) == so:
            return m.group(0)
    return so
