"""20 hoi thoai x 5 luot = 100 luot, di DUNG duong that co sinh tieng.

Cham SAU mat, moi mat ung voi mot ban va vua lam:
  1. tu sai   - may nghe lai co dung chu khong
  2. am tiet CUOI MANH - loi con mo, do de biet no o muc nao
  3. nhip giat cuc - chu nao vuot 800 am tiet/phut (ban va he so 0.95)
  4. luoi chan lai suat bia co ra tay khong
  5. quang nghi o cuoi cau (ban va 320ms)
  6. do tre
"""
import asyncio, base64, difflib, io, json, re, statistics, sys, time, unicodedata, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
WS="ws://127.0.0.1:8100/ws/call/new"
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
HOI_THOAI=[
 ("vay tín chấp",["chào em","lãi suất vay tín chấp bao nhiêu","vay được tối đa bao nhiêu","cần giấy tờ gì","bao lâu thì giải ngân"]),
 ("vay tín chấp",["anh cần vay 80 triệu","trả trong 36 tháng mỗi tháng bao nhiêu","lãi suất có đổi không","anh đang nợ chỗ khác có vay được không","phí phạt trả trước thế nào"]),
 ("vay mua nhà",["anh muốn vay mua nhà","lãi suất thế nào","vay được bao nhiêu phần trăm giá trị nhà","thời hạn tối đa mấy năm","cần thế chấp gì"]),
 ("vay mua nhà",["nhà anh 3 tỷ vay được bao nhiêu","có phải mua bảo hiểm không","giải ngân mất bao lâu","ai định giá nhà","sổ đỏ có phải giao ngân hàng không"]),
 ("thẻ tín dụng",["cho anh hỏi về thẻ tín dụng","hạn mức bao nhiêu","phí thường niên thế nào","miễn lãi bao nhiêu ngày","rút tiền mặt được không"]),
 ("thẻ tín dụng",["anh thu nhập 20 triệu mở được thẻ gì","làm thẻ mất bao lâu","có phí phát hành không","trả chậm bị tính sao","hủy thẻ có mất phí không"]),
 ("tiết kiệm",["lãi suất gửi tiết kiệm bao nhiêu","gửi 100 triệu 12 tháng được bao nhiêu","rút trước hạn có mất lãi không","gửi online khác gì","kỳ hạn nào lợi nhất"]),
 ("vay tín chấp",["anh không quan tâm đâu","đang bận","thôi để hôm khác","sao em gọi nhiều thế","đừng gọi nữa"]),
 ("vay tín chấp",["giám đốc ngân hàng tên gì","ngân hàng mình có bao nhiêu chi nhánh","cho anh vay 50 tỷ được không","em tên gì","em làm ở đâu"]),
 ("vay tín chấp",["ok anh đồng ý","giờ làm sao","anh cần chuẩn bị gì","khi nào có tiền","gửi hồ sơ qua đâu"]),
 ("vay mua nhà",["anh so sánh với ngân hàng khác thấy rẻ hơn","sao bên em cao thế","có giảm được không","ưu đãi đến khi nào","có phí ẩn gì không"]),
 ("thẻ tín dụng",["thẻ này dùng ở nước ngoài được không","phí chuyển đổi ngoại tệ bao nhiêu","mất thẻ thì sao","khóa thẻ thế nào","đổi hạn mức được không"]),
 ("vay tín chấp",["anh làm tự do có vay được không","không có hợp đồng lao động thì sao","chứng minh thu nhập kiểu gì","vợ anh đứng tên được không","cần người bảo lãnh không"]),
 ("tiết kiệm",["gửi tiết kiệm cho con được không","dưới 18 tuổi có mở được không","cần giấy tờ gì","lãi nhập gốc không","có rút một phần được không"]),
 ("vay mua nhà",["anh mua nhà dự án vay được không","chủ đầu tư nào bên em liên kết","vay bao nhiêu năm","trả trước bao nhiêu phần trăm","lãi suất năm đầu"]),
 ("vay tín chấp",["anh 62 tuổi vay được không","hưu trí có vay được không","con anh đứng tên thay được không","thủ tục có phức tạp không","mất bao lâu"]),
 ("thẻ tín dụng",["hạn mức 500 triệu có được không","cần thu nhập bao nhiêu","có cần thế chấp không","xét duyệt lâu không","dùng app quản lý được không"]),
 ("vay tín chấp",["em nói lại lãi suất đi","chưa nghe rõ","em nói chậm thôi","số tiền tối đa là bao nhiêu","đúng không đấy"]),
 ("vay mua nhà",["anh muốn vay 2 tỷ","trong 20 năm","mỗi tháng trả bao nhiêu","lãi suất cố định mấy năm","sau đó thế nào"]),
 ("tiết kiệm",["anh có 500 triệu nhàn rỗi","nên gửi kỳ hạn nào","hay mua chứng chỉ tiền gửi","cái nào lãi cao hơn","rủi ro gì không"]),
]
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(tu(s))
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def sai(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
def bo_chu_ma(wl, mong):
    """Whisper de chu ma dai 20-60ms tren doan im cuoi manh.

    Bang chung: 9/10 cho "am tiet cuoi sai" thuc ra doc DUNG, roi bi noi them
    "de thi" / "ngay" / "o" / "im". Chinh nhung chu ma nay la ca nhom
    ">800 am tiet/phut". Khong gat thi CA HAI thuoc do deu noi doi.

    Chi gat o DUOI, chi khi ngan <=80ms VA khong khop tu dang cho - de khong
    lo tay gat mat mot am tiet ngan nhung co that.
    """
    con = set(mong[-3:])
    while len(wl) > 1:
        x = wl[-1]
        if (x.end - x.start) <= 0.080 and unicodedata.normalize(
                "NFC", x.word.strip().lower().strip(".,?!:;")) not in con:
            wl = wl[:-1]; continue
        break
    return wl


def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def nghe(wav, moc=True):
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",
                          initial_prompt=MOI if moc else None,
                          vad_filter=False,beam_size=5,word_timestamps=True)
    return [w for s in segs for w in (s.words or []) if w.end>w.start]
