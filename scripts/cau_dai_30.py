"""30 cau DAI 10-12s, sinh o DUNG nhip cuoc goi (0.90 x 1.28), full 24kHz.

Full bang thong de nghe ro chinh cho hong; nhip cuoc gooi de loi lo ra dung nhu
that. Cham diem cong bang voi viet tat.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
TOC="http://127.0.0.1:8100/api/voices/giong_heu/speed"; GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\CAU DAI 10-12s 13-08")

CAU=[
"Dạ hiện tại bên em đang triển khai gói vay tín chấp dành cho khách hàng có thu nhập ổn định từ mười lăm triệu đồng một tháng trở lên, với hạn mức tối đa lên đến năm trăm triệu đồng và thời gian vay linh hoạt từ mười hai đến sáu mươi tháng ạ.",
"Dạ về hồ sơ thì anh chị chỉ cần chuẩn bị chứng minh nhân dân hoặc căn cước công dân còn hiệu lực, sổ hộ khẩu hoặc giấy tạm trú, và sao kê tài khoản lương ba tháng gần nhất là bên em có thể tiếp nhận và xét duyệt được rồi ạ.",
"Dạ lãi suất áp dụng cho gói vay này là bảy phẩy chín phần trăm một năm trong mười hai tháng đầu tiên, sau đó sẽ điều chỉnh theo lãi suất tiết kiệm mười ba tháng cộng biên độ ba phẩy năm phần trăm ạ.",
"Dạ nếu anh chị vay tám mươi triệu đồng trong thời hạn ba mươi sáu tháng thì số tiền phải trả hàng tháng sẽ vào khoảng hai triệu bảy trăm nghìn đồng, bao gồm cả gốc và lãi tính trên dư nợ giảm dần ạ.",
"Dạ đối với gói vay thế chấp sổ đỏ thì bên em cho vay tối đa bằng bảy mươi phần trăm giá trị định giá của tài sản, thời hạn vay lên đến hai mươi năm, và anh chị được ân hạn gốc trong mười hai tháng đầu ạ.",
"Dạ thời gian xử lý hồ sơ trung bình từ hai đến ba ngày làm việc kể từ khi bên em nhận đủ giấy tờ, và ngay sau khi hồ sơ được phê duyệt thì tiền sẽ được giải ngân trực tiếp vào tài khoản của anh chị ạ.",
"Dạ anh chị hoàn toàn có thể trả nợ trước hạn bất cứ lúc nào, tuy nhiên nếu trả trước trong vòng mười hai tháng đầu thì sẽ phát sinh phí phạt bằng hai phần trăm trên số tiền trả trước ạ.",
"Dạ trường hợp anh chị đang có khoản vay tại ngân hàng khác thì bên em vẫn xem xét được, miễn là lịch sử tín dụng không có nợ quá hạn và tổng nghĩa vụ trả nợ hàng tháng không vượt quá sáu mươi phần trăm thu nhập ạ.",
"Dạ ngoài gói vay tín chấp thì bên em còn có sản phẩm thẻ tín dụng với hạn mức lên đến ba trăm triệu đồng, miễn lãi tối đa bốn mươi lăm ngày và miễn phí thường niên trong năm đầu tiên ạ.",
"Dạ anh chị có thể so sánh thêm với các ngân hàng khác như VPBank, TPBank hay MBBank, nhưng em tin là mức lãi suất và thời gian giải ngân bên em đang là một trong những mức tốt nhất trên thị trường hiện nay ạ.",
"Dạ để em tóm tắt lại cho anh chị dễ theo dõi, gói vay này có hạn mức năm trăm triệu, lãi suất bảy phẩy chín phần trăm, thời hạn tối đa sáu mươi tháng, và không cần tài sản đảm bảo ạ.",
"Dạ em hiểu là anh chị đang cần cân nhắc thêm, vậy em xin phép gửi thông tin chi tiết qua tin nhắn để anh chị tham khảo, và em sẽ gọi lại vào đầu tuần sau xem anh chị đã quyết định thế nào ạ.",
"Dạ nếu anh chị đồng ý thì ngay bây giờ em sẽ mở hồ sơ trên hệ thống, sau đó gửi đường link để anh chị bổ sung giấy tờ trực tuyến, không cần phải ra chi nhánh và cũng không mất thêm khoản phí nào ạ.",
"Dạ khoản vay này được bảo hiểm khoản vay đi kèm, nghĩa là trong trường hợp không may xảy ra rủi ro thì công ty bảo hiểm sẽ đứng ra thanh toán phần dư nợ còn lại thay cho gia đình anh chị ạ.",
"Dạ về điều kiện thì anh chị cần trong độ tuổi từ hai mươi hai đến sáu mươi tuổi, có hợp đồng lao động từ mười hai tháng trở lên, và đang nhận lương qua tài khoản ngân hàng chứ không phải nhận tiền mặt ạ.",
"Dạ em xin phép xác nhận lại thông tin, anh tên là Nguyễn Văn Minh, sinh năm một nghìn chín trăm tám mươi lăm, hiện đang làm việc tại công ty trách nhiệm hữu hạn Thành Đạt với mức thu nhập hai mươi triệu một tháng ạ.",
"Dạ trong trường hợp anh chị muốn vay số tiền lớn hơn hạn mức tín chấp thì bên em có thể tư vấn chuyển sang hình thức vay thế chấp, khi đó hạn mức sẽ phụ thuộc vào giá trị tài sản mà anh chị đưa vào ạ.",
"Dạ phí trả nợ trước hạn được tính trên số tiền gốc còn lại tại thời điểm tất toán, chứ không phải trên tổng số tiền vay ban đầu, nên nếu anh chị đã trả được hơn một nửa thì khoản phí này sẽ rất nhỏ ạ.",
"Dạ nếu anh chị quan tâm đến việc gửi tiết kiệm thì hiện tại lãi suất kỳ hạn sáu tháng là bốn phẩy tám phần trăm, kỳ hạn mười hai tháng là năm phẩy hai phần trăm, và gửi online sẽ được cộng thêm không phẩy hai phần trăm ạ.",
"Dạ em xin lỗi vì đã làm phiền anh chị vào giờ này, nếu bây giờ không tiện thì anh chị cho em xin một khung giờ phù hợp hơn, em sẽ chủ động gọi lại đúng giờ đó để tư vấn kỹ hơn cho anh chị ạ.",
"Dạ khi hồ sơ được duyệt thì bên em sẽ gửi hợp đồng tín dụng qua thư điện tử để anh chị đọc kỹ trước, sau đó nếu đồng ý với toàn bộ điều khoản thì anh chị mới ký xác nhận và tiền được giải ngân ngay sau đó ạ.",
"Dạ về lịch trả nợ thì hệ thống sẽ tự động trích tiền từ tài khoản của anh chị vào ngày mùng năm hàng tháng, và trước đó ba ngày bên em sẽ gửi tin nhắn nhắc để anh chị chủ động chuẩn bị số dư ạ.",
"Dạ nếu trong quá trình vay mà anh chị gặp khó khăn về tài chính thì có thể liên hệ với bên em để được xem xét cơ cấu lại thời hạn trả nợ, chứ đừng để phát sinh nợ quá hạn vì sẽ ảnh hưởng đến lịch sử tín dụng ạ.",
"Dạ hiện tại chương trình ưu đãi này chỉ áp dụng đến hết ngày ba mươi mốt tháng tám, sau thời điểm đó thì mức lãi suất sẽ quay về biểu lãi suất thông thường là chín phẩy năm phần trăm một năm ạ.",
"Dạ ngoài ra anh chị còn được miễn phí phát hành thẻ ghi nợ quốc tế, miễn phí chuyển khoản trong và ngoài hệ thống, cùng với việc sử dụng ứng dụng ngân hàng số để quản lý khoản vay mọi lúc mọi nơi ạ.",
"Dạ để đảm bảo quyền lợi cho anh chị thì mọi thông tin cá nhân cung cấp cho bên em đều được bảo mật tuyệt đối theo quy định của Ngân hàng Nhà nước, và chỉ sử dụng cho mục đích thẩm định khoản vay này thôi ạ.",
"Dạ trường hợp anh chị là chủ hộ kinh doanh chứ không có hợp đồng lao động thì bên em vẫn có sản phẩm riêng, chỉ cần giấy phép kinh doanh và sao kê tài khoản sáu tháng gần nhất để chứng minh dòng tiền ạ.",
"Dạ em vừa kiểm tra trên hệ thống thì thấy anh chị đã là khách hàng của bên em từ năm hai nghìn hai mươi, nên anh chị sẽ được xét duyệt theo diện khách hàng thân thiết với thủ tục đơn giản hơn rất nhiều ạ.",
"Dạ vậy em chốt lại là anh chị sẽ vay một trăm năm mươi triệu đồng trong bốn mươi tám tháng, lãi suất bảy phẩy chín phần trăm, trả hàng tháng khoảng ba triệu tám trăm nghìn đồng, anh chị xác nhận giúp em nhé ạ.",
"Dạ em cảm ơn anh chị đã dành thời gian lắng nghe, mọi thắc mắc sau này anh chị cứ gọi trực tiếp vào số máy này gặp em, em tên Dương, chuyên viên tư vấn tín dụng, em luôn sẵn sàng hỗ trợ anh chị ạ.",
]

def dat_toc(v):
    req=urllib.request.Request(TOC,data=json.dumps({"speed":v}).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
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
    with urllib.request.urlopen(req,timeout=600) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def lech(a,b):
    A,B=chuan(a).split(),chuan(b).split(); mat=[];them=[]
    for op,i1,i2,j1,j2 in difflib.SequenceMatcher(None,A,B).get_opcodes():
        if op in ("delete","replace"): mat+=A[i1:i2]
        if op in ("insert","replace"): them+=B[j1:j2]
    return mat,them
def cer(a,b): return 1-difflib.SequenceMatcher(None,chuan(a),chuan(b)).ratio()
HE_SO=float(Path(r"C:\duan\chat-ai\models\tts\ref_voices\_he_so_thoai.txt").read_text().strip())
RA.mkdir(parents=True, exist_ok=True)
dat_toc(round(0.90*HE_SO,3))
try:
    print(f"nhịp cuộc gọi (tốc {round(0.90*HE_SO,3)})\n")
    print(f"{'#':>3}{'giây':>6}{'mảnh':>5}{'â.tiết/ph':>10}{'CER':>7}  10 chữ đầu")
    print("-"*88)
    e=[];nh=[];g_=[];hong=[]
    for i,c in enumerate(CAU,1):
        b64,j=sinh(c)
        if not b64: print(f"{i:>3}  LỖI {j.get('error','')[:60]}"); continue
        mong=normalize_for_tts(c); ra=nghe(b64); x=cer(mong,ra); e.append(x)
        g=j["duration_ms"]/1000; g_.append(g)
        a=len(chuan(mong).split())/g*60 if g else 0; nh.append(a)
        (RA/f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:46].strip()}.wav").write_bytes(base64.b64decode(b64))
        print(f"{i:>3}{g:6.2f}{j['so_manh']:>5}{a:10.0f}{x*100:6.1f}% {'✓' if x<=0.05 else '✗'} {' '.join(c.split()[:9])}")
        if x>0.05: hong.append((i,c,mong,ra))
    print("-"*88)
    print(f"ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu (CER ≤ 5%)   CER trung bình {sum(e)/len(e)*100:.1f}%")
    print(f"dài {min(g_):.1f}-{max(g_):.1f}s, trung bình {sum(g_)/len(g_):.1f}s   "
          f"nhịp {min(nh):.0f}-{max(nh):.0f}, trung bình {sum(nh)/len(nh):.0f} âm tiết/phút")
    for i,c,mong,ra in hong:
        m,t=lech(mong,ra)
        print(f"\n  {i}. nghe : {ra[:150]}")
        print(f"     mất={m[:12]}\n     thừa={t[:12]}")
finally:
    dat_toc(0.90); print(f"\nĐã trả tốc về 0.90. File: {RA}")
