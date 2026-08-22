"""No CHEP tai lieu hay DIEN DAT LAI? Do do trung chu giua cau tra loi va tai lieu RAG.

Thuoc do: ty le 5-gram cua cau tra loi CO MAT nguyen van trong tai lieu.
    ~0%   = tu dien dat hoan toan
    >40%  = chep nguyen doan
Kem: doan chep dai nhat (chuoi tu lien tiep dai nhat trung voi tai lieu).
"""
import asyncio, difflib, json, re, sys, unicodedata
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
WS="ws://127.0.0.1:8100/ws/call/new"
HOI=[("vay tín chấp","lãi suất vay tín chấp bao nhiêu"),
     ("vay tín chấp","anh vay được tối đa bao nhiêu"),
     ("vay tín chấp","cần giấy tờ gì không em"),
     ("vay tín chấp","bao lâu thì giải ngân"),
     ("vay mua nhà","lãi suất vay mua nhà thế nào"),
     ("vay mua nhà","vay được bao nhiêu phần trăm giá trị nhà"),
     ("thẻ tín dụng","hạn mức thẻ tín dụng bao nhiêu"),
     ("thẻ tín dụng","phí thường niên thế nào"),
     ("tiết kiệm","lãi suất gửi tiết kiệm bao nhiêu"),
     ("vay tín chấp","điều kiện vay là gì")]
async def hoi(sp,q):
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        await ws.send(json.dumps({"type":"text_soi","text":q,"turn_id":1}))
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=180))
            if m.get("type")=="turn_complete":
                return m.get("full_response",""), m.get("metrics",{}) or {}
def tu(s): return re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split()
def ng(t,n): return [tuple(t[i:i+n]) for i in range(max(0,len(t)-n+1))]
def dai_nhat_trung(a,b):
    A,B=tu(a),tu(b)
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False)
    m=sm.find_longest_match(0,len(A),0,len(B))
    return " ".join(A[m.a:m.a+m.size]), m.size
async def main():
    print(f"{'#':>3}{'từ':>5}{'chép 5-gram':>13}{'chuỗi chép dài nhất':>22}   câu hỏi")
    print("-"*100)
    ty=[]; dai=[]
    for i,(sp,q) in enumerate(HOI,1):
        try: tra,mt=await hoi(sp,q)
        except Exception as e: print(f"{i:>3}  LỖI {e}"); continue
        nguon=mt.get("rag_nguon") or []
        tl=" ".join((n.get("doan") or "") for n in nguon if not n.get("bi_loc"))
        if not tl.strip(): print(f"{i:>3}  (không có tài liệu)"); continue
        A=tu(tra); B=set(ng(tu(tl),5))
        g=ng(A,5)
        r=sum(1 for x in g if x in B)/max(1,len(g)); ty.append(r)
        chuoi,n=dai_nhat_trung(tra,tl); dai.append(n)
        print(f"{i:>3}{len(A):>5}{r*100:12.0f}%{n:>10} từ  {chuoi[:34]!r:<38}   {q[:26]}")
    print("-"*100)
    print(f"chép nguyên văn trung bình {sum(ty)/len(ty)*100:.0f}% số 5-gram   "
          f"chuỗi chép dài nhất trung bình {sum(dai)/len(dai):.1f} từ, tối đa {max(dai)}")
    print("\nĐối chiếu: 0% = tự diễn đạt hoàn toàn · trên 40% = chép nguyên đoạn")
asyncio.run(main())
