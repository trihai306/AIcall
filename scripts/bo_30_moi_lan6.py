"""30 luot tu van MOI, nham 12 giay, o cau hinh CHOT sau tat ca ban va.

Cham diem theo TU voi autojunk=False (difflib mac dinh bo qua ky tu hay gap khi
chuoi >= 200 ky tu - tung cham mot cau sai dung mot chu thanh 62,7%).
Quy viet tat ve mot dang truoc khi so: audio doc "ve be banh" ma STT viet
"vpbank" la STT nghe DUNG.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, wave
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\30 BAN MOI 12s - CHOT")

CAU=[
"Dạ về gói vay mua xe thì bên em cho vay tối đa tám mươi phần trăm giá trị xe, thời hạn lên tới bảy năm, lãi suất ưu đãi tám phẩy năm phần trăm trong năm đầu, và anh chị được nhận xe ngay sau khi hoàn tất thủ tục đăng ký biển số ạ.",
"Dạ nếu anh chị đang có khoản vay ở ngân hàng khác với lãi suất cao thì bên em có sản phẩm chuyển khoản nợ về, anh chị được hưởng lãi suất thấp hơn khoảng hai phần trăm và không phải trả thêm bất kỳ khoản phí thu xếp nào cả ạ.",
"Dạ tài khoản trả lương của anh chị mở tại bên em thì được miễn toàn bộ phí duy trì, miễn phí rút tiền tại mọi cây tự động trên cả nước, và đặc biệt là được cấp hạn mức thấu chi bằng ba tháng lương mà không cần thế chấp gì ạ.",
"Dạ điểm tín dụng của anh chị được tính từ lịch sử trả nợ, số lượng khoản vay đang có, và mức độ sử dụng hạn mức thẻ, nên nếu anh chị luôn trả đúng hạn và không dùng quá bảy mươi phần trăm hạn mức thì điểm sẽ rất tốt ạ.",
"Dạ em xin phép nói rõ về cách tính lãi để anh chị dễ theo dõi, tháng đầu anh chị trả lãi trên toàn bộ số vay, sang tháng thứ hai thì lãi chỉ tính trên phần gốc còn lại, nên số tiền phải trả giảm dần theo từng tháng ạ.",
"Dạ hồ sơ của anh chị cần công chứng bản sao giấy tờ tùy thân, còn sao kê lương thì bên em tự tra được trên hệ thống nếu anh chị nhận lương qua tài khoản bên em, đỡ được một lần đi lại và tiết kiệm khá nhiều thời gian ạ.",
"Dạ về bảo hiểm nhân thọ đi kèm khoản vay thì đây là sản phẩm tự nguyện, phí khoảng không phẩy tám phần trăm số tiền vay mỗi năm, và quyền lợi là công ty bảo hiểm sẽ trả nốt phần dư nợ nếu người vay gặp rủi ro ngoài ý muốn ạ.",
"Dạ trường hợp anh chị muốn vay ngoại tệ để thanh toán hàng nhập khẩu thì bên em hỗ trợ được, tuy nhiên anh chị cần chứng minh nguồn thu ngoại tệ để trả nợ, hoặc chấp nhận rủi ro tỷ giá khi mua ngoại tệ tại thời điểm đến hạn ạ.",
"Dạ gói vay dành cho sinh viên thì cần có người bảo lãnh là phụ huynh, hạn mức tối đa năm mươi triệu mỗi năm học, lãi suất ưu đãi năm phẩy năm phần trăm, và được ân hạn trả gốc cho tới sau khi tốt nghiệp mười hai tháng ạ.",
"Dạ em vừa kiểm tra thì thấy căn nhà anh chị định mua đã có sổ hồng riêng và không nằm trong diện tranh chấp, nên hồ sơ thế chấp sẽ khá thuận lợi, bên em chỉ cần thêm hợp đồng mua bán có công chứng là xử lý được ngay ạ.",
"Dạ về việc rút tiền từ thẻ tín dụng thì em khuyên anh chị nên tránh, vì khoản đó bị tính lãi ngay từ ngày rút chứ không được miễn lãi bốn mươi lăm ngày như khi quẹt thẻ mua hàng, cộng thêm phí rút bằng bốn phần trăm số tiền ạ.",
"Dạ nếu anh chị đồng ý thì em gửi luôn đường dẫn xác thực điện tử, anh chị chỉ cần chụp hai mặt giấy tờ và quay một đoạn ngắn theo hướng dẫn trên màn hình, hệ thống tự đối chiếu trong vòng ba phút là xong bước định danh ạ.",
"Dạ bên em có chương trình giới thiệu khách hàng, anh chị giới thiệu người thân vay thành công thì cả hai bên đều được tặng một khoản tiền vào tài khoản, và người được giới thiệu còn được giảm thêm không phẩy ba phần trăm lãi suất năm đầu ạ.",
"Dạ về thời hạn giải ngân thì với khoản vay tín chấp bên em xử lý trong hai ngày làm việc, còn vay thế chấp thì cần thêm thời gian định giá tài sản nên thường mất từ năm đến bảy ngày kể từ khi nhận đủ giấy tờ ạ.",
"Dạ em hiểu là lãi suất bên em chưa phải thấp nhất thị trường, nhưng bù lại anh chị không mất phí thu xếp, không phí thẩm định, không phí bảo hiểm bắt buộc, nên tính tổng chi phí cả kỳ vay thì thường lại rẻ hơn nhiều nơi khác ạ.",
"Dạ trường hợp anh chị trả chậm thì hệ thống tính lãi quá hạn bằng một trăm năm mươi phần trăm lãi suất trong hợp đồng, áp trên phần tiền chậm trả, nên anh chị cố gắng thu xếp đúng ngày hoặc gọi cho em trước để em hỗ trợ ạ.",
"Dạ với khoản vay kinh doanh thì bên em cần thêm báo cáo doanh thu sáu tháng và hợp đồng với đối tác nếu có, mục đích là để xác định dòng tiền của anh chị đủ trả nợ, chứ không phải để gây khó khăn gì cho anh chị đâu ạ.",
"Dạ anh chị có thể chọn ngày trả nợ hàng tháng theo lịch nhận lương của mình, bên em cho phép đặt vào ngày mùng năm, ngày mười lăm hoặc ngày hai mươi lăm, và đổi được một lần trong suốt thời gian vay nếu công việc thay đổi ạ.",
"Dạ sổ tiết kiệm của anh chị vẫn có thể dùng làm tài sản bảo đảm mà không cần tất toán trước hạn, bên em cho vay tới chín mươi lăm phần trăm giá trị sổ, nên anh chị vừa giữ được lãi tiền gửi vừa có tiền dùng ngay ạ.",
"Dạ về ứng dụng ngân hàng số thì anh chị tra được dư nợ, lịch trả nợ, và cả bảng tính lãi chi tiết từng tháng, ngoài ra còn đặt được nhắc nhở trước ngày đến hạn ba ngày để tránh trường hợp quên mất mà phát sinh lãi quá hạn ạ.",
"Dạ em xin phép xác nhận lại con số để anh chị nắm, anh chị vay hai trăm triệu đồng trong sáu mươi tháng, lãi suất bảy phẩy chín phần trăm một năm, tháng đầu trả khoảng bốn triệu sáu, và các tháng sau giảm dần theo dư nợ ạ.",
"Dạ nếu anh chị chưa quyết định ngay thì hoàn toàn không sao, em xin phép gửi bảng so sánh ba gói vay qua tin nhắn để anh chị xem cùng gia đình, rồi cuối tuần em gọi lại xem anh chị chọn gói nào cho phù hợp nhất ạ.",
"Dạ về hồ sơ đã nộp thì em thấy còn thiếu giấy xác nhận tình trạng hôn nhân, anh chị xin ở phường nơi đăng ký thường trú, thường lấy được trong ngày, và chụp gửi qua cho em là em bổ sung vào hệ thống ngay lập tức ạ.",
"Dạ bên em vừa nhận được phê duyệt cho hồ sơ của anh chị với hạn mức đúng như đề nghị ban đầu, em sẽ gửi hợp đồng qua thư điện tử trong hôm nay, anh chị đọc kỹ phần lãi suất và phí trước khi ký giúp em ạ.",
"Dạ em rất xin lỗi về trải nghiệm vừa rồi của anh chị ở phòng giao dịch, em đã ghi nhận và chuyển cho bộ phận phụ trách, đồng thời em xin phép hỗ trợ trực tiếp anh chị từ giờ để không phải chờ đợi thêm lần nào nữa ạ.",
"Dạ khoản vay này không có phí trả nợ trước hạn nếu anh chị tất toán sau tháng thứ hai mươi bốn, còn trước thời điểm đó thì phí bằng hai phần trăm trên dư nợ gốc còn lại tại đúng ngày anh chị mang tiền đến tất toán ạ.",
"Dạ anh chị lưu ý là hạn mức thẻ tín dụng và hạn mức vay tín chấp được xét chung trên tổng thu nhập, nên nếu anh chị mở thẻ với hạn mức cao thì phần vay tín chấp sẽ bị giảm tương ứng, em nói trước để anh chị cân nhắc ạ.",
"Dạ về việc thay đổi thông tin liên hệ thì anh chị làm ngay trên ứng dụng, vào phần thông tin cá nhân rồi cập nhật số điện thoại mới, hệ thống gửi mã xác thực về số cũ nên anh chị cần còn dùng được số đó ạ.",
"Dạ em cảm ơn anh chị đã tin tưởng chọn bên em, sau khi giải ngân thì em vẫn là người phụ trách hồ sơ của anh chị, nên có bất cứ vướng mắc gì trong suốt thời gian vay anh chị cứ gọi thẳng số này cho em ạ.",
"Dạ vậy em xin phép kết thúc cuộc gọi tại đây, em sẽ gửi tin nhắn tóm tắt toàn bộ nội dung mình vừa trao đổi để anh chị lưu lại đối chiếu, chúc anh chị buổi chiều làm việc thật hiệu quả và hẹn gặp lại anh chị ạ.",
]

def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=900) as r:
        j=json.load(r)
    return (None,j) if j.get("error") else (base64.b64decode(j["audio"]),j)
def nghe(wav):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(wav); w("\r\n")
    for k,v in (("language","vi"),("response_format","json"),("prompt",MOI)):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),
        headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=900) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def do(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); c=[];n=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op=="replace": c.append((" ".join(A[i1:i2])," ".join(B[j1:j2]))); n+=max(i2-i1,j2-j1)
        elif op=="delete": c.append((" ".join(A[i1:i2]),"∅")); n+=i2-i1
        elif op=="insert": c.append(("∅"," ".join(B[j1:j2]))); n+=j2-j1
    return n/max(1,len(A)), c, len(A)
RA.mkdir(parents=True, exist_ok=True)
print(f"{'#':>3}{'giây':>6}{'mảnh':>5}{'â.tiết/ph':>10}{'sai':>7}  lệch ở đâu")
print("-"*92)
e=[];g_=[];nh=[];dong=[]
for i,c in enumerate(CAU,1):
    wav,j=sinh(c)
    if not wav: print(f"{i:>3}  LỖI {j.get('error','')[:56]}"); continue
    mong=normalize_for_tts(c); ra=nghe(wav); x,ds,tong=do(mong,ra); e.append(x)
    g=j["duration_ms"]/1000; g_.append(g); nh.append(tong/g*60)
    (RA/f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:44].strip()}.wav").write_bytes(wav)
    print(f"{i:>3}{g:6.2f}{j['so_manh']:>5}{tong/g*60:10.0f}{x*100:6.1f}% {'✓' if x<=0.05 else '✗'} "
          + (", ".join(f"{a}→{b}" for a,b in ds)[:50] or "—"))
    dong.append(f"{i:02d}. {g:.1f}s  {x*100:.0f}% tu sai\n    VIET   : {c}\n    NGHE RA: {ra}\n"
                + ("    LECH   : "+", ".join(f"{a} -> {b}" for a,b in ds)+"\n" if ds else ""))
print("-"*92)
print(f"ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu   từ sai trung bình {sum(e)/len(e)*100:.1f}%   "
      f"sạch tuyệt đối {sum(1 for x in e if x==0)}/{len(e)}")
print(f"dài {min(g_):.1f}-{max(g_):.1f}s, trung bình {sum(g_)/len(g_):.1f}s   nhịp {sum(nh)/len(nh):.0f} âm tiết/phút")
(RA/"GHI CHU.txt").write_text(
    f"""30 BAN VOICE MOI - 13/08/2026, cau hinh CHOT
