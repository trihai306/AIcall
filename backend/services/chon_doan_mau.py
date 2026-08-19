"""Tách bản ghi dài thành ứng viên đoạn mẫu, đo, và xếp hạng.

VÌ SAO CÓ. F5-TTS chép giọng từ một đoạn mẫu ngắn, nên đoạn mẫu quan trọng
ngang model. Chọn sai thì hỏng theo kiểu rất khó truy: 17-08-2026 bên A báo chữ
"ạ" nghe không tự nhiên, gốc là đoạn mẫu đang dùng là giọng KỂ CHUYỆN, không có
lấy một chữ "ạ" nào trong suốt 20 phút bản ghi - F5 phải tự bịa ngữ điệu cho
tiểu từ.

Chọn bằng tay mất ~2 giờ cho một giọng. Module này làm lại việc đó, nhưng KHÔNG
tự quyết: nó lọc bỏ thứ chắc chắn hỏng rồi xếp hạng phần còn lại để người dùng
nghe và chọn. Con số chỉ để loại bớt, tai người quyết.

Mọi ngưỡng dưới đây là số ĐO ĐƯỢC, không phải ước lượng - xem chú thích tại chỗ.

Thuần numpy, chạy được trên máy không có GPU lẫn librosa.
"""
import re
import unicodedata

import numpy as np

# Độ dài đoạn mẫu. Cùng một người, cùng một bản ghi, chỉ khác chỗ cắt:
#
#     8,88s -> tông lệch đầu ra 35,0%
#     6,42s -> 27,0%
#     3,18s -> 14,0%          <- đang chạy thật
#
# Dài hơn là F5 có nhiều "ngữ cảnh" hơn để trôi. Sàn 3,0s là của `pick_ref.py`
# từ trước: ngắn quá thì không đủ chất giọng để chép.
DAI_MIN, DAI_MAX = 3.0, 5.5

# Lời ghi trong .txt phải khớp thứ STT nghe được trên chính clip đó. Ứng viên
# `heu_a6_50` lệch 12,5% -> WER đầu ra 160%, tiếng vỡ hoàn toàn: F5 canh chữ
# theo ref_text rồi sinh tiếp trên nền ref_audio, chỗ lệch không biến mất mà rò
# sang phần sinh.
#
# NHƯNG NGƯỠNG PHẦN TRĂM LÀ THƯỚC ĐO SAI. Đo 24 ứng viên trên bản ghi thật
# (18-08): phân bố liên tục từ 0% tới 48%, khe rộng nhất nằm ở 34%->48% - vô
# dụng làm mốc cắt, nên chọn 5% hay 8% hay 10% đều tuỳ tiện như nhau.
#
# Thứ có quy luật là VỊ TRÍ lệch. 9/24 cái lệch 6-24% đều là mất hoặc thừa đúng
# một từ ở BIÊN, tức cắt hỏng - đó mới là đường dẫn tới WER 160%. Còn lệch ở
# GIỮA thì chỉ là STT nghe nhoè chính tả ("táp"/"tab", "nó"/"nói"), hoàn toàn
# dùng được mà ngưỡng 5% đang loại oan.
#
# Nên: lệch ở biên -> loại bất kể tỉ lệ; lệch ở giữa -> tha tới trần rộng hơn.
# (Hằng `LECH_LOI_TRAN = 0.05` cũ đã bỏ hẳn - giữ lại một ngưỡng không ai dùng
# là mời người sau tưởng nó còn hiệu lực.)
#
# Trần cho lệch nằm GIỮA câu. Rộng hơn hẳn vì nhoè chính tả vô hại, nhưng vẫn
# phải có trần: nhoè vài chữ thì tha, nghe ra nửa câu khác thì không.
LECH_GIUA_TRAN = 0.25

# Khe im giữa hai từ. Rộng hơn thế thì đó là chỗ ngắt/lấy hơi - cắt ở đó, đừng
# nuốt cả khoảng lặng vào clip.
KHE_TOI_DA = 0.6

# Cứ mấy từ lại thử bắt đầu một ứng viên mới, ngoài các chỗ có dấu chấm.
BUOC_DAU = 3

