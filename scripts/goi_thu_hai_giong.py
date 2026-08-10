"""Cuoc goi thu HAI GIONG, di qua DUNG duong realtime co STT.

Khac `ghi_hoi_thoai_that.py`: script do gui CHU (msg_type="text"), bo qua han
STT. Script nay TONG HOP tieng khach bang mot giong KHAC roi day vao WebSocket
duoi dang audio - dung duong ma cuoc goi that di:

    tieng khach -> STT -> RAG -> LLM -> cat manh -> TTS -> tieng AI

Nho the moi thu duoc nhung loi chi lo ra khi co STT: phien am sai lam AI tra loi
lac de, hoac tre STT cong them vao thoi gian khach cho.

Ban ghi ra HAI KENH:
    trai  = khach (giong khac)
    phai  = AI
Nghe stereo thi phan biet duoc ngay ai dang noi, va thay ro cho chong tieng.
Ban tron mono cung duoc ghi kem de nghe nhu qua dien thoai.

Chay TREN MAY WIN (backend phai dang chay):
    .venv\\python.exe scripts\\goi_thu_hai_giong.py
    .venv\\python.exe scripts\\goi_thu_hai_giong.py --giong-khach fosd_1
"""
import argparse
import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import websockets               # noqa: E402

from backend.services.tts_service import F5TTSService  # noqa: E402

WS = "ws://127.0.0.1:8100/ws/call/goi-thu"
RA = Path("C:/tmp/goithu")
SR = 24000

LUOT = [
    "Alo em chào anh, anh đang cần vay tín chấp thì lãi suất bao nhiêu vậy em?",
    "Vậy hạn mức tối đa là bao nhiêu, và anh cần chuẩn bị giấy tờ gì?",
    "Anh làm công ty được ba năm rồi, lương chuyển khoản mười lăm triệu một tháng.",
    "Thế thời gian giải ngân mất mấy ngày em nhỉ?",
    "Nếu anh muốn trả trước hạn thì có bị phạt gì không em?",
    "Em nói lại giúp anh toàn bộ điều kiện và thủ tục một lượt được không?",
    "Anh cần suy nghĩ thêm, em cho anh xin số điện thoại để anh gọi lại nhé.",
]


def mmss(g: float) -> str:
    return f"{int(g)//60:d}:{g - 60*(int(g)//60):05.2f}"


def wav_bytes(x: np.ndarray, sr: int) -> bytes:
    b = io.BytesIO()
    sf.write(b, np.clip(x, -1, 1), sr, format="WAV", subtype="PCM_16")
    return b.getvalue()


async def mot_luot(ws, wav: bytes, so: int, moc0: float):
    """Day TIENG khach vao, thu ve tung manh tieng AI kem moc thoi gian."""
    await ws.send(json.dumps({"type": "audio", "turn_id": so,
                              "data": base64.b64encode(wav).decode()}))
    manh, chu = [], {}
    while True:
        try:
            g = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
        except asyncio.TimeoutError:
            print(f"      hết giờ chờ lượt {so}")
            return manh, "", "", {}
        t = g.get("type")
        if t == "audio":
            x, sr = sf.read(io.BytesIO(base64.b64decode(g["data"])), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            manh.append({"moc": time.perf_counter() - moc0, "wav": x, "sr": sr,
                         "dai": len(x) / sr, "id": g.get("chunk_id", 0),
                         "dem": bool(g.get("is_filler"))})
        elif t == "response_chunk":
            chu[g.get("chunk_id", -1)] = g.get("text", "")
        elif t == "turn_complete":
            for m in manh:
                m["chu"] = "[câu đệm]" if m["dem"] else chu.get(m["id"], "")
            mt = g.get("metrics", {})
            return manh, g.get("full_response", ""), mt.get("transcript", ""), mt
        elif t == "transcript":
            chu["__stt__"] = g.get("text", "")
        elif t == "error":
            print(f"      lỗi: {g.get('message')}")
            return manh, "", "", {}


def len_lich(manh):
    """Moc PHAT that: client XEP HANG, manh sau noi duoi manh truoc."""
    ra, het = [], None
    for m in sorted(manh, key=lambda z: z["moc"]):
        phat = m["moc"] if het is None else max(m["moc"], het)
        dut = 0.0 if het is None else max(0.0, m["moc"] - het)
        het = phat + m["dai"]
        ra.append({**m, "phat": phat, "dut": dut})
    return ra


async def chay(giong_khach: str, ra: Path):
    svc = F5TTSService()
    svc.load()
    await svc.ensure_voice(giong_khach)
    print(f"  giọng khách: {giong_khach}\n")

    # Tong hop TRUOC toan bo tieng khach - khoi tinh vao do tre cuoc goi.
    tieng_khach = []
    for c in LUOT:
        b = await svc.synthesize(c, voice=giong_khach)
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        tieng_khach.append((x.mean(axis=1) if x.ndim > 1 else x, sr))

    ra.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(WS, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "set_session", "customer_name": "anh Hải",
                                  "product": "vay tín chấp", "phone": "0912345678"}))
        try:
            await asyncio.wait_for(ws.recv(), timeout=20)
        except asyncio.TimeoutError:
            pass

        k_seg, a_seg, bao = [], [], []
        moc0 = time.perf_counter()
        for i, (cau, (xk, srk)) in enumerate(zip(LUOT, tieng_khach), 1):
            t_khach = time.perf_counter() - moc0
            k_seg.append((t_khach, xk, srk))
            # Doi het tieng khach roi moi gui - dung nhu nguoi that noi xong.
            await asyncio.sleep(len(xk) / srk)
            print(f"  [{i}] khách : {cau}")
            manh, tra_loi, stt, mt = await mot_luot(ws, wav_bytes(xk, srk), i, moc0)
            lich = len_lich(manh)
            a_seg.extend(lich)
            bao.append((i, cau, t_khach, len(xk)/srk, stt, tra_loi, lich, mt))
            print(f"      STT nghe: {stt[:70]}")
            print(f"      AI      : {tra_loi[:70]}")
            print(f"      {len(manh)} mảnh, TTFA {mt.get('ttfa_ms','?')}ms,"
                  f" STT {mt.get('stt_ms','?')}ms")
            if lich:
                cho = max(m["phat"] + m["dai"] for m in lich) - (time.perf_counter() - moc0)
                if cho > 0:
                    await asyncio.sleep(cho)
            await asyncio.sleep(0.5)
    return k_seg, a_seg, bao