=============================================

Noi dung MOI hoan toan, khong trung hai bo truoc. File 24kHz, va nhip nay DUNG
BANG nhip khach nghe (he so thoai = 1.00).

KET QUA: doc dung {sum(x<=0.05 for x in e)}/{len(e)} cau   tu sai trung binh {sum(e)/len(e)*100:.1f}%
         sach tuyet doi (0 tu sai) {sum(1 for x in e if x==0)}/{len(e)}
         dai {min(g_):.1f}-{max(g_):.1f} giay, trung binh {sum(g_)/len(g_):.1f}s
         nhip {sum(nh)/len(nh):.0f} am tiet/phut

CAU HINH DANG CHAY
------------------
  toc giong          0.98
  he so toc thoai    1.00  (nen Test giong = Nhan tin = Cuoc goi, mot nhip duy nhat)
  nguong tach phay   4 tu moi ve
  chuan hoa          "Da ..." -> "da, ..."  (chi them DAU, khong them chu nao)
  dau ket cau        tu them dau cham khi manh cuoi thieu

DA SUA GI TU LAN 4 DEN GIO
--------------------------
1. Nhip nghe thu = nhip cuoc goi. Truoc day nghe o 24kHz ra 283 am tiet/phut con
   cuoc goi doc 347 - duyet giong o 24kHz la duyet nham.