# CHỈ tiểu từ lễ phép thật. `text_chunker.TIEU_TU_CUOI_VE` nhận rộng hơn (có
# "à", "ấy") và với việc CỦA NÓ - chèn nhịp nghỉ - nhận rộng thì cùng lắm nghỉ
# thừa, vô hại. Ở đây nhận rộng là hỏng: chạy thật trên bản ghi 20 phút, cả 4
# đoạn lọt chung kết đều là nhận nhầm ("bạn ấy", "câu chuyện đó ấy", "rằng là
# à"), chúng chiếm hết suất kiểm lời nên đoạn tốt thật bị đẩy ra ngoài.
TIEU_TU = frozenset({"ạ", "nhé", "nha", "nhá", "nhỉ"})
LE_PHEP = frozenset({"dạ", "vâng", "em", "anh", "chị", "mình", "ạ"})
KET_CAU = ".?!"

# Quy về thang 0..1 bằng mốc CỐ ĐỊNH chứ không so tương đối giữa các ứng viên -
# để điểm của hai lần chạy khác nhau còn so được với nhau.
H1H2_TOT, H1H2_TE = 0.0, 12.0          # dB, thấp = ít thổi
NEN_TOT, NEN_TE = -70.0, -40.0         # dBFS; bản đang dùng đo -45,1

TRONG_SO = {
    # Đúng gốc lỗi bên A báo, mà trong 20 phút bản ghi chỉ có 3 chỗ kết bằng
    # tiểu từ - vừa quan trọng nhất vừa khan nhất.
    "tieu_tu": 5.0,
    # Tương quan +0,93 giữa độ thổi của đoạn mẫu và độ thổi đầu ra.
    "h1h2": 3.0,
    "nen": 2.0,
    "le_phep": 2.0,
    # Trừ, không phải cộng: clip cắt cụt một âm ở đầu/cuối thì vẫn nghe được
    # nhưng kém hơn hẳn clip cắt gọn. Đủ nặng để đẩy xuống dưới, không đủ để vứt.
    "cut_bien": -4.0,
}

_KHUNG_MS = 40.0
_F0_MIN, _F0_MAX = 70.0, 400.0


# --- lời ------------------------------------------------------------------

