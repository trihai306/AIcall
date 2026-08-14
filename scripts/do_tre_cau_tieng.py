"""Sau `start_bridge`, bao lau thi o cam that su chay byte? Khong goi cho ai."""
import asyncio, socket, sys, time
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services import adb_service
S="21f10e44220c7ece"; PORT=8123
async def mot_lan(lan):
    await adb_service.stop_bridge(S, PORT); await asyncio.sleep(0.8)
    t0=time.time()
    ok,_=await adb_service.start_bridge(S, PORT, 3)
    t_bat=time.time()-t0
    if not ok: print(f"  lần {lan}: bật cầu LỖI"); return
    noi_duoc=None; byte_dau=None; so_lan_dut=0
    while time.time()-t0 < 8:
        try:
            s=socket.create_connection(("127.0.0.1",PORT), timeout=1.5); s.settimeout(1.5)
            if noi_duoc is None: noi_duoc=time.time()-t0
            try:
                b=s.recv(4096)
            except socket.timeout:
                b=b""
            s.close()
            if b:
                byte_dau=time.time()-t0; break
            so_lan_dut+=1
        except Exception:
            pass
        await asyncio.sleep(0.1)
    print(f"  lần {lan}:  bật cầu {t_bat:.2f}s | nối được ổ cắm sau {noi_duoc if noi_duoc is None else f'{noi_duoc:.2f}s'} "
          f"| CÓ BYTE sau {byte_dau if byte_dau is None else f'{byte_dau:.2f}s'} | số lần nối ra 0 byte: {so_lan_dut}")
async def main():
    print("Đo với nguồn 3 = VOICE_DOWNLINK (đúng nguồn đường gọi dùng):")
    for i in range(1,5): await mot_lan(i)
    await adb_service.stop_bridge(S, PORT)
    print("đã dừng cầu nối")
asyncio.run(main())
