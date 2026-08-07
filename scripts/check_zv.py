import io, os, sys, unicodedata, re, requests, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
STT = "http://localhost:8178/inference"
S = requests.Session()
CAU = [
 "dạ em chào anh chị",
 "dạ lãi suất vay tín chấp hiện tại",
 "dạ được ạ, em xin phép tư vấn thêm",
 "vâng, để em kiểm tra lại thông tin",
 "dạ anh chị cần chuẩn bị chứng minh nhân dân",
 "dạ lãi suất vay tín chấp hiện tại là sáu phẩy năm phần trăm",
]
def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"[^\w\s]", "", s).strip()
def cer(r, h):
    r, h = norm(r), norm(h)
    if not r: return 0.0
    d=[[0]*(len(h)+1) for _ in range(len(r)+1)]
    for i in range(len(r)+1): d[i][0]=i
    for j in range(len(h)+1): d[0][j]=j
    for i in range(1,len(r)+1):
        for j in range(1,len(h)+1):
            d[i][j]=min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(r[i-1]!=h[j-1]))
    return 100.0*d[len(r)][len(h)]/len(r)

D = sys.argv[1] if len(sys.argv)>1 else r"C:\duan\chat-ai\logs\zv_out6"
print("== %s ==" % D.rsplit(chr(92),1)[-1]); print("%-6s %8s %7s   %s" % ("file","giây","CER","nghe ra"))
tot=[]
for i, goc in enumerate(CAU):
    p = os.path.join(D, "c%d.wav" % i)
    if not os.path.exists(p): print("  c%d.wav THIEU" % i); continue
    info = sf.info(p)
    wb = io.open(p,"rb").read()
    r = S.post(STT, files={"file":("a.wav",wb,"audio/wav")}, data={"language":"vi","response_format":"json"}, timeout=180)
    try: hyp = r.json().get("text","")
    except Exception: hyp = r.text[:40]
    c = cer(goc, hyp); tot.append(c)
    print("c%d.wav %7.2fs %6.1f%%   %r" % (i, info.duration, c, hyp.strip()[:58]))
if tot: print("\n  CER trung binh: %.1f%%" % (sum(tot)/len(tot)))
