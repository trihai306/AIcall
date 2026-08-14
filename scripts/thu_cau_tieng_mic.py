"""Cau tieng co chay khong - thu bang nguon MIC, KHONG goi cho ai.

Neu byte chay ve thi duong ong (service + adb forward + o cam) lanh, va cho hong
nam o rieng viec thu TIENG CUOC GOI. Neu 0 byte thi chinh cau noi hong.
"""
import asyncio, socket, sys, time
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services import adb_service
S="21f10e44220c7ece"; PORT=8123
async def main():
    print("1) dừng cầu cũ nếu còn")
    await adb_service.stop_bridge(S, PORT)
    await asyncio.sleep(1)
    for ten, src in (("MIC (nguồn 1)", adb_service.SRC_MIC),
                     ("VOICE_CALL (nguồn 4)", adb_service.SRC_VOICE_CALL)):
        print(f"\n2) bật cầu nối nguồn {ten}")
        ok, msg = await adb_service.start_bridge(S, PORT, src)
        print(f"   {'OK' if ok else 'LỖI'}: {msg}")
        if not ok: continue
        await asyncio.sleep(1.5)
        try:
            s=socket.create_connection(("127.0.0.1",PORT), timeout=5)
            s.settimeout(4)
            tong=0; lan=0; t0=time.time()
            while time.time()-t0 < 3:
                try:
                    b=s.recv(4096)
                except socket.timeout:
                    break
                if not b:
                    print("   ổ cắm ĐÓNG (0 byte) — đúng triệu chứng trong log"); break
                tong+=len(b); lan+=1
            s.close()
            giay=time.time()-t0
            print(f"   nhận {tong} byte trong {giay:.1f}s ({lan} lần đọc)  "
                  f"= {tong/max(giay,0.01)/2/8000:.2f}x thời gian thực @8kHz")
            if tong==0: print("   -> KHÔNG có tiếng chảy về")
        except Exception as e:
            print(f"   không nối được ổ cắm: {type(e).__name__} {e}")
        await adb_service.stop_bridge(S, PORT)
        await asyncio.sleep(1)
    print("\n3) đã dừng cầu nối, không gọi cho ai cả")
asyncio.run(main())
