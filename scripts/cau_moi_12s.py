"""30 luot tu van MOI, nham 12 giay/cau, o cau hinh DA SUA.

24kHz va nhip nay DUNG BANG nhip cuoc goi (he so thoai = 1.00), nen nghe truc
tiep la duyet duoc. Noi dung moi hoan toan, khong trung bo cu.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\30 LUOT MOI 12s - DA SUA")

CAU=[
"Dạ em xin phép giới thiệu qua về gói tiết kiệm linh hoạt bên em, anh chị gửi từ mười triệu đồng trở lên là được hưởng lãi suất bậc thang, kỳ hạn càng dài lãi càng cao, và điểm khác biệt là anh chị vẫn rút được một phần tiền gốc bất cứ lúc nào mà phần còn lại không bị mất lãi ạ.",
"Dạ về thẻ tín dụng thì hạn mức của anh chị sẽ được cấp dựa trên thu nhập hàng tháng, thông thường bằng ba đến năm lần lương, anh chị được miễn lãi tối đa bốn mươi lăm ngày, và nếu chi tiêu đạt một trăm triệu một năm thì bên em miễn luôn phí thường niên cho những năm sau ạ.",
"Dạ đối với khách hàng vay mua nhà lần đầu thì bên em đang có gói ưu đãi riêng, lãi suất cố định sáu phẩy chín phần trăm trong hai mươi bốn tháng đầu, cho vay tối đa tám mươi phần trăm giá trị căn hộ, thời hạn tới hai mươi lăm năm và được ân hạn gốc mười hai tháng ạ.",
"Dạ em hiểu là anh chị đang lo về việc lãi suất thả nổi sau thời gian ưu đãi, thực tế thì biên độ bên em cam kết ghi rõ trong hợp đồng là ba phẩy năm phần trăm, không phải muốn điều chỉnh thế nào cũng được, nên anh chị hoàn toàn tính trước được khoản trả hàng tháng ạ.",
"Dạ trường hợp anh chị đang kinh doanh tự do và không có hợp đồng lao động, bên em vẫn có sản phẩm vay riêng, chỉ cần giấy phép đăng ký kinh doanh còn hiệu lực cùng sao kê tài khoản sáu tháng gần nhất để chứng minh dòng tiền ra vào là bên em thẩm định được ạ.",
"Dạ về quy trình thì sau khi anh chị đồng ý, em sẽ mở hồ sơ ngay trên hệ thống rồi gửi một đường dẫn qua tin nhắn, anh chị chỉ cần chụp giấy tờ tải lên, ký xác nhận điện tử, và toàn bộ quá trình này không cần ra chi nhánh cũng không mất bất kỳ khoản phí nào ạ.",
"Dạ bảo hiểm khoản vay là tự nguyện chứ không bắt buộc, phí khoảng không phẩy sáu phần trăm trên số tiền vay mỗi năm, ý nghĩa của nó là nếu không may anh chị gặp rủi ro thì công ty bảo hiểm thanh toán phần dư nợ còn lại, gia đình không phải gánh khoản nợ đó ạ.",
"Dạ nếu anh chị muốn tất toán khoản vay sớm thì hoàn toàn được, phí phạt tính trên số dư nợ gốc tại thời điểm tất toán chứ không phải trên tổng số tiền vay ban đầu, và từ năm thứ ba trở đi thì bên em miễn hẳn khoản phí này cho anh chị luôn ạ.",
"Dạ về lịch trả nợ thì hệ thống tự động trích từ tài khoản của anh chị vào ngày mùng năm hàng tháng, trước đó ba ngày bên em nhắn tin nhắc, và nếu tháng nào anh chị cần đổi ngày trích thì chỉ cần báo trước một tuần là bên em điều chỉnh được ạ.",
"Dạ hiện tại chương trình này chỉ áp dụng tới hết ngày ba mươi mốt tháng tám, sau mốc đó lãi suất quay về biểu thông thường là chín phẩy năm phần trăm một năm, chênh lệch khoảng một phẩy sáu phần trăm, tính ra trên khoản vay năm trăm triệu là hơn tám triệu một năm ạ.",
"Dạ em xin phép xác nhận lại thông tin để mở hồ sơ, anh tên là Nguyễn Văn Minh, sinh ngày mười hai tháng tư năm một nghìn chín trăm tám mươi lăm, số căn cước công dân là không ba tám không bảy hai, hiện đang cư trú tại quận Hai Bà Trưng, thành phố Hà Nội ạ.",
"Dạ ngoài khoản vay thì anh chị còn được mở miễn phí một tài khoản thanh toán kèm thẻ ghi nợ quốc tế, miễn phí chuyển khoản trong và ngoài hệ thống không giới hạn số lần, cùng với ứng dụng ngân hàng số để tra cứu dư nợ và lịch trả nợ mọi lúc mọi nơi ạ.",
"Dạ em xin lỗi vì gọi vào giờ này, nếu bây giờ anh chị đang bận thì cho em xin một khung giờ thuận tiện hơn, buổi trưa hay cuối giờ chiều đều được, em sẽ chủ động gọi lại đúng khung giờ đó để tư vấn kỹ hơn, tránh làm mất thời gian của anh chị ạ.",
"Dạ điều kiện để xét duyệt gói này là anh chị trong độ tuổi từ hai mươi hai đến sáu mươi, có hợp đồng lao động còn hiệu lực từ mười hai tháng trở lên, nhận lương qua tài khoản ngân hàng, và không có nợ nhóm hai trở lên trên hệ thống thông tin tín dụng quốc gia ạ.",
"Dạ nếu trong quá trình trả nợ mà anh chị gặp khó khăn về tài chính thì làm ơn liên hệ với bên em sớm để được xem xét cơ cấu lại thời hạn trả nợ, đừng để phát sinh nợ quá hạn, vì lúc đó lịch sử tín dụng bị ảnh hưởng và sau này vay ở đâu cũng khó ạ.",
"Dạ số tiền anh chị phải trả hàng tháng gồm hai phần, phần gốc chia đều cho số tháng vay và phần lãi tính trên dư nợ giảm dần, nên những tháng đầu trả nhiều hơn còn về sau giảm dần, chứ không phải cố định một mức như nhiều nơi khác vẫn quảng cáo ạ.",
"Dạ về hồ sơ thì ngoài giấy tờ tùy thân, anh chị chuẩn bị thêm hợp đồng lao động bản sao, sao kê lương ba tháng gần nhất có xác nhận của ngân hàng, và nếu có thêm giấy tờ chứng minh thu nhập phụ như hợp đồng cho thuê nhà thì hạn mức sẽ được xét cao hơn ạ.",
"Dạ em vừa tra trên hệ thống thì thấy anh chị đã là khách hàng của bên em từ năm hai nghìn hai mươi và chưa từng phát sinh nợ quá hạn lần nào, nên anh chị thuộc diện khách hàng thân thiết, hồ sơ sẽ được ưu tiên xử lý và thủ tục cũng đơn giản hơn rất nhiều ạ.",
"Dạ nếu anh chị so sánh với bên VPBank hay TPBank thì em nghĩ điểm mạnh của bên em không nằm ở con số lãi suất, mà ở chỗ giải ngân nhanh trong hai ngày làm việc và không phát sinh bất kỳ khoản phí ẩn nào, mọi khoản đều ghi rõ trong bảng phí công khai ạ.",
"Dạ vậy em chốt lại để anh chị nắm, anh chị vay một trăm năm mươi triệu đồng trong bốn mươi tám tháng, lãi suất bảy phẩy chín phần trăm một năm, trả hàng tháng khoảng ba triệu tám trăm nghìn đồng, tổng lãi phải trả cho cả kỳ là khoảng hai mươi ba triệu đồng ạ.",
"Dạ trường hợp anh chị muốn vay số tiền lớn hơn mức tín chấp cho phép thì bên em tư vấn chuyển sang hình thức thế chấp, khi đó hạn mức phụ thuộc vào giá trị định giá tài sản, và lãi suất cũng thấp hơn khoảng hai phần trăm so với vay tín chấp thông thường ạ.",
"Dạ hồ sơ của anh chị đã được phê duyệt rồi, bên em sẽ gửi hợp đồng tín dụng qua thư điện tử trong hôm nay, anh chị đọc kỹ toàn bộ điều khoản, đặc biệt là phần lãi suất và phí phạt, nếu đồng ý thì ký điện tử và tiền sẽ về tài khoản trong vòng hai giờ ạ.",
"Dạ em xin phép hỏi thêm để tư vấn cho chính xác, hiện tại thu nhập hàng tháng của anh chị khoảng bao nhiêu, có bao gồm thưởng hay hoa hồng không, và anh chị đang có khoản vay hoặc thẻ tín dụng nào đang dư nợ tại ngân hàng khác hay không ạ.",
"Dạ về gói tiết kiệm online thì lãi suất cao hơn gửi tại quầy không phẩy hai phần trăm, kỳ hạn sáu tháng là bốn phẩy tám, mười hai tháng là năm phẩy hai, và anh chị có thể tất toán trước hạn ngay trên ứng dụng mà vẫn được hưởng lãi không kỳ hạn cho phần đã gửi ạ.",
"Dạ em hiểu là anh chị cần thời gian bàn với gia đình, vậy em xin phép gửi toàn bộ thông tin gồm bảng tính lãi chi tiết và danh mục giấy tờ qua tin nhắn, anh chị xem lúc nào thuận tiện, và cuối tuần này em gọi lại một lần xem anh chị quyết định thế nào ạ.",
"Dạ thời gian xử lý trung bình của bên em là hai ngày làm việc kể từ lúc nhận đủ giấy tờ, nhưng nếu anh chị nộp hồ sơ trước mười giờ sáng thì phần lớn trường hợp là có kết quả ngay trong ngày, và giải ngân luôn vào sáng hôm sau ạ.",
"Dạ về việc bảo mật thông tin thì anh chị hoàn toàn yên tâm, mọi dữ liệu cá nhân anh chị cung cấp đều được mã hóa và lưu trữ theo quy định của Ngân hàng Nhà nước, chỉ dùng cho mục đích thẩm định khoản vay này và không chia sẻ cho bất kỳ bên thứ ba nào ạ.",
"Dạ nếu anh chị đã có thẻ tín dụng của ngân hàng khác thì bên em có chương trình chuyển đổi dư nợ, anh chị chuyển toàn bộ dư nợ hiện tại sang bên em và được hưởng lãi suất không phần trăm trong sáu tháng đầu, chỉ mất phí chuyển đổi một lần là ba phần trăm ạ.",
"Dạ em cảm ơn anh chị đã dành thời gian nghe em trình bày, mọi thắc mắc sau này anh chị cứ gọi thẳng vào số máy này gặp em, em tên Dương, chuyên viên tư vấn tín dụng, làm việc từ tám giờ sáng đến năm giờ chiều các ngày trong tuần ạ.",
"Dạ vậy em xin phép kết thúc cuộc gọi tại đây, em sẽ gửi tin nhắn xác nhận toàn bộ nội dung mình vừa trao đổi ngay bây giờ để anh chị lưu lại đối chiếu, chúc anh chị một ngày làm việc thật hiệu quả và hẹn gặp lại anh chị ạ.",
]

def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=900) as r:
        j=json.load(r)
    return (None,j) if j.get("error") else (j["audio"],j)
def nghe(b64):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
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
print("-"*96)
e=[];nh=[];g_=[];dong=[]
for i,c in enumerate(CAU,1):
    b64,j=sinh(c)
    if not b64: print(f"{i:>3}  LỖI {j.get('error','')[:60]}"); continue
    mong=normalize_for_tts(c); ra=nghe(b64); x,ds,tong=do(mong,ra); e.append(x)
    g=j["duration_ms"]/1000; g_.append(g); nh.append(tong/g*60)
    (RA/f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:46].strip()}.wav").write_bytes(base64.b64decode(b64))
    print(f"{i:>3}{g:6.2f}{j['so_manh']:>5}{tong/g*60:10.0f}{x*100:6.1f}% {'✓' if x<=0.05 else '✗'} "
          + (", ".join(f"{a}→{b}" for a,b in ds)[:56] or "—"))
    dong.append(f"{i:02d}. {g:.1f}s  {x*100:.0f}% tu sai\n    VIET   : {c}\n    NGHE RA: {ra}\n"
                + ("    LECH   : " + ", ".join(f"{a} -> {b}" for a,b in ds) + "\n" if ds else ""))
print("-"*96)
print(f"ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu   từ sai trung bình {sum(e)/len(e)*100:.1f}%")
print(f"dài {min(g_):.1f}-{max(g_):.1f}s, trung bình {sum(g_)/len(g_):.1f}s   "
      f"nhịp trung bình {sum(nh)/len(nh):.0f} âm tiết/phút")
(RA/"BAN DOI CHIEU.txt").write_text(
    f"""30 LUOT TU VAN MOI - 13/08/2026, giong giong_heu, toc 0.90, he so thoai 1.00
