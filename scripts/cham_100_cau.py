"""Cham 100 cau mau: F5 doc RA DUNG CHU khong, va nhip co deu khong.

Cho STT nghe lai tung cau roi so voi chu goc (ban DA CHUAN HOA - do moi la thu
F5 nhan). Hat giong da co dinh nen ket qua TAT DINH: chay lai ra y nguyen.

Bao gom ca do NHIP tung cau (am tiet/phut) de tim cau doc nhanh/cham bat thuong.

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\cham_100_cau.py
"""
import base64
import difflib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import unicodedata
import uuid
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.tts_service import so_am_tiet

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
STT = "http://127.0.0.1:8178/inference"
GIONG = sys.argv[1] if len(sys.argv) > 1 else "giong_heu"

CAU = [
    ('chao', 'Dạ em chào anh chị, em là Lan bên Ngân hàng Quân đội ạ.'),
    ('chao', 'Dạ em chào anh Minh, em gọi từ Ngân hàng Quân đội ạ.'),
    ('chao', 'Dạ vâng em nghe anh chị ạ.'),
    ('chao', 'Dạ em xin phép trao đổi ngắn với anh chị ạ.'),
    ('chao', 'Dạ em cảm ơn anh chị đã nghe máy ạ.'),
    ('chao', 'Dạ anh chị đang quan tâm sản phẩm nào ạ?'),
    ('chao', 'Dạ em có thể hỗ trợ gì thêm cho anh chị không ạ?'),
    ('chao', 'Dạ em xin phép gọi lại sau ạ.'),
    ('lai_suat', 'Dạ lãi suất vay tín chấp của bên em từ bảy phẩy chín phần trăm một năm ạ.'),
    ('lai_suat', 'Lãi suất vay mua nhà ưu đãi sáu phẩy năm phần trăm trong hai năm đầu ạ.'),
    ('lai_suat', 'Sau ưu đãi thì lãi suất thả nổi theo thị trường, khoảng tám đến mười phần trăm ạ.'),
    ('lai_suat', 'Lãi suất hiện tại là bảy phẩy chín phần trăm một năm, chưa gồm phí bảo hiểm ạ.'),
    ('lai_suat', 'Dạ lãi suất cố định trong suốt thời gian vay ạ.'),
    ('lai_suat', 'Lãi suất tính trên dư nợ giảm dần ạ.'),
    ('lai_suat', 'Dạ mức lãi suất còn phụ thuộc vào hồ sơ của anh chị ạ.'),
    ('lai_suat', 'Lãi suất thẻ tín dụng là hai phẩy năm phần trăm một tháng ạ.'),
    ('han_muc', 'Hạn mức vay tín chấp lên đến năm trăm triệu đồng ạ.'),
    ('han_muc', 'Dạ hạn mức thẻ tín dụng từ mười triệu đến năm trăm triệu đồng ạ.'),
    ('han_muc', 'Vay mua nhà được tối đa tám mươi phần trăm giá trị bất động sản ạ.'),
    ('han_muc', 'Hạn mức tối đa là mười tỷ đồng cho vay mua nhà ạ.'),
    ('han_muc', 'Dạ với thu nhập của anh chị thì hạn mức khoảng ba trăm triệu ạ.'),
    ('han_muc', 'Anh chị có thể vay từ năm mươi triệu trở lên ạ.'),
    ('han_muc', 'Hạn mức được cấp bằng năm lần thu nhập hàng tháng ạ.'),
    ('han_muc', 'Dạ số tiền vay tối thiểu là mười triệu đồng ạ.'),
    ('ho_so', 'Dạ hồ sơ chỉ cần chứng minh nhân dân và sao kê lương ba tháng gần nhất ạ.'),
    ('ho_so', 'Anh chị cần chuẩn bị căn cước công dân và hợp đồng lao động ạ.'),
    ('ho_so', 'Dạ cần thêm sổ đỏ và giấy tờ pháp lý của bất động sản ạ.'),
    ('ho_so', 'Hồ sơ gồm căn cước, sao kê lương và xác nhận thu nhập ạ.'),
    ('ho_so', 'Dạ anh chị không cần chứng minh thu nhập với gói này ạ.'),
    ('ho_so', 'Bên em sẽ có nhân viên tới tận nhà hỗ trợ làm hồ sơ ạ.'),
    ('ho_so', 'Dạ chỉ cần bản photo, không cần công chứng ạ.'),
    ('ho_so', 'Anh chị cần cung cấp thêm hóa đơn điện nước ba tháng ạ.'),
    ('thoi_gian', 'Dạ hồ sơ được duyệt trong hai mươi tư giờ ạ.'),
    ('thoi_gian', 'Giải ngân trong vòng hai tư giờ sau khi phê duyệt ạ.'),
    ('thoi_gian', 'Thời hạn vay từ mười hai đến sáu mươi tháng ạ.'),
    ('thoi_gian', 'Vay mua nhà có thời hạn tối đa hai mươi lăm năm ạ.'),
    ('thoi_gian', 'Dạ anh chị muốn trả trong bao lâu ạ?'),
    ('thoi_gian', 'Thời gian xét duyệt khoảng một đến hai ngày làm việc ạ.'),
    ('thoi_gian', 'Dạ em sẽ báo lại kết quả trong hôm nay ạ.'),
    ('thoi_gian', 'Anh chị có thể tất toán trước hạn sau mười hai tháng ạ.'),
    ('tra_gop', 'Vay một trăm triệu trong ba mươi sáu tháng thì mỗi tháng trả khoảng ba phẩy bốn triệu ạ.'),
    ('tra_gop', 'Dạ mỗi tháng anh chị trả cả gốc và lãi khoảng năm triệu đồng ạ.'),
    ('tra_gop', 'Trả trước hạn thì phí là hai phần trăm trên số tiền trả trước ạ.'),
    ('tra_gop', 'Dạ kỳ đầu tiên thanh toán sau ba mươi ngày kể từ ngày giải ngân ạ.'),
    ('tra_gop', 'Anh chị có thể chọn ngày thanh toán cố định hàng tháng ạ.'),
    ('tra_gop', 'Dạ nếu chậm thanh toán thì phí phạt là bốn phần trăm ạ.'),
    ('tra_gop', 'Tổng số tiền phải trả là một trăm hai mươi triệu đồng ạ.'),
    ('tra_gop', 'Dạ dư nợ hiện tại của anh chị là một trăm bốn mươi hai triệu năm trăm nghìn đồng ạ.'),
    ('tu_choi', 'Dạ em hiểu ạ, em xin phép không làm phiền thêm ạ.'),
    ('tu_choi', 'Dạ em xin lỗi đã gọi không đúng lúc ạ.'),
    ('tu_choi', 'Dạ vâng, em xin phép gọi lại sau ạ.'),
    ('tu_choi', 'Dạ em cảm ơn anh chị đã dành thời gian ạ.'),
    ('tu_choi', 'Dạ nếu sau này anh chị cần thì gọi lại cho em ạ.'),
    ('tu_choi', 'Dạ em ghi nhận, khi nào tiện anh chị nhắn em ạ.'),
    ('tu_choi', 'Dạ em hiểu là anh chị đang bận ạ.'),
    ('tu_choi', 'Dạ không sao ạ, em chúc anh chị một ngày tốt lành ạ.'),
    ('viet_tat', 'Dạ anh chị cần mang căn cước công dân và chứng minh nhân dân ạ.'),
    ('viet_tat', 'Bên em sẽ gửi mã xác thực qua tin nhắn cho anh chị ạ.'),
    ('viet_tat', 'Dạ em kiểm tra thông tin tín dụng của anh chị trên hệ thống ạ.'),
    ('viet_tat', 'Anh chị có thể rút tiền tại các máy rút tiền tự động ạ.'),
    ('viet_tat', 'Dạ hợp đồng lao động và bảo hiểm xã hội đều được ạ.'),
    ('viet_tat', 'Em cần thêm giấy xác nhận tạm trú của anh chị ạ.'),
    ('viet_tat', 'Dạ anh chị có thẻ tín dụng ở ngân hàng nào chưa ạ?'),
    ('viet_tat', 'Dạ bên em là Ngân hàng Quân đội ạ.'),
    ('so_lieu', 'Dạ lãi suất bảy phẩy chín phần trăm, hạn mức năm trăm triệu, thời hạn sáu mươi tháng ạ.'),
    ('so_lieu', 'Anh chị vay tám mươi triệu, trả ba mươi sáu tháng, mỗi tháng hai phẩy sáu triệu ạ.'),
    ('so_lieu', 'Dạ phí thường niên năm đầu miễn phí, từ năm thứ hai là ba trăm nghìn ạ.'),
    ('so_lieu', 'Hạn mức tín dụng của anh chị là một trăm năm mươi triệu đồng ạ.'),
    ('so_lieu', 'Dạ tỷ lệ cho vay là bảy mươi phần trăm giá trị tài sản ạ.'),
    ('so_lieu', 'Số tiền giải ngân là hai trăm triệu đồng ạ.'),
    ('so_lieu', 'Dạ anh chị đã trả được mười tám kỳ trong ba mươi sáu kỳ ạ.'),
    ('so_lieu', 'Lãi suất quá hạn là một trăm năm mươi phần trăm lãi suất trong hạn ạ.'),
    ('cau_dai', 'Dạ em xin phép thông tin lại với anh chị, gói vay tín chấp của bên em có lãi suất từ bảy phẩy chín phần trăm một năm, hạn mức lên đến năm trăm triệu đồng, và thời hạn linh hoạt từ mười hai đến sáu mươi tháng ạ.'),
    ('cau_dai', 'Anh chị cứ yên tâm, hồ sơ chỉ cần chứng minh nhân dân và sao kê lương ba tháng gần nhất, bên em sẽ có nhân viên tới tận nhà hỗ trợ, và giải ngân trong vòng hai tư giờ sau khi phê duyệt ạ.'),
    ('cau_dai', 'Dạ với vay mua nhà thì lãi suất ưu đãi sáu phẩy năm phần trăm trong hai năm đầu, sau đó thả nổi theo thị trường, hạn mức lên đến tám mươi phần trăm giá trị bất động sản và thời hạn tối đa hai mươi lăm năm ạ.'),
    ('cau_dai', 'Em hiểu là anh chị đang cân nhắc, nên em xin phép gửi thông tin chi tiết qua tin nhắn để anh chị xem kỹ hơn, và nếu có thắc mắc gì thì anh chị cứ gọi lại cho em bất cứ lúc nào ạ.'),
    ('cau_dai', 'Dạ nếu anh chị vay một trăm triệu đồng trong ba mươi sáu tháng thì mỗi tháng phải trả cả gốc và lãi khoảng ba phẩy bốn triệu đồng, và tổng số tiền phải trả là khoảng một trăm hai mươi hai triệu đồng ạ.'),
    ('cau_dai', 'Dạ em xin phép xác nhận lại thông tin của anh chị, họ tên là Nguyễn Văn Minh, số điện thoại là không chín một hai ba bốn năm sáu bảy tám, và anh chị muốn vay tám mươi triệu đồng đúng không ạ?'),
    ('xung_ho', 'Dạ bên em có gói phù hợp với anh Minh ạ.'),
    ('xung_ho', 'Dạ chị Hoa cần em tư vấn thêm gì không ạ?'),
    ('xung_ho', 'Dạ anh chị cho em xin thông tin để em kiểm tra ạ.'),
    ('xung_ho', 'Dạ em xin phép hỏi anh Minh vài câu ngắn ạ.'),
    ('xung_ho', 'Dạ chị cứ yên tâm nhé, em sẽ theo hồ sơ của chị ạ.'),
    ('xung_ho', 'Dạ anh Minh có muốn em gửi bảng tính chi tiết không ạ?'),
    ('hoi_lai', 'Dạ anh chị đang cần vay khoảng bao nhiêu ạ?'),
    ('hoi_lai', 'Dạ anh chị dự kiến vay trong bao lâu ạ?'),
    ('hoi_lai', 'Dạ thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?'),
    ('hoi_lai', 'Dạ anh chị đang làm ở công ty nào ạ?'),
    ('hoi_lai', 'Dạ anh chị đã từng vay ở ngân hàng nào chưa ạ?'),
    ('hoi_lai', 'Dạ anh chị muốn vay để làm gì ạ?'),
    ('hoi_lai', 'Dạ em xin phép hỏi anh chị bao nhiêu tuổi ạ?'),
    ('hoi_lai', 'Dạ anh chị có tài sản thế chấp không ạ?'),
]
CAU += [
    ("them", "Dạ em xin phép xác nhận số điện thoại của anh là không chín tám bảy sáu năm bốn ba hai một ạ."),
    ("them", "Dạ bên em không thu bất kỳ khoản phí nào trước khi giải ngân ạ."),
    ("them", "Dạ anh chị chỉ cần ký hợp đồng một lần tại nhà ạ."),
    ("them", "Dạ khoản vay này không cần người bảo lãnh ạ."),
    ("them", "Dạ em gửi anh chị bảng tính lãi và gốc từng tháng qua tin nhắn ạ."),
    ("them", "Dạ nếu anh chị đồng ý thì em mở hồ sơ luôn hôm nay ạ."),
    ("them", "Dạ khoản vay được bảo hiểm khoản vay đi kèm, phí là một phần trăm ạ."),
    ("them", "Dạ em xin phép ghi nhận và chuyển cho bộ phận thẩm định ạ."),
]


