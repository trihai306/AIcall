"""Chay mot hoi thoai QUA DUNG DUONG THAT roi ghi lai y nhu khach nghe.

Khac han cac script tong hop tieng thong thuong: script nay noi vao WebSocket cua
backend, di qua DUNG duong ma trang Hoi thoai va cuoc goi dung - LLM streaming ->
cat manh -> TTS -> gui tung manh. Roi no dat MOI MANH VAO DUNG MOC THOI GIAN
manh do toi noi.

Vi sao phai giu moc thoi gian: noi lien cac manh lai thi moi khoang dut BIEN MAT.
Ban ghi nghe muot trong khi khach that su nghe ngat quang. Do chinh la ly do cac
lan xuat tieng truoc day khong tai hien duoc loi.

Ket qua:
    <ra>/hoi_thoai.wav        toan bo cuoc noi chuyen, gap giu nguyen
    <ra>/bao_cao.txt          tung manh: moc toi, do dai, khoang lang truoc no

Chay TREN MAY WIN (backend phai dang chay):
    .venv\\python.exe scripts\\ghi_hoi_thoai_that.py
    .venv\\python.exe scripts\\ghi_hoi_thoai_that.py --tep kich_ban.txt
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

WS = "ws://127.0.0.1:8100/ws/call/thu-nghe"   # /ws/campaign la tien do chien dich, KHONG phai hoi thoai
RA = Path("C:/tmp/hoithoai")
SR = 24000
# Khach noi gi. Moi dong mot luot - chon cau ma AI phai tra loi DAI, vi manh
# ngan chi xuat hien khi cau tra loi co nhieu dau phay.
LUOT = [
    "Alo em chào anh, anh đang cần vay tín chấp thì lãi suất bao nhiêu vậy em?",
    "Vậy hạn mức tối đa là bao nhiêu, và anh cần giấy tờ gì?",
    "Anh làm công ty được ba năm rồi, lương chuyển khoản mười lăm triệu.",
    "Thế thời gian giải ngân mất mấy ngày em nhỉ?",
]


async def mot_luot(ws, text: str, so: int, moc0: float):
    """Gui mot cau, thu ve moi manh tieng kem moc thoi gian."""
    await ws.send(json.dumps({"type": "text", "text": text, "turn_id": so}))
    manh = []
    while True:
        try:
            tho = await asyncio.wait_for(ws.recv(), timeout=90)
        except asyncio.TimeoutError:
            print(f"    het gio cho luot {so}")
            break
        g = json.loads(tho)
        t = g.get("type")
        if t == "audio":
            b = base64.b64decode(g["data"])
            x, sr = sf.read(io.BytesIO(b), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            # Lang o DAU manh = do code chen (chen_lang_dau_wav). Do thang o
            # day thay vi suy tu ban ghi da ghep: suy tu ngoai da doan sai hai
            # lan (goi nham lang chen thanh "F5 bia").
            n = max(1, int(sr * 0.02))
            k = len(x) // n
            dau = 0
            for i in range(k):
                if abs(x[i*n:(i+1)*n]).max() >= 0.015:
                    break
                dau += 20
            # Quang lang nam GIUA tieng cua chinh manh nay - neu co thi la F5
            # bia that, khong the do dau khac duoc nua.
            im_giua, i2 = [], 0
            while i2 < k:
                if abs(x[i2*n:(i2+1)*n]).max() < 0.015:
                    j2 = i2
                    while j2 < k and abs(x[j2*n:(j2+1)*n]).max() < 0.015:
                        j2 += 1
                    if i2 > 0 and j2 < k and (j2-i2)*20 >= 300:
                        im_giua.append((j2-i2)*20)
                    i2 = j2
                else:
                    i2 += 1
            manh.append({
                "moc": time.perf_counter() - moc0,
                "wav": x, "sr": sr,
                "lang_dau": dau,
                "im_giua": im_giua,
                "dai": len(x) / sr,
                "id": g.get("chunk_id", 0),
                "dem": bool(g.get("is_filler")),
            })
        elif t == "turn_complete":
            return manh, g.get("full_response", ""), g.get("metrics", {})
        elif t == "error":
            print(f"    loi: {g.get('message')}")
            return manh, "", {}
    return manh, "", {}


async def chay(luot, ra: Path):
    ra.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(WS, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "set_session",
                                  "customer_name": "anh Hải",
                                  "product": "vay tín chấp",
                                  "phone": "0912345678"}))
        try:
            await asyncio.wait_for(ws.recv(), timeout=20)
        except asyncio.TimeoutError:
            pass

        tat_ca, bao = [], []
        moc0 = time.perf_counter()
        for i, cau in enumerate(luot, 1):
            t_gui = time.perf_counter() - moc0
            print(f"\n  [{i}] khách: {cau}")
            manh, tra_loi, mt = await mot_luot(ws, cau, i, moc0)
            bao.append((i, cau, t_gui, manh, tra_loi, mt))
            tat_ca.extend(manh)
            print(f"      AI  : {tra_loi[:76]}")
            print(f"      {len(manh)} mảnh, TTFA {mt.get('ttfa_ms','?')}ms")
            # Cho tieng luot nay phat het roi moi hoi cau sau - dung nhu nguoi that.
            if manh:
                het = max(m["phat"] + m["dai"] for m in len_lich(manh))
                cho = het - (time.perf_counter() - moc0)
                if cho > 0:
                    await asyncio.sleep(cho)
            await asyncio.sleep(0.7)
        return tat_ca, bao


def len_lich(manh):
    """Tinh moc PHAT that cho tung manh, dung mo hinh client dung.

    Client KHONG phat manh vao dung luc no toi - no XEP HANG. Manh sau noi duoi
    manh truoc:
        phat_luc = max(luc_toi, luc_manh_truoc_phat_xong)

    Vi TTS nhanh hon realtime ~4x nen manh thuong toi SOM (luc_toi am so voi
    manh truoc) - do la binh thuong, khong phai loi.

    DUT xay ra khi luc_toi > luc_manh_truoc_phat_xong: khong con gi de phat,
    loa im cho toi khi manh moi toi. Do chinh la khoang trong khach nghe thay.

    Ban dau script dat moi manh vao dung luc_toi -> cac manh chong len nhau,
    ra tieng de len tieng. Ban ghi kieu do vo dung.
    """
    ra, het = [], None
    for m in sorted(manh, key=lambda z: z["moc"]):
        if het is None:
            phat, dut = m["moc"], 0.0
        else:
            dut = max(0.0, m["moc"] - het)
            phat = max(m["moc"], het)
        het = phat + m["dai"]
        ra.append({**m, "phat": phat, "dut": dut})
    return ra


def dung_wav(lich, ra: Path):
    if not lich:
        return 0.0
    tong = max(m["phat"] + m["dai"] for m in lich) + 0.5
    out = np.zeros(int(tong * SR), dtype=np.float32)
    for m in lich:
        x = m["wav"]
        if m["sr"] != SR:                       # moi manh deu 24k, nhung phong xa
            n = int(len(x) * SR / m["sr"])
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
        i = int(m["phat"] * SR)
        j = min(i + len(x), len(out))
        out[i:j] += x[: j - i]
    d = float(np.abs(out).max())
    if d > 1.0:
        out /= d
    sf.write(ra / "hoi_thoai.wav", out, SR)
    return tong


def viet_bao_cao(bao, ra: Path, tong: float):
    d = []
    d.append("BAN GHI HOI THOAI - giu nguyen moc thoi gian that")
    d.append("=" * 66)
    d.append(f"tong dai: {tong:.1f}s")
    d.append("")
    d.append("Cot 'lang truoc' = khoang im lang ngay TRUOC manh do.")
    d.append("Duoi 150ms la nhip nghi binh thuong. Tren 300ms la nghe ra DUT.")
    d.append("")
    tong_dut = 0
    for i, cau, t_gui, manh, tra_loi, mt in bao:
        d.append("-" * 66)
        d.append(f"[{i}] {t_gui:6.2f}s  KHACH: {cau}")
        d.append(f"          AI   : {tra_loi}")
        d.append(f"          TTFA {mt.get('ttfa_ms','?')}ms")
        for m in len_lich(manh):
            co = ""
            if m["dut"] * 1000 > 300:
                co = "   <== DUT"
                tong_dut += 1
            nhan = "dem " if m["dem"] else f"#{m['id']:<3}"
            d.append(f"            {nhan} toi {m['moc']:6.2f}s  phat {m['phat']:6.2f}s"
                     f"  dai {m['dai']:5.2f}s  lang dau {m.get('lang_dau',0):4.0f}ms"
                     f"  im {m['dut']*1000:6.0f}ms"
                     f"{'  BIA ' + str(m.get('im_giua')) if m.get('im_giua') else ''}{co}")
    d.append("=" * 66)
    d.append(f"TONG SO CHO DUT (lang > 300ms giua cac manh): {tong_dut}")
    (ra / "bao_cao.txt").write_text("\n".join(d), encoding="utf-8")
    return tong_dut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", default=None, help="tep chua cau khach, moi dong mot luot")
    ap.add_argument("--ra", default=str(RA))
    a = ap.parse_args()

    luot = LUOT
    if a.tep:
        luot = [l.strip() for l in Path(a.tep).read_text(encoding="utf-8").splitlines()
                if l.strip()]

    ra = Path(a.ra)
    manh, bao = asyncio.run(chay(luot, ra))
    tong = dung_wav(len_lich(manh), ra)
    dut = viet_bao_cao(bao, ra, tong)
    print(f"\n  tong {tong:.1f}s, {len(manh)} mảnh, {dut} chỗ đứt (lặng > 300ms)")
    print(f"  {ra / 'hoi_thoai.wav'}")
    print(f"  {ra / 'bao_cao.txt'}")


if __name__ == "__main__":
    main()
