"""Gọi một số thật rồi cho AI nói vào cuộc gọi đó.

Đây là phép thử đầu-cuối thật sự: máy phone farm gọi ra, người bên kia bắt máy,
và nghe tiếng AI - không qua loa, không qua micro, tiếng được tiêm thẳng vào
đường lên của cuộc gọi.

Trình tự quan trọng:
  1. Bật cầu tiếng (app trên máy mở cổng TCP qua USB).
  2. Gọi.
  3. Chờ NGƯỜI BÊN KIA BẮT MÁY - đọc `mForegroundCallState`, không phải
     `mCallState`. Phát sớm hơn thì tiếng rơi vào lúc còn đổ chuông.
  4. NỐI MÁY XONG MỚI bật đường tiêm. Đặt trước là mất, vì dựng tuyến cuộc gọi
     làm HAL chạy lại mixer_paths.xml và ghi đè `ABOX UAIF0 SPK`.
  5. Phát lời chào.

    python scripts/goi_va_noi.py 0396130621
    python scripts/goi_va_noi.py 0396130621 --giay 45
"""

import argparse
import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"

LOI_CHAO = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
            "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def sh(cmd: str, root: bool = False, t: int = 60) -> str:
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb", "-s", SERIAL, "shell", full],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


# Trạng thái cuộc gọi trước (PreciseCallState). Đo tận tay bằng
# scripts/soi_trang_thai_goi.py trên chính máy này: một cuộc gọi ra đi qua
# 3 -> 4 -> 1 -> 0, và giá trị 1 rơi đúng vào giây người bên kia bấm nghe.
TEN_TRANG_THAI = {
    0: "rảnh",
    1: "ĐÃ NỐI MÁY",
    2: "đang giữ máy",
    3: "đang quay số",
    4: "đang đổ chuông bên kia",
    5: "có cuộc gọi đến",
    6: "cuộc gọi chờ",
    7: "đã ngắt",
    8: "đang ngắt",
}


def trang_thai_truoc() -> int:
    """Trạng thái cuộc gọi ĐANG hoạt động, theo mForegroundCallState.

    KHÔNG dùng mCallState: trong Android đó là OFFHOOK, tức "máy đang nhấc" -
    bật lên ngay từ lúc quay số. Dùng nó thì script báo nối máy ở giây thứ 2 và
    AI nói vào lúc còn đổ chuông, người bên kia chỉ nghe nhạc chờ.

    Cũng KHÔNG dùng dumpsys telecom: bản Samsung này chỉ ghi nhật ký có dấu thời
    gian (SET_DIALING / SET_ACTIVE / SET_DISCONNECTED), không có trường trạng
    thái hiện tại để đọc thẳng.
    """
    d = sh("dumpsys telephony.registry")
    m = re.search(r"mForegroundCallState=(\d+)", d)
    return int(m.group(1)) if m else -1


def da_noi_may() -> tuple[bool, str]:
    t = trang_thai_truoc()
    return t == 1, TEN_TRANG_THAI.get(t, f"mã {t}")


