"""Do dinh luong muc RAP KHUON cua cau tra loi. Khong doan, do.

Bon thuoc do:
  1. Cau mo dau: bao nhieu kieu khac nhau tren N luot
  2. Cau ket: nhu tren
  3. Trung 4-gram giua CAC CAP cau tra loi (khac chu de van trung = rap khuon)
  4. Do dai: lech chuan (rap khuon thi moi cau dai bang nhau)
Chay lai cung cau hoi 3 lan de tach "rap khuon giua cac cau hoi" khoi
"khong da dang khi hoi lai cung mot cau".
"""
import asyncio, itertools, json, re, statistics, sys, unicodedata
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
WS="ws://127.0.0.1:8100/ws/call/new"
HOI=[("vay tín chấp","lãi suất vay tín chấp bao nhiêu"),
     ("vay tín chấp","anh vay được tối đa bao nhiêu"),
     ("vay tín chấp","cần giấy tờ gì không em"),
     ("vay tín chấp","bao lâu thì giải ngân"),
     ("vay tín chấp","anh đang nợ chỗ khác có vay được không"),
     ("vay mua nhà","lãi suất vay mua nhà thế nào"),
     ("vay mua nhà","vay được bao nhiêu phần trăm giá trị nhà"),
     ("vay mua nhà","thời hạn tối đa mấy năm"),
     ("thẻ tín dụng","hạn mức thẻ tín dụng bao nhiêu"),
     ("thẻ tín dụng","phí thường niên thế nào"),
     ("tiết kiệm","lãi suất gửi tiết kiệm bao nhiêu"),
     ("tiết kiệm","gửi online có lợi hơn không"),
     ("vay tín chấp","anh không quan tâm đâu"),
     ("vay tín chấp","đang bận em ạ"),
     ("vay tín chấp","để anh suy nghĩ thêm")]
async def hoi(sp,q):
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        await ws.send(json.dumps({"type":"text_soi","text":q,"turn_id":1}))
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=180))
            if m.get("type")=="turn_complete": return m.get("full_response","")
def tu(s): return re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split()
def ngram(s,n=4):
    t=tu(s); return {tuple(t[i:i+n]) for i in range(max(0,len(t)-n+1))}
def mo_dau(s,k=3): return " ".join(tu(s)[:k])
def ket(s,k=3): return " ".join(tu(s)[-k:])
async def main():
    lan={}
    for i in range(1,4):
        ra=[]
        for sp,q in HOI:
            try: ra.append(await hoi(sp,q))
            except Exception as e: ra.append("")
        lan[i]=[x for x in ra if x.strip()]
        print(f"lượt {i}: {len(lan[i])}/{len(HOI)} câu")
    for i,ra in lan.items():
        md={mo_dau(x) for x in ra}; kt={ket(x) for x in ra}
        dai=[len(tu(x)) for x in ra]
        cap=[len(ngram(a)&ngram(b))/max(1,min(len(ngram(a)),len(ngram(b))))
             for a,b in itertools.combinations(ra,2)]
        print(f"\nlượt {i}  ({len(ra)} câu trả lời cho {len(ra)} câu hỏi KHÁC nhau)")
        print(f"   kiểu mở đầu khác nhau : {len(md):>3}/{len(ra)}   {sorted(md)[:4]}")
        print(f"   kiểu kết câu khác nhau: {len(kt):>3}/{len(ra)}   {sorted(kt)[:4]}")
        print(f"   trùng 4-gram giữa các cặp: trung bình {sum(cap)/len(cap)*100:5.1f}%  "
              f"cao nhất {max(cap)*100:.0f}%")
        print(f"   độ dài: {min(dai)}-{max(dai)} từ, lệch chuẩn {statistics.pstdev(dai):.1f}")
    print("\n--- 6 câu trả lời đầu của lượt 1 ---")
    for x in lan[1][:6]: print("  •",x[:110])
asyncio.run(main())
