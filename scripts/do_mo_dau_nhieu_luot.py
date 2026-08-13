"""Do mo dau tren MOT phien nhieu luot lien tiep - dung cach co che xen ke chay.

Phep do truoc SAI: moi cau hoi mo mot phien MOI nen session.turn_count luon bang
nhau, `bo_da` ra cung mot ket qua, co che xen ke chua tung duoc kich hoat.
"""
import asyncio, json, re, sys, unicodedata
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
WS="ws://127.0.0.1:8100/ws/call/new"
LUOT=["lãi suất vay tín chấp bao nhiêu","anh vay được tối đa bao nhiêu",
      "cần giấy tờ gì không em","bao lâu thì giải ngân",
      "anh đang nợ chỗ khác có vay được không","điều kiện vay là gì",
      "phí trả nợ trước hạn thế nào","thế thủ tục có phức tạp không",
      "anh cần vay 80 triệu","trả trong 36 tháng mỗi tháng bao nhiêu"]
def tu(s): return re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split()
async def main():
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh",
                                  "product":"vay tín chấp"}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        ten_a = "số lần ạ"
        print(f"{'lượt':>5}  {'mở đầu':<16}{ten_a:>11}  câu trả lời")
        print("-"*100)
        dau=[]; sa=[]
        for i,q in enumerate(LUOT,1):
            await ws.send(json.dumps({"type":"text_soi","text":q,"turn_id":i}))
            while True:
                m=json.loads(await asyncio.wait_for(ws.recv(),timeout=180))
                if m.get("type")=="turn_complete": break
            tra=m.get("full_response","")
            t=tu(tra); md=" ".join(t[:2]); n=sum(1 for x in t if x=="ạ")
            dau.append(md); sa.append(n)
            print(f"{i:>5}  {md:<16}{n:>11}  {tra[:62]}")
        print("-"*100)
        print(f"kiểu mở đầu khác nhau: {len(set(dau))}/{len(dau)}   {sorted(set(dau))}")
        print(f"lượt mở bằng 'dạ'    : {sum(1 for x in dau if x.startswith('dạ'))}/{len(dau)}")
        print(f"'ạ' trung bình       : {sum(sa)/len(sa):.2f} lần/lượt   (0 lần: {sa.count(0)} lượt)")
asyncio.run(main())