async def giu_duong_tiem(adb_service, duong=None, chu_ky: float = 5.0):
    """Canh đường tiêm, và CHỈ đặt lại khi nó thật sự bị ghi đè.

    HAL không đụng tới đường tiêm trong một cuộc gọi bình thường, nhưng mọi lần
    đổi tuyến (bật loa ngoài, cắm tai nghe, cuộc gọi chờ) đều làm nó chạy lại
    `mixer_paths.xml` và ghi đè `ABOX UAIF0 SPK`. Nên vẫn cần canh.

    NHƯNG ĐỪNG GHI VÔ ĐIỀU KIỆN. Bản cũ cứ 5 giây lại ghi hơn 20 control vào
    khối âm thanh giữa lúc đang gọi, và chính nó LÀM RỚT CUỘC GỌI. Đo tận tay
    (2026-08-05, cùng máy cùng SIM, các cuộc cách nhau vài phút):

        gọi trần, không đụng gì        36.1s   REMOTE / NORMAL
        cầu tiếng + ghi lại mỗi 5s     12-19s  ERROR / OUT_OF_SERVICE
        cầu tiếng + KHÔNG ghi lại      32.2s   REMOTE / NORMAL

    Ba lần đầu đều báo "Mobile network not available" nên rất dễ đổ oan cho nhà
    mạng - đã đổ oan thật một lần. Người dùng phản bác "hôm qua vẫn gọi bình
    thường" mới lòi ra.

    ĐỌC thì vô hại, GHI mới phá. Nên đọc trước, lệch mới ghi.
    """
    canh = ("ABOX UAIF0 SPK", "AIF1TX1 Input 2")
    while True:
        await asyncio.sleep(chu_ky)
        try:
            hien = await adb_service.doc_duong_tiem(SERIAL)
            lech = [k for k in canh
                    if hien.get(k) in (None, "None", "RESERVED")]
            if lech:
                print(f"    [giữ đường tiêm] HAL ghi đè {', '.join(lech)} -> đặt lại")
                await adb_service.set_uplink_injection(SERIAL, True, duong)
        except Exception:
            pass


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so", help="Số điện thoại cần gọi")
    ap.add_argument("--giay", type=int, default=40, help="Giữ cuộc gọi bao lâu")
    # src=3 (VOICE_DOWNLINK) chỉ thu tiếng ĐẦU BÊN KIA nói.
    # src=4 (VOICE_CALL) thu cả hai chiều trộn lại -> AI nghe thấy chính tiếng
    # mình vừa tiêm vào đường lên, phiên âm ra rác và tự cắt lời liên tục.
    ap.add_argument("--src", type=int, default=3,
                    help="3 = chỉ tiếng khách (nên dùng), 4 = cả hai chiều, 1 = micro")
    ap.add_argument("--duong", choices=["codec", "usb"], default=None,
                    help="đường tiêm tiếng lên: codec (mặc định) hoặc usb")
    # Giọng phải đặt cho CẢ BA chỗ: lời chào, các từ đệm, và phiên gọi. Thiếu
    # một chỗ là cuộc gọi đổi giọng giữa chừng - từ đệm một giọng, câu trả lời
    # một giọng khác.
    # Hai cần gạt để TÁCH nguyên nhân làm rớt cuộc gọi. Đo 2026-08-05: gọi
    # trần giữ được 36s và kết thúc bình thường, còn gọi có cầu tiếng + tiêm rớt
    # sau 12-19s với `Reason: OUT_OF_SERVICE`. Tức chính đường tiêm làm rớt chứ
    # không phải sóng - dùng hai cần này để khoanh xem khâu nào.
    ap.add_argument("--khong-giu", action="store_true",
                    help="chỉ đặt đường tiêm MỘT lần, không đặt lại định kỳ")
    ap.add_argument("--khong-tiem", action="store_true",
                    help="dựng cầu tiếng nhưng KHÔNG đụng mixer (AI sẽ không ai nghe được)")
    ap.add_argument("--giong", default=None,
                    help="tên giọng trong models/tts/ref_voices (mặc định: giọng trong .env)")
    args = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    from backend.services.filler_store import lay_kho
    from backend.services import adb_service
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    print("Nạp model ...")
    stt, llm, tts, rag = STTService(), LLMService(), F5TTSService(), RAGService()
    tts.load()
    rag.load()
    pipeline = StreamingPipeline(stt=stt, llm=llm, tts=tts, rag=rag)
    session = CallSession(customer_name="Khách")
    if args.giong:
        session.voice_name = await tts.ensure_voice(args.giong)
        if session.voice_name != args.giong:
            print(f"    !! không nạp được giọng '{args.giong}', dùng "
                  f"'{session.voice_name}'")
    # Nạp sẵn từ đệm CHO ĐÚNG GIỌNG đang dùng. Nạp cho giọng khác thì
    # `pick_filler` không tìm thấy và khách phải chờ im lặng hết TTFA.
    await tts.dung_fillers(lay_kho(), voice=session.voice_name)
    print(f"    giọng: {session.voice_name}")

    print(f"\n[1] Bật cầu tiếng trên máy (nguồn {args.src}) ...")
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=args.src)
    print(f"    {msg}")
    if not ok:
        return 1

    # KHÔNG bật đường tiêm ở đây. `ABOX UAIF0 SPK` là control HAL có quản (chính
    # đường `incall-headphone` trong mixer_paths.xml đặt nó), nên dựng tuyến cuộc
    # gọi sẽ xoá mất. Bật sau khi đã nối máy.

    bridge = PhoneCallBridge(pipeline, session, port=8123)
    giu = None
    bridge.tam_dung_nghe = True     # chưa nối máy thì đừng phiên âm nhạc chờ
    await bridge.start()
    print("    đã nối cầu tiếng (tạm chưa nghe)")

    try:
        print(f"\n[2] Gọi {args.so} ...")
        # Mở khoá TRƯỚC khi gọi. Màn khoá thì giao diện gọi không lên được và
        # cuộc gọi đứng im ở "rảnh" - trông hệt như không ai bắt máy, đã mất
        # nhiều lượt vì tưởng nhầm là nhà mạng chặn.
        sh("input keyevent KEYCODE_WAKEUP")
        sh("wm dismiss-keyguard")
        await asyncio.sleep(0.6)
        # Chỉ định thẳng khe SIM: máy hai khe bật hộp chọn SIM cho số chưa gọi
        # bao giờ, mà hộp đó chờ người bấm. Khe 1 trống, Viettel ở khe 2 -> slot 1.
        sh(f"am start -a android.intent.action.CALL -d tel:{args.so} "
           f"--ei com.android.phone.extra.slot 1")

        # SINH SẴN LỜI CHÀO NGAY BÂY GIỜ, trong lúc còn đổ chuông.
        # Lời chào là câu cố định, biết trước - không có lý do gì để chờ nối máy
        # xong mới sinh. Đo được: sinh sau khi nối máy làm khách phải nghe im
        # vài giây sau khi bấm nghe, và đó là ấn tượng đầu tiên của cuộc gọi.
        # Đổ chuông thường 5-12 giây, thừa sức che toàn bộ thời gian sinh.
        t_sinh = time.perf_counter()
        wav_chao = await tts.synthesize(LOI_CHAO, voice=session.voice_name,
                                        use_cache=False)
        print(f"    (đã sinh sẵn lời chào trong lúc đổ chuông: "
              f"{(time.perf_counter()-t_sinh)*1000:.0f}ms, {len(wav_chao)} byte)")

        print("[3] Chờ NGƯỜI BÊN KIA BẮT MÁY (tối đa 45s) — HÃY BẮT MÁY ...")
        noi = False
        da_quay = False       # đã từng thấy cuộc gọi sống, để phân biệt với lúc chưa kịp lên
        truoc = None
        for i in range(45):
            await asyncio.sleep(1)
            t = trang_thai_truoc()
            if t != truoc:
                print(f"    {i}s: {TEN_TRANG_THAI.get(t, f'mã {t}')}")
                truoc = t
            if t == 1:
                noi = True
                print(f"    -> mạng {sh('getprop gsm.network.type')}")
                break
            if t in (3, 4, 2):
                da_quay = True
            elif da_quay and t in (0, 7):
                print(f"    {i}s: cuộc gọi kết thúc trước khi bắt máy")
                return 1
        if not noi:
            print("    hết giờ chờ - không ai bắt máy")
            return 1

        # Chờ một nhịp cho tuyến âm thanh ổn định: phát ngay thì mấy trăm mili
        # giây đầu rơi vào lúc chưa có đường tiêm, mất chữ đầu câu chào.
        #
        # Hạ 1500 -> 800ms (2026-08-04). Sau khi bỏ được khâu sinh tiếng khỏi
        # đường tới hạn, mốc này chiếm 84% quãng im lặng khách nghe sau khi bấm
        # nghe. Mà đo thật thì đặt đường tiêm chỉ mất 167ms và đọc lại 83ms -
        # tức 1500ms là dư rất nhiều.
        # NẾU MẤT CHỮ ĐẦU CÂU thì nâng lại; đây là ấn tượng đầu tiên của khách.
        CHO_ON_DINH = 0.8
        t_noi = time.perf_counter()
        await asyncio.sleep(CHO_ON_DINH)

        t_inj = time.perf_counter()
        if args.khong_tiem:
            ok_inj, msg_inj = True, "(bỏ qua đặt đường tiêm theo yêu cầu)"
        else:
            ok_inj, msg_inj = await adb_service.set_uplink_injection(
                SERIAL, True, args.duong)
        ms_inj = (time.perf_counter() - t_inj) * 1000
        print(f"    {msg_inj}")
        if not ok_inj:
            return 1
        # Đọc lại để CHẮC đường tiêm đã vào, đừng tin mỗi lệnh set.
        t_doc = time.perf_counter()
        for k, v in sorted((await adb_service.doc_duong_tiem(SERIAL)).items()):
            print(f"        {k:<24}= {v}")
        ms_doc = (time.perf_counter() - t_doc) * 1000
        if not (args.khong_giu or args.khong_tiem):
            giu = asyncio.create_task(giu_duong_tiem(adb_service, args.duong))
        else:
            print('    (không đặt lại đường tiêm định kỳ)')
        bridge.tam_dung_nghe = False

        print(f"\n[4] AI nói lời chào (đã sinh sẵn) ...")
        await bridge.play(wav_chao)
        tong = (time.perf_counter() - t_noi) * 1000
        print(f"    đã đưa {len(wav_chao)} byte tiếng vào cuộc gọi")
        print(f"    TỪ LÚC NỐI MÁY TỚI LÚC CÓ TIẾNG: {tong:.0f}ms"
              f"   (chờ ổn định {CHO_ON_DINH*1000:.0f} + đặt đường tiêm {ms_inj:.0f}"
              f" + đọc lại {ms_doc:.0f} + đệm mồi {settings.phone_dem_mo_ms})")
        print(f"    >>> BẮT MÁY VÀ NGHE THỬ <<<")

        print(f"\n[5] Giữ cuộc gọi {args.giay}s, AI trả lời nếu bạn nói ...")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < args.giay:
            await asyncio.sleep(3)
            if trang_thai_truoc() != 1:
                print("    cuộc gọi đã kết thúc")
                break
            if bridge.turns:
                print(f"    {bridge.turns} lượt | khách: {bridge.sink.last_transcript[:50]}")
                print(f"              AI: {bridge.sink.last_reply[:60]}")
    finally:
        print("\n[6] Dọn dẹp ...")
        if giu is not None:
            giu.cancel()
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.set_uplink_injection(SERIAL, False, args.duong)
        await adb_service.stop_bridge(SERIAL, port=8123)
        print(f"    xong ({bridge.turns} lượt hội thoại)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