def dung_stereo(k_seg, a_seg, ra: Path):
    het = max([t + len(x)/s for t, x, s in k_seg] +
              [m["phat"] + m["dai"] for m in a_seg]) + 0.5
    n = int(het * SR)
    trai = np.zeros(n, dtype=np.float32)
    phai = np.zeros(n, dtype=np.float32)
    for t, x, s in k_seg:
        i = int(t * SR); j = min(i + len(x), n)
        trai[i:j] += x[:j-i]
    for m in a_seg:
        i = int(m["phat"] * SR); j = min(i + len(m["wav"]), n)
        phai[i:j] += m["wav"][:j-i]
    for kenh in (trai, phai):
        d = float(np.abs(kenh).max())
        if d > 1.0:
            kenh /= d
    sf.write(ra / "cuoc_goi_stereo.wav", np.stack([trai, phai], axis=1), SR)
    tron = np.clip((trai + phai) * 0.7, -1, 1)
    sf.write(ra / "cuoc_goi_mono.wav", tron, SR)
    return het


def viet_bao_cao(bao, ra: Path, het: float):
    d = ["CUOC GOI THU HAI GIONG - qua duong realtime co STT",
         "=" * 78, f"tong dai {mmss(het)}", "",
         "kenh TRAI = khach   |   kenh PHAI = AI", ""]
    dut = 0
    for i, cau, t_k, dai_k, stt, tra_loi, lich, mt in bao:
        d.append("-" * 78)
        d.append(f"[{i}] {mmss(t_k)} - {mmss(t_k + dai_k)}  KHACH: {cau}")
        d.append(f"      STT nghe lai : {stt}")
        d.append(f"      STT {mt.get('stt_ms','?')}ms | TTFA {mt.get('ttfa_ms','?')}ms")
        d.append("")
        for m in lich:
            co = ""
            if m["dut"] * 1000 > 300:
                co = "  <== DUT"; dut += 1
            d.append(f"  {mmss(m['phat'])} - {mmss(m['phat']+m['dai'])}  "
                     f"{('dem' if m['dem'] else '#'+str(m['id'])):<5} "
                     f"{(m.get('chu') or '')[:44]:<44}{co}")
    d.append("=" * 78)
    d.append(f"TONG: {sum(len(x[6]) for x in bao)} manh, {dut} cho dut")
    (ra / "bang_tra.txt").write_text("\n".join(d), encoding="utf-8")
    return dut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong-khach", default="giong_nam",
                    help="giọng đóng vai khách, phải KHÁC giọng AI")
    ap.add_argument("--ra", default=str(RA))
    a = ap.parse_args()
    ra = Path(a.ra)
    k, s, bao = asyncio.run(chay(a.giong_khach, ra))
    het = dung_stereo(k, s, ra)
    dut = viet_bao_cao(bao, ra, het)
    print(f"\n  tổng {mmss(het)}, {sum(len(x[6]) for x in bao)} mảnh, {dut} chỗ đứt")
    print(f"  {ra/'cuoc_goi_stereo.wav'}  (trái=khách, phải=AI)")
    print(f"  {ra/'cuoc_goi_mono.wav'}")
    print(f"  {ra/'bang_tra.txt'}")


if __name__ == "__main__":
    main()