2. He so toc thoai 1.28 -> 1.00. No sinh ra de chong "dinh chu" tren kenh 8kHz
   nhung lai lam doc NHANH hon, va do ra thi gay dung cai no dinh chong.
3. Ten ngan hang viet tat: VPBank -> "ve be banh" (truoc sai 10/10 lan).
4. Ngat o dau phay, nhung CHI khi ca hai ve tu 4 tu tro len - ve 3 tu tach ra
   nghe giat cuc (ca "Em la Duong," ban bao o Lan 5).
5. Cum "......" tu dong gop lai con "." - 6 dau cham chiem ngan sach thoi luong
   ma khong co am nao.
6. Am cuoi tat lim: manh thieu dau ket cau thi F5 cat phut, nay tu them dau cham.
7. Hat giong CO DINH: cung chu + cung giong + cung toc luon ra dung mot file.

CHUA SUA - noi ro de khong hieu nham
------------------------------------
Am tiet CUOI phat ngon con yeu hon nguoi that (ty le do to 0,73 so voi 0,98).
Da thu va LOAI ba cach: noi ngan sach thoi luong (0.85 da la muc dung), bu do to
cho chu cuoi (+12 dB - may nghe dung 1/8 truoc va van 1/8 sau), doi doan mau
(6 clip, ngang nhau tren cau that). Ba nut cua mo hinh (nfe 16, cfg 2.0,
sway -1) deu da o muc tot nhat. Trong kich ban that don roi vao chu "a" cuoi cau
chu khong vao tu mang noi dung.

LUU Y KHI DOC BANG DOI CHIEU
----------------------------
May nghe khong phai tai nguoi. Loi con lai gan het la lech THANH DIEU o tu chuc
nang (chi -> chi, lai -> lai, thi -> ky) - cho PhoWhisper von yeu. Nghe truc tiep
de phan dinh.

""" + "\n".join(dong), encoding="utf-8")
print(f"\nFile: {RA}")
