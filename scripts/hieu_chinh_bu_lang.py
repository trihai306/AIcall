"""Do lai HE_SO_BU_LANG: cap bao nhieu thi F5 doc dung nhip dinh ra.

He so nay bu cho phan LANG bi cat sau khi sinh. No duoc chinh TRUOC khi co
cat_lang_bia va truoc khi bo dau cau - hai thay doi do lam gan het lang bien
mat, nen he so cu thanh thoi gian THUA. F5 do thua vao am tiet cuoi (ngan dai).

Cach do: cap thoi luong voi he so 1.00 (dung muc tieu), sinh, cat lang, roi xem
tieng that ra NGAN hon bao nhieu. Ty le do CHINH LA he so can bu.
"""
import sys, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch
from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.pipeline.text_chunker import tach_manh, GIOI_HAN_TU_MANH
from backend.services import tts_service as T
from f5_tts.infer.utils_infer import infer_batch_process

CAU_AI = [
 "Dạ anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha anh, tùy vào hồ sơ và thu nhập của mình ạ.",
 "Hạn mức tối đa cho vay tín chấp là năm trăm triệu đồng, còn giấy tờ thì anh chuẩn bị chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất.",
 "Với mức lương mười lăm triệu một tháng và làm việc ổn định ba năm thì anh hoàn toàn đủ điều kiện vay ạ.",
 "Thời gian giải ngân sẽ là trong vòng 24 giờ sau khi hồ sơ được phê duyệt, anh yên tâm nhé.",
 "Nếu anh trả trước hạn thì sẽ có phí phạt khoảng hai phần trăm trên số tiền trả trước, tính theo dư nợ còn lại.",
 "Anh chị cần đáp ứng các điều kiện như công dân Việt Nam từ 22 đến 60 tuổi, có thu nhập ổn định và không có nợ xấu tại CIC.",
]
def cat_het(s):
    ra, con = [], s
    while True:
        m, con = tach_manh(con, first_chunk=not ra)
        if m is None: break
        ra.append(m)
    if con.strip():
        if ra and len(con.split()) < 3: ra[-1] += " " + con.strip()
        else: ra.append(con.strip())
    return ra

svc = T.F5TTSService(); svc.load()
import asyncio; ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
dai_ref = rw.shape[-1] / rs

def sinh(chu, fix):
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y, sr, _ = next(infer_batch_process((rw, rs), rt, [T.bo_dau_cau_cho_f5(chu)],
            svc._model, svc._vocoder, mel_spec_type="vocos", progress=None,
            nfe_step=nfe, speed=sp, fix_duration=fix, device=svc._model.device))
    y = T.cat_lang_bia(T.trim_silence(np.asarray(y), sr), sr)
    return y, sr

def am_tiet_cuoi(y, sr):
    """Do dai AM TIET cuoi = tu day nang luong cuoi den het tieng."""
    h = max(1, int(sr * 0.01)); k = len(y) // h
    e = np.array([float(np.sqrt((y[i*h:(i+1)*h] ** 2).mean())) for i in range(k)])
    if k < 20: return 0.0, 0.0
    e = np.convolve(e, np.ones(5) / 5, mode="same")
    dinh = [i for i in range(2, k-2)
            if e[i] == max(e[max(0,i-6):i+7]) and e[i] > e.max() * 0.18]
    if len(dinh) < 2: return 0.0, 0.0
    ranh = [0] + [int(np.argmin(e[a:b]) + a) for a, b in zip(dinh, dinh[1:])] + [k]
    d = np.diff(ranh) * 10.0
    return float(d[-1]), float(np.median(d[:-1]))

manh = [m for c in CAU_AI for m in cat_het(normalize_for_tts(c))]
print(f"\n  {len(manh)} manh, cat {GIOI_HAN_TU_MANH} tu\n")
print(f"  {'am':>3} {'cap':>6} {'ra':>6} {'hao':>6}   chu")
print("  " + "-" * 74)
ty = []
for m in manh:
    cu = T.HE_SO_BU_LANG; T.HE_SO_BU_LANG = 1.00
    fix = T.thoi_luong_ep(m, dai_ref, sp); T.HE_SO_BU_LANG = cu
    if fix is None:
        print(f"  {T.so_am_tiet(m):>3}   (qua ngan, khong ep)          {m[:40]}"); continue
    y, sr = sinh(m, fix); cap = fix - dai_ref; ra = len(y) / sr
    ty.append(cap / ra)
    print(f"  {T.so_am_tiet(m):>3} {cap:>5.2f}s {ra:>5.2f}s {cap/ra:>5.2f}x   {m[:40]}")
print("  " + "-" * 74)
print(f"\n  he so bu CAN THIET : trung vi {st.median(ty):.3f}"
      f"  (khoang {min(ty):.3f} - {max(ty):.3f})")
print(f"  he so DANG DAT     : {T.HE_SO_BU_LANG:.3f}"
      f"   -> dang cap DU {(T.HE_SO_BU_LANG/st.median(ty)-1)*100:.0f}%")

CAU = normalize_for_tts("Anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha.")
print(f"\n  cau anh nghe thay: {CAU}")
print(f"\n  {'he so':>7} {'ra':>6} {'am cuoi':>8} {'am giua':>8} {'cuoi/giua':>10}")
print("  " + "-" * 46)
for he in (1.11, round(st.median(ty), 3), 1.00, None):
    cu = T.HE_SO_BU_LANG
    if he is not None: T.HE_SO_BU_LANG = he
    fix = T.thoi_luong_ep(CAU, dai_ref, sp) if he is not None else None
    T.HE_SO_BU_LANG = cu
    y, sr = sinh(CAU, fix); c, g = am_tiet_cuoi(y, sr)
    nhan = f"{he:.3f}" if he is not None else "khong ep"
    print(f"  {nhan:>7} {len(y)/sr:>5.2f}s {c:>6.0f}ms {g:>6.0f}ms {c/max(g,1):>9.2f}x")
print("  " + "-" * 46)
print("\n  'cuoi/giua' = am tiet cuoi dai gap may lan am tiet thuong. To = ngan dai.")