=============================================================================

Noi dung MOI hoan toan, khong trung bo truoc. File 24kHz, va nhip nay DUNG BANG
nhip khach nghe qua dien thoai (he so thoai da ve 1.00), nen nghe truc tiep la
duyet duoc.

KET QUA: doc dung {sum(x<=0.05 for x in e)}/{len(e)} cau, tu sai trung binh {sum(e)/len(e)*100:.1f}%
Dai {min(g_):.1f}-{max(g_):.1f} giay, trung binh {sum(g_)/len(g_):.1f}s. Nhip {sum(nh)/len(nh):.0f} am tiet/phut.

DA SUA GI TRONG BO NAY (so voi cac bo truoc)
--------------------------------------------
1. Nhip nghe thu = nhip cuoc goi. Truoc day nghe o 24kHz ra 283 am tiet/phut con
   cuoc goi doc 347 - duyet giong o 24kHz la duyet nham.
2. He so toc thoai 1.28 -> 1.00. He so nay sinh ra de chong "dinh chu" tren kenh
   8kHz nhung lai lam doc NHANH hon, va do ra thi no gay dung cai no dinh chong:
   cau dai 23/30 o 1.28, len 30/30 o 1.00.
3. "Da" dau luot -> "Da vang,". Can CA hai: dau phay mot minh chi duoc 8/12,
   "vang" mot minh 10/12 (va chinh "vang" rung duoi thanh "van"), ca hai thi 12/12.

LUU Y KHI DOC BANG DOI CHIEU
----------------------------
May nghe khong phai tai nguoi. Cac loi con lai gan het la lech THANH DIEU o tu
chuc nang (chi -> chi, lai -> lai, a -> han) - cho PhoWhisper von yeu, rat co the
tai nguoi van nghe ra dung. Nghe truc tiep de phan dinh.

""" + "\n".join(dong), encoding="utf-8")
print(f"\nFile: {RA}")