def gon(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(a: str, b: str) -> float:
    """Tỉ lệ ký tự sai giữa lời ghi và lời STT nghe được.

    Bỏ dấu câu và hoa/thường trước khi so: STT trả về không dấu câu, còn lời
    người ghi thì có - chênh đó không phải lệch thật.
    """
    a, b = gon(a), gon(b)
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sau = [i]
        for j, cb in enumerate(b, 1):
            sau.append(min(truoc[j] + 1, sau[j - 1] + 1, truoc[j - 1] + (ca != cb)))
        truoc = sau
    return truoc[-1] / len(a)


def _tu_cuoi(loi: str) -> str:
    t = gon(loi).split()
    return t[-1] if t else ""


def co_tieu_tu(loi: str) -> bool:
    """Chỉ chữ CUỐI mới tính - "ạ" giữa câu không cho ngữ điệu kết."""
    return _tu_cuoi(loi) in TIEU_TU


def le_phep(loi: str) -> bool:
    return bool(set(gon(loi).split()) & LE_PHEP)


# --- tách đơn vị ----------------------------------------------------------

def _phang(doan_stt: list[dict]) -> list[dict]:
    """Trải mọi từ của mọi đoạn STT thành một chuỗi.

    Câu hay thường vắt qua ranh giới đoạn của Whisper, nên phải trải phẳng chứ
    không xử lý từng đoạn riêng.

    Bỏ từ có thời lượng <= 0: PhoWhisper bịa ra "chữ ma" dài 0 giây ở cuối tệp.
    Chúng từng làm hỏng cả ba lượt đo hôm 17-08 (báo "17,5 chữ ngân/câu").
    """
    ra = []
    for d in doan_stt or []:
        for w in d.get("words") or []:
            try:
                a, b = float(w["start"]), float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            chu = (w.get("word") or "").strip()
            if chu and b > a:
                ra.append({"word": chu, "start": a, "end": b})
    ra.sort(key=lambda w: w["start"])
    return ra


def _het_cau(ws: list[dict], j: int) -> bool:
    """Sau từ thứ j có phải ranh giới câu không.

    Ba dấu hiệu: dấu kết câu do Whisper đặt, hết chuỗi, hoặc có chỗ lấy hơi.
    """
    chu = ws[j]["word"].rstrip()
    return (bool(chu) and chu[-1] in KET_CAU) \
        or j + 1 >= len(ws) \
        or ws[j + 1]["start"] - ws[j]["end"] > 0.25


def _dau_cau(ws: list[dict]) -> list[int]:
    """Các vị trí được phép bắt đầu một ứng viên.

    Mốc chữ của Whisper KHÔNG có khe - đo trên bản ghi thật thì chữ nào cũng nối
    liền chữ sau, đúng 0ms - nên dấu chấm là tín hiệu ranh giới DUY NHẤT. Chỉ
    nhận chỗ có dấu chấm đứng trước thì rơi từ 355 xuống 84 đơn vị và mất luôn
    đoạn tốt nhất của cả bản ghi ("em thấy tự ti và bản thân mình tệ quá chị ạ"),
    vì trước chữ "em" không hề có dấu chấm.

    Nên nhận CẢ chuỗi bước đều: cứ vài từ lại cho phép bắt đầu một ứng viên. Chỗ
    bắt đầu xấu không lọt được xa - khâu cho STT nghe lại clip đã cắt sẽ loại nó.
    """
    if not ws:
        return []
    sau_cham = [0] + [j + 1 for j in range(len(ws) - 1) if _het_cau(ws, j)]
    return sorted(set(sau_cham) | set(range(0, len(ws), BUOC_DAU)))


def _diem_ket(ws: list[dict], j: int) -> float:
    """Kết ở đây có tự nhiên không. Cao hơn = chỗ ngắt đẹp hơn."""
    chu = ws[j]["word"]
    # Hết câu THẬT hay chưa. Phải xét trước: thưởng cho tiểu từ ở bất kỳ đâu là
    # dạy bộ tách đi săn chữ trùng âm giữa câu để cắt vào, và nó làm đúng thế -
    # "kể cho mình nghe ... và nếu có thể thì bạn ấy" là một đoạn nó từng chọn.
    if not _het_cau(ws, j):
        return 0.0
    return 150.0 if gon(chu) in TIEU_TU else 50.0


def tach_don_vi(doan_stt: list[dict]) -> list[dict]:
    """Gom từ thành ứng viên dài 3,0-5,5s, CẮT ĐÚNG RANH GIỚI TỪ.

    Cắt theo giây thay vì theo mốc chữ là lỗi đã mắc: mốc rơi vào giữa một từ,
    STT nghe ra thêm chữ "không" không hề có ở đầu clip, và dùng clip đó làm
    đoạn mẫu thì F5 đọc ra đúng chữ sai ấy (WER 160%).
    """
    ws = _phang(doan_stt)
    ra, da_co = [], set()
    for i in _dau_cau(ws):
        tot, j = None, i
        while j < len(ws):
            if j > i and ws[j]["start"] - ws[j - 1]["end"] > KHE_TOI_DA:
                break                       # khe im rộng -> không nuốt vào clip
            dai = ws[j]["end"] - ws[i]["start"]
            if dai > DAI_MAX:
                break
            if dai >= DAI_MIN:
                # cùng độ đẹp thì lấy đoạn NGẮN hơn: dài hơn = F5 trôi nhiều hơn
                d = _diem_ket(ws, j) - dai
                if tot is None or d > tot[0]:
                    tot = (d, j)
            j += 1
        if tot is None:
            continue
        j = tot[1]
        khoa = (ws[i]["start"], ws[j]["end"])
        if khoa in da_co:
            continue
        da_co.add(khoa)
        ra.append({
            "a": khoa[0],
            "b": khoa[1],
            "dai": round(khoa[1] - khoa[0], 3),
            "loi": " ".join(w["word"] for w in ws[i:j + 1]).strip(),
        })
    return ra


# --- đo -------------------------------------------------------------------

def _khung(x: np.ndarray, sr: int) -> np.ndarray:
    n = max(1, int(sr * _KHUNG_MS / 1000))
    k = len(x) // n
    return x[: k * n].reshape(k, n) if k else np.empty((0, n))


def _f0_khung(k: np.ndarray, sr: int) -> float:
    """Cao độ một khung bằng tự tương quan, có chữa lỗi bội quãng tám."""
    k = k - k.mean()
    if not np.any(k):
        return 0.0
    # Tự tương quan bằng FFT, KHÔNG dùng `np.correlate`: bản trực tiếp là O(n^2),
    # mà một bản ghi 20 phút ở 48kHz có ~35 nghìn khung, mỗi khung 1920 mẫu ->
    # gần 130 tỉ phép. Đo thử thì khâu này một mình ăn hơn 5 phút.
    m = 1 << int(np.ceil(np.log2(2 * len(k))))
    f = np.fft.rfft(k, m)
    r = np.fft.irfft(f * np.conj(f), m)[:len(k)]
    if r[0] <= 0:
        return 0.0
    lo, hi = int(sr / _F0_MAX), min(int(sr / _F0_MIN), len(r) - 1)
    if hi <= lo:
        return 0.0
    tre = lo + int(np.argmax(r[lo:hi + 1]))
    # Bắt nhầm bội 2 là lỗi kinh điển: nếu nửa trễ cũng mạnh gần bằng thì cao
    # độ thật là chỗ đó (tần số gấp đôi).
    nua = tre // 2
    if nua >= lo and r[nua] > 0.85 * r[tre]:
        tre = nua
    return sr / tre if tre else 0.0


def _do_pho(x: np.ndarray, sr: int) -> tuple[float, float, float]:
    """Trả (H1-H2 dB, cao độ trung vị Hz, dải 10-90% Hz) trên khung CÓ TIẾNG."""
    kh = _khung(x, sr)
    if not len(kh):
        return 0.0, 0.0, 0.0
    rms = np.sqrt((kh ** 2).mean(axis=1))
    dinh = rms.max()
    if dinh <= 0:
        return 0.0, 0.0, 0.0
    co = kh[rms > 0.2 * dinh]           # chỉ khung có tiếng mới có cao độ
    if not len(co):
        return 0.0, 0.0, 0.0

    cua = np.hanning(co.shape[1])
    f0s, h = [], []
    for k in co:
        f = _f0_khung(k, sr)
        if not (_F0_MIN <= f <= _F0_MAX):
            continue
        f0s.append(f)
        pho = np.abs(np.fft.rfft(k * cua))
        tan = np.fft.rfftfreq(len(k), 1 / sr)
        i1 = int(np.argmin(np.abs(tan - f)))
        i2 = int(np.argmin(np.abs(tan - 2 * f)))
        if i2 < len(pho) and pho[i1] > 0 and pho[i2] > 0:
            h.append(20 * np.log10(pho[i1] / pho[i2]))
    if not f0s:
        return 0.0, 0.0, 0.0
    f0s = np.asarray(f0s)
    return (float(np.median(h)) if h else 0.0,
            float(np.median(f0s)),
            float(np.percentile(f0s, 90) - np.percentile(f0s, 10)))


def _nen(x: np.ndarray, sr: int) -> float:
    """Sàn nhiễu: độ to của 10% khung im nhất, tính bằng dBFS."""
    kh = _khung(x, sr)
    if not len(kh):
        return -120.0
    rms = np.sqrt((kh ** 2).mean(axis=1))
    return float(20 * np.log10(np.percentile(rms, 10) + 1e-12))


def cham_diem(pcm, sr: int, loi: str, loi_nghe_lai: str) -> dict:
    """Số đo của một ứng viên. Không phán, chỉ đo."""
    x = np.asarray(pcm, dtype=np.float64).squeeze()
    if x.ndim > 1:
        x = x.mean(axis=1)
    h1h2, f0_tv, f0_dai = _do_pho(x, sr)
    return {
        "dai": len(x) / sr if sr else 0.0,
        "lech_loi": cer(loi, loi_nghe_lai),
        "h1h2": round(h1h2, 2),
        "nen": round(_nen(x, sr), 1),
        "f0_tv": round(f0_tv, 1),
        "f0_dai": round(f0_dai, 1),
        "co_tieu_tu": co_tieu_tu(loi),
        "le_phep": le_phep(loi),
    }


# --- xếp hạng -------------------------------------------------------------

def _thang(v: float, tot: float, te: float) -> float:
    return float(np.clip((te - v) / (te - tot), 0.0, 1.0))


def lech_o_bien(loi: str, nghe_lai: str) -> bool:
    """Chỗ lệch có nằm ở TỪ ĐẦU hoặc TỪ CUỐI không.

    Lệch ở biên nghĩa là mốc cắt ăn cụt một từ hoặc ăn lẹm sang từ bên cạnh -
    clip mở đầu (hoặc kết thúc) bằng một âm dở dang. Đó là thứ làm F5 vỡ tiếng.
    Lệch ở giữa thì chỉ là STT nghe nhoè, clip vẫn tốt.
    """
    a, b = gon(loi).split(), gon(nghe_lai).split()
    if not a or not b:
        return True
    return a[0] != b[0] or a[-1] != b[-1]


def _dat(u: dict) -> bool:
    """Loại thứ CHẮC CHẮN hỏng. Cắt cụt biên thì trừ điểm, không loại.

    Đã thử loại thẳng khi lệch ở biên: trên bản ghi thật chỉ còn ĐÚNG MỘT ứng
    viên (luật cũ giữ 3) - không đủ để nghe so, mà mục đích của cả tính năng là
    đưa ra danh sách để tai người chọn.

    Và loại thẳng là sai chỗ: `.txt` KHÔNG lấy từ khâu tách mà lấy từ chính STT
    nghe lại clip đã cắt, nên nó khớp tiếng theo cấu tạo. "Lệch biên" ở đây chỉ
    còn nói lên clip cắt cụt một âm - đáng trừ điểm, chưa có bằng chứng là đủ
    hỏng để vứt. Ca WER 160% ngày xưa lệch vì `.txt` ghi sai lời, một chuyện
    khác hẳn, không còn xảy ra được nữa.
    """
    return (DAI_MIN <= u.get("dai", 0.0) <= DAI_MAX
            and u.get("lech_loi", 1.0) <= LECH_GIUA_TRAN)


def diem(u: dict) -> float:
    return round(
        TRONG_SO["tieu_tu"] * bool(u.get("co_tieu_tu"))
        + TRONG_SO["h1h2"] * _thang(u.get("h1h2", H1H2_TE), H1H2_TOT, H1H2_TE)
        + TRONG_SO["nen"] * _thang(u.get("nen", NEN_TE), NEN_TOT, NEN_TE)
        + TRONG_SO["le_phep"] * bool(u.get("le_phep"))
        + TRONG_SO["cut_bien"] * bool(
            u.get("nghe_lai") is not None
            and lech_o_bien(u.get("loi", ""), u["nghe_lai"])), 4)


def xep_hang(ung_vien: list[dict]) -> list[dict]:
    """Loại thứ chắc chắn hỏng, rồi xếp phần còn lại theo điểm.

    KHÔNG lấy độ trôi cao độ của clip ra chấm: tương quan với đầu ra chỉ +0,48,
    và `heu_a6` phá quy luật (clip tự trôi 47,7% mà đầu ra chỉ trôi 6%). Vẫn đo
    và báo cáo, nhưng chưa đủ bằng chứng để cho vào điểm.
    """
    dat = []
    for u in ung_vien or []:
        if not _dat(u):
            continue
        u = dict(u)
        u["diem"] = diem(u)
        dat.append(u)
    return sorted(dat, key=lambda u: -u["diem"])


# --- chia cửa sổ để gửi cho STT -------------------------------------------

# Bản ghi 20 phút là ~200MB. Gửi nguyên tệp cho Whisper vừa chậm vừa dễ hết bộ
# nhớ, nên phải chia. Nhưng chia theo GIÂY CHẴN thì ranh giới cửa sổ rơi vào
# giữa từ - đúng loại lỗi đã làm hỏng clip `heu_a6_50` (WER 160%) - và câu vắt
# qua chỗ đó mất luôn. Chia tại CHỖ IM.
CUA_SO_S = 40.0
_NGUONG_IM_DB = -42.0
_LO_MAU = 1_000_000          # số mẫu mỗi lô khi quét năng lượng


def cua_so_ngat(x, sr: int, dai_toi_da: float = CUA_SO_S) -> list[tuple[int, int]]:
    """Chia bản ghi thành cửa sổ (mốc mẫu), cắt GIỮA quãng im khi có thể.

    Trả danh sách (đầu, cuối) phủ kín bản ghi, không chồng lấn, không hở.

    Cắt tại khung im CUỐI CÙNG thì mốc rơi đúng lúc tiếng vào lại, phụ âm bật
    hơi vào rất nhẹ nên dễ mất đầu từ. Nhắm vào GIỮA quãng im mới có đệm hai
    bên.
    """
    x = np.asarray(x).squeeze()
    n_max = int(sr * dai_toi_da)
    if len(x) <= n_max:
        return [(0, len(x))] if len(x) else []

    b = max(1, int(sr * 0.01))                       # khung 10ms
    k = len(x) // b
    # Theo LÔ, không ép cả mảng lên float64: bản ghi 20 phút là ~29 triệu mẫu,
    # ép nguyên mảng ngốn thêm ~230MB và thêm chừng ấy nữa cho mảng bình phương
    # tạm - trên máy đang chạy F5 lẫn Ollama thì đó là chỗ hết bộ nhớ.
    rms = np.empty(k, dtype=np.float64)
    lo_khung = max(1, _LO_MAU // b)
    for t in range(0, k, lo_khung):
        h = min(t + lo_khung, k)
        lo = x[t * b:h * b].astype(np.float64).reshape(h - t, b)
        rms[t:h] = np.sqrt((lo ** 2).mean(axis=1))
    dinh = rms.max()
    if dinh <= 0:
        return [(0, len(x))]
    im = 20 * np.log10(rms / dinh + 1e-12) < _NGUONG_IM_DB

    # giữa từng quãng im, đổi ra mốc mẫu
    vien = np.diff(np.concatenate(([0], im.view(np.int8), [0])))
    giua = [((int(a) + int(z)) // 2) * b
            for a, z in zip(np.nonzero(vien == 1)[0], np.nonzero(vien == -1)[0])]
    giua = np.asarray(giua, dtype=np.int64)

    ra, i = [], 0
    while i < len(x):
        het = i + n_max
        if het >= len(x):
            ra.append((i, len(x)))
            break
        hop = giua[(giua >= i + n_max // 2) & (giua <= het)]
        ket = int(hop[-1]) if len(hop) else het
        ra.append((i, ket))
        i = ket
    return ra


# --- nắn mốc cắt ----------------------------------------------------------

NAN_CUA_MS = 150.0


def nan_moc(x, sr: int, moc: int, cua_ms: float = NAN_CUA_MS) -> int:
    """Kéo mốc cắt về chỗ LẶNG NHẤT trong sóng âm, quanh mốc chữ.

    Mốc chữ của Whisper là kết quả căn chữ, không phải ranh giới âm thật - cắt
    đúng vào đó là cắt giữa một phụ âm. Clip mở đầu bằng âm cụt thì STT nghe lại
    ra khác, và ứng viên trượt khâu kiểm lời dù nội dung hoàn toàn tốt. Đó đúng
    là cách đoạn hay nhất của bản ghi bị loại.

    Chỉ được nắn trong cửa sổ hẹp: đi xa là ăn sang từ bên cạnh hoặc cụt mất từ.
    """
    x = np.asarray(x).squeeze()
    if not len(x):
        return 0
    moc = int(np.clip(moc, 0, len(x)))
    cua = int(sr * cua_ms / 1000)
    lo, hi = max(0, moc - cua), min(len(x), moc + cua)
    if hi - lo < 2:
        return moc
    b = max(1, int(sr * 0.005))                      # khung 5ms
    k = (hi - lo) // b
    if k < 2:
        return moc
    nl = (x[lo:lo + k * b].astype(np.float64).reshape(k, b) ** 2).mean(axis=1)
    return lo + int(np.argmin(nl)) * b + b // 2


# --- dẹp ứng viên đè lên nhau ---------------------------------------------

# Đè nhau quá tỉ lệ này thì coi là một - giữ cái điểm cao hơn.
DE_LEN_TRAN = 0.5


def dep_de_len(uv: list[dict], tran: float = DE_LEN_TRAN) -> list[dict]:
    """Bỏ ứng viên trùng chỗ, giữ cái điểm cao nhất mỗi vùng.

    Cho phép bắt đầu ở nhiều chỗ thì cùng một câu đẻ ra chục biến thể lệch nhau
    vài từ. Chạy thật trên bản ghi 20 phút: 1520 ứng viên, mà hai cái đứng đầu
    là CÙNG MỘT CÂU chỉ khác chỗ vào - chúng chiếm hết suất kiểm lời (khâu đắt
    nhất) nên đoạn hay nhất của cả bản ghi không tới lượt.
    """
    ra = []
    for u in sorted(uv or [], key=lambda z: -z.get("diem", 0.0)):
        a, b = u.get("a", 0.0), u.get("b", 0.0)
        trum = False
        for v in ra:
            chung = min(b, v["b"]) - max(a, v["a"])
            if chung > 0 and chung / max(1e-9, min(b - a, v["b"] - v["a"])) > tran:
                trum = True
                break
        if not trum:
            ra.append(u)
    return ra