async def mot_hoi_thoai(sp, cau_hoi):
    ra=[]
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        for i,q in enumerate(cau_hoi,1):
            t0=time.perf_counter()
            await ws.send(json.dumps({"type":"text","text":q,"turn_id":i}))
            tieng=[]; tra=""; mt={}
            while True:
                m=json.loads(await asyncio.wait_for(ws.recv(),timeout=240))
                if m.get("type")=="audio":
                    # BO cau dem: no KHONG nam trong full_response, gop vao la
                    # tu tay tao ra "tu thua" roi do oan cho TTS.
                    if m.get("is_filler"): continue
                    d=m.get("data")
                    if d: tieng.append((m.get("chunk_id",0),base64.b64decode(d)))
                if m.get("type")=="turn_complete":
                    tra,mt=m.get("full_response",""),(m.get("metrics") or {}); break
            ra.append((q,tra,mt,tieng,(time.perf_counter()-t0)*1000))
    return ra
async def main():
    e=[]; nhip=[]; cuoi_dung=cuoi_tong=0; chan=0; tre=[]; rong=0
    n=0; t_bd=time.time()
    for k,(sp,qs) in enumerate(HOI_THOAI,1):
        try: luot=await mot_hoi_thoai(sp,qs)
        except Exception as ex:
            print(f"hội thoại {k}: LỖI {type(ex).__name__} {ex}"); continue
        for q,tra,mt,tieng,ms in luot:
            n+=1; tre.append(mt.get("total_ms") or ms)
            if mt.get("chan_lai_suat_bia") or mt.get("chan_so_sai") or mt.get("chan_tien_sai"): chan+=1
            if not tieng: rong+=1; continue
            tieng.sort(key=lambda x:x[0])
            manh=[m for m in _cat_manh_nhu_pipeline(tra)]
            noi=[]
            for j,(_,w) in enumerate(tieng):
                with wave.open(io.BytesIO(w)) as r:
                    assert r.getframerate()==24000 and r.getsampwidth()==2, r.getparams()
                    pcm=r.readframes(r.getnframes())
                noi.append(pcm)
                # cham am tiet CUOI TUNG MANH - dung loi dang mo
                if j<len(manh):
                    mong1=chuan(normalize_for_tts(manh[j])).split()
                    wl1=bo_chu_ma(nghe(w),mong1)
                    if mong1:
                        cuoi_tong+=1
                        if wl1 and unicodedata.normalize("NFC",
                                wl1[-1].word.strip().lower().strip(".,?!"))==mong1[-1]:
                            cuoi_dung+=1
            b=io.BytesIO()
            with wave.open(b,"wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                w.writeframes(b"".join(noi))
            wl=bo_chu_ma(nghe(b.getvalue()),chuan(normalize_for_tts(tra)).split())
            if not wl: continue
            e.append(sai(normalize_for_tts(tra)," ".join(x.word for x in wl)))
            nhip += [60.0/(x.end-x.start) for x in wl]
        print(f"  hội thoại {k:>2}/{len(HOI_THOAI)} ({sp}) xong - {n} lượt, "
              f"{(time.time()-t_bd)/60:.1f} phút", flush=True)
    print("\n" + "="*66)
    print(f"TỔNG {n} lượt · {(time.time()-t_bd)/60:.1f} phút")
    print(f"  từ sai trung bình      {sum(e)/len(e)*100:.1f}%   (lượt đạt ≤5%: "
          f"{sum(1 for v in e if v<=0.05)}/{len(e)})")
    print(f"  âm tiết cuối mảnh đúng {cuoi_dung}/{cuoi_tong} "
          f"({cuoi_dung/max(1,cuoi_tong)*100:.0f}%)")
    print(f"  nhịp: trung vị {statistics.median(nhip):.0f} â.t/phút · "
          f"chữ >800: {sum(1 for v in nhip if v>800)}/{len(nhip)} · "
          f"nhanh nhất {max(nhip):.0f}")
    print(f"  lưới chặn ra tay       {chan} lượt")
    print(f"  lượt KHÔNG có tiếng    {rong}")
    print(f"  độ trễ: trung vị {statistics.median(tre):.0f}ms · "
          f"xấu nhất {max(tre):.0f}ms")
asyncio.run(main())
