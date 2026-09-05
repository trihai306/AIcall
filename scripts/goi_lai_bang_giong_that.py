"""Chay lai cuoc goi 4cd44fb7 bang CHINH GIONG THAT cua khach.

Tieng lay tu ban ghi cuoc goi that -> DA di qua GSM/AMR that, khong phai
tieng F5 sinh ra qua kenh gia lap nhu moi phep do truoc day.

Duong chay: WebSocket /ws/call/<id> -> process_turn -> STT -> RAG -> LLM -> TTS,
dung duong ma cuoc goi that dung. Phien do WS tu tao nen mang kich ban mac dinh
sc_nganhang va product RONG - trung khop cau hinh cuoc goi goc.
"""
import asyncio, time, base64, io, json, sys, time
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
import websockets

# Moi lan chay phai la PHIEN MOI, khong thi lich su luot cu con do va
# ket qua khong so sanh duoc voi lan truoc.
PHIEN = f"{int(time.time())}"

URL = f"ws://127.0.0.1:8100/ws/call/giong_that_{PHIEN}"
THU_MUC = Path(DU_AN / "data" / "luot_that")
RA = Path(DU_AN / "data" / "ket_goi_lai.txt")

# Chu may nghe duoc LUC GOI THAT (lay tu app.db) + cau AI da tra loi khi do
GOC = [
    ("cũng như nào",                  "Em xin lỗi, anh/chị có thể nói rõ hơn về vấn đề anh/chị đang hỏi không ạ?"),
    ("như nào",                       "anh/chị muốn biết về hạn mức vay tối đa ạ."),
    ("đúng rồi",                      "Hạn mức vay tối đa là 500 triệu đồng ạ. Anh/chị cần thêm thông tin gì không?"),
    ("lãi suất rất nhiều",            "Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ..."),
    ("đại sơn văn tín trăm ba nhiều", "Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ..."),
    ("mừng được mời nhiều",           "Anh/chị có thể nói rõ hơn về vấn đề anh/chị đang hỏi không ạ?"),
    ("sẵn mức được bao nhiêu",        "Hạn mức vay tối đa là 500 triệu đồng ạ. Anh/chị cần tư vấn thêm không?"),
]

async def mot_luot(ws, pcm: bytes):
    """Gui 1 luot, thu ve phien am + cau tra loi + so do."""
    await ws.send(json.dumps({"type": "audio",
                              "data": base64.b64encode(pcm).decode()}))
    phien_am, tra_loi, so_do = "", "", {}
    t0 = time.perf_counter()
    while True:
        try:
            tin = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        except asyncio.TimeoutError:
            return "(qua han)", "(qua han)", {}
        loai = tin.get("type", "")
        if loai == "transcript":
            phien_am = tin.get("text", "")
        elif loai == "error":
            tra_loi = f"(loi: {tin.get('message','')})"
        elif loai == "turn_complete":
            tra_loi = tin.get("full_response", "") or tra_loi
            so_do = tin.get("metrics", {}) or {}
            so_do["tong_ms"] = round((time.perf_counter() - t0) * 1000)
            return phien_am, tra_loi, so_do

async def main():
    dong = []
    async with websockets.connect(URL, max_size=None) as ws:
        chao = json.loads(await ws.recv())
        dong.append(f"phien: {chao.get('session_id','?')} | "
                    f"kich ban: {chao.get('scenario_id') or chao.get('scenario') or '(mac dinh)'}")
        for i in range(1, 8):
            f = THU_MUC / f"luot_{i}.raw"
            pcm = f.read_bytes()
            pa, tl, sd = await mot_luot(ws, pcm)
            goc_nghe, goc_dap = GOC[i - 1]
            dong.append(f"\n{'='*74}\nLUOT {i}   ({len(pcm)/32000:.2f}s tieng that)")
            dong.append(f"  may nghe LUC GOI THAT : {goc_nghe!r}")
            dong.append(f"  may nghe LAN NAY      : {pa!r}")
            dong.append(f"  {'>> GIONG NHAU' if pa.strip()==goc_nghe.strip() else '>> KHAC'}")
            dong.append(f"  AI dap LUC GOI THAT   : {goc_dap[:70]!r}")
            dong.append(f"  AI dap LAN NAY        : {tl.strip()[:70]!r}")
            dong.append(f"  so do: stt={sd.get('stt_ms','?')}ms rag={sd.get('rag_ms','?')}ms "
                        f"tong={sd.get('tong_ms','?')}ms"
                        + (f" | CHAN: {sd['chan_lai_suat_bia']}" if sd.get('chan_lai_suat_bia') else "")
                        + (f" | CHAN SO: {sd['chan_so_sai']}" if sd.get('chan_so_sai') else ""))
    RA.write_text("\n".join(dong), encoding="utf-8")
    print("xong ->", RA)

asyncio.run(main())