def sinh(text):
    d = urllib.parse.urlencode({"text": text, "voice_name": GIONG}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def nghe(b64):
    ranh = uuid.uuid4().hex
    b = io.BytesIO()
    w = lambda s: b.write(s if isinstance(s, bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k, v in (("language", "vi"), ("response_format", "json")):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req = urllib.request.Request(STT, data=b.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r).get("text", "").strip()


def chuan(s):
    # NFC BẮT BUỘC: "hóa" và "hoá" là CÙNG một từ, chỉ khác cách tổ hợp dấu
    # thanh trong Unicode. Không chuẩn hoá thì đếm ra lỗi giả - đã mắc.
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def cer(a, b):
    a, b = chuan(a).replace(" ", ""), chuan(b).replace(" ", "")
    if not a:
        return 0.0
    return 1 - difflib.SequenceMatcher(None, a, b).ratio()


def lech_tu(mong, ra):
    a, b = chuan(mong).split(), chuan(ra).split()
    mat, them = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op in ("delete", "replace"):
            mat += a[i1:i2]
        if op in ("insert", "replace"):
            them += b[j1:j2]
    return mat, them


def giay_co_tieng(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = max(1, int(sr * 0.02)); k = len(x) // n
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1))
    return (rms > max(rms.max() * 0.10, 1e-4)).sum() * 0.02


def main():
    print(f"Giọng {GIONG} · {len(CAU)} câu · hạt giống cố định nên kết quả tất định\n")
    theo_nhom = defaultdict(lambda: [0, 0, [], []])   # dat, tong, cer, nhip
    xau = []
    for i, (nhom, cau) in enumerate(CAU, 1):
        r = sinh(cau)
        if r.get("error"):
            print(f"  {i:3}. LỖI {r['error']}"); continue
        mong = normalize_for_tts(cau)
        ra = nghe(r["audio"])
        c = cer(mong, ra)
        at = so_am_tiet(mong)
        gt = giay_co_tieng(r["audio"])
        nhip = at / gt * 60 if gt else 0
        g = theo_nhom[nhom]
        g[1] += 1; g[2].append(c); g[3].append(nhip)
        if c <= 0.02:
            g[0] += 1
        else:
            mat, them = lech_tu(mong, ra)
            xau.append((c, nhom, cau, mat, them))
        if i % 20 == 0:
            print(f"  ...{i}/{len(CAU)}")

    print(f"\n{'nhóm':<12}{'đạt':>6}{'/':^3}{'tổng':<6}{'CER tb':>9}{'nhịp tb':>10}{'nhịp min-max':>16}")
    print("-" * 66)
    T = D = 0
    for k, (dat, tong, cers, nhips) in sorted(theo_nhom.items()):
        T += tong; D += dat
        print(f"{k:<12}{dat:>6}{'/':^3}{tong:<6}{sum(cers)/len(cers)*100:>8.1f}%"
              f"{sum(nhips)/len(nhips):>10.0f}{f'{min(nhips):.0f} - {max(nhips):.0f}':>16}")
    print("-" * 66)
    print(f"{'TỔNG':<12}{D:>6}{'/':^3}{T:<6}   ({D/T*100:.0f}% câu đọc đúng, CER <= 2%)")

    if xau:
        print(f"\n{len(xau)} câu lệch quá 2% — nặng nhất trước:")
        for c, nhom, cau, mat, them in sorted(xau, reverse=True)[:14]:
            print(f"\n  CER {c*100:.0f}%  [{nhom}]  {cau[:76]}")
            print(f"      mất={mat}  thừa={them}")


if __name__ == "__main__":
    main()
