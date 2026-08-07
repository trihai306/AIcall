"""Gọi rồi ĐỌC MỘT KỊCH BẢN DÀI - không STT, không LLM, không hội thoại.

Vì sao cần: khi nghe thử một cuộc gọi có AI, chất giọng bị trộn lẫn với chất
lượng nhận dạng và chất lượng trả lời, khó chấm riêng thứ nào. Script này bỏ hết
phần AI, chỉ còn đúng đường tiếng - nghe được liên tục gần một phút để chấm
giọng, tốc độ, ngữ điệu, và độ rõ khi đọc SỐ.

Kịch bản cố ý chứa đủ các con số thật trong tài liệu (7.9%, 500 triệu, 12-60
tháng, 24 giờ, 5 triệu) để nghe luôn bộ đọc số có đúng không.

    python scripts/goi_doc_kich_ban.py 0833816298
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

# Cắt sẵn thành từng câu: sinh và phát lần lượt để khách nghe liền mạch mà không
# phải chờ sinh xong cả bài.
KICH_BAN = [
    "Dạ em chào anh chị ạ. Em là Lan, nhân viên tư vấn của ngân hàng ABC ạ.",
    "Em gọi để giới thiệu tới anh chị chương trình vay tín chấp cá nhân đang "
    "triển khai ạ.",
    "Dạ lãi suất hiện tại của bên em là từ 7.9% một năm ạ.",
    "Hạn mức cho vay lên đến 500 triệu đồng, thời hạn linh hoạt từ 12 đến 60 tháng ạ.",
    "Điều kiện cũng đơn giản thôi ạ, anh chị chỉ cần có thu nhập ổn định "
    "từ 5 triệu đồng một tháng trở lên.",
    "Hồ sơ thì anh chị chuẩn bị căn cước công dân còn hiệu lực và sao kê lương "
    "ba tháng gần nhất ạ.",
    "Sau khi hồ sơ được phê duyệt, bên em giải ngân trong vòng 24 giờ ạ.",
    "Dạ không biết anh chị có đang quan tâm tới khoản vay nào không ạ?",
]

TEN_TT = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 2: "giữ máy", 3: "đang quay số",
          4: "đổ chuông bên kia", 7: "đã ngắt", 8: "đang ngắt"}


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


# ĐÃ BỎ `giu_duong_tiem`. Nó ghi lại mixer mỗi 5 giây để "giữ" đường tiêm, và
# chính việc ghi đó LÀM RỚT CUỘC GỌI: đo được cuộc trần giữ 36.1s (REMOTE/NORMAL)
# còn cuộc có vòng ghi lại chỉ 12-19s rồi đứt với ERROR/OUT_OF_SERVICE - nhìn ra
# y như "mất sóng". Backend đã gỡ vòng này từ lâu, chỉ script còn sót.
# Đặt đường tiêm ĐÚNG MỘT LẦN sau khi nối máy là đủ.


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--duong", choices=["codec", "usb"], default=None)
    # Nhận văn bản riêng qua TỆP, không qua tham số dòng lệnh: chuỗi tiếng Việt
    # đi qua PowerShell rồi SSH bị hỏng dấu ở nhiều tầng trích dẫn, đã mắc.
    # Mỗi dòng trong tệp là một mảnh đọc liền - ngắt dòng ở đâu thì nghỉ ở đó.
    ap.add_argument("--tep", default="", help="tệp UTF-8, mỗi dòng một mảnh đọc")
    # Đọc LIỀN MẠCH: ghép hết thành MỘT dòng tiếng rồi phát một lần, không nghỉ
    # giữa câu. Vẫn sinh theo từng mảnh chứ không đưa cả bài vào F5 một lượt -
    # văn bản càng dài F5 càng trôi giọng, mà ghép lại thì tai không phân biệt
    # được miễn là cắt sạch quãng lặng ở hai đầu mỗi mảnh.
    ap.add_argument("--lien-mach", action="store_true",
                    help="ghép cả bài thành một dòng tiếng, bỏ nhịp nghỉ giữa câu")
    # Đổi checkpoint / tốc độ CHỈ CHO LẦN CHẠY NÀY, không sửa .env. Cần khi so
    # hai checkpoint cạnh nhau: sửa .env rồi khởi động lại mất 3 phút mỗi lượt,
    # mà còn dễ quên trả về giá trị cũ. `load()` đọc settings lúc nạp nên gán
    # đè trước khi gọi là đủ.
    ap.add_argument("--ckpt", default="", help="đường dẫn checkpoint khác")
    ap.add_argument("--vocab", default="", help="vocab đi kèm --ckpt")
    ap.add_argument("--speed", type=float, default=0.0, help="đè F5TTS_SPEED")
    # Xuất ra tệp và KHÔNG gọi. Cần khi người nghe không tiện bắt máy, hoặc khi
    # muốn nghe đi nghe lại một bản để chấm tốc độ/ngữ điệu mà không tốn cuộc gọi.
    # Lưu ý khi chấm: tệp này CHƯA qua GSM, nên nghe sạch hơn thực tế.
    ap.add_argument("--chi-luu", default="",
                    help="chỉ sinh tiếng ra tệp WAV này, không quay số")
    # GHI ÂM CUỘC GỌI bằng chính điện thoại: đổi nguồn thu sang VOICE_CALL (4)
    # thay vì VOICE_DOWNLINK (3). Nguồn 4 trộn CẢ HAI chiều - đúng thứ một máy
    # ghi âm cuộc gọi cho ra.
    #
    # Vì sao không dùng tính năng ghi âm sẵn của Samsung: SM-G965F bản quốc tế
    # khoá theo vùng. Khoá `CscFeature_VoiceCall_ConfigRecording` có trong ROM
    # (vùng BNG/CAM/EGY/ILO/INS bật) nhưng `/odm` gắn read-only và máy không có
    # sales code active - muốn bật phải remount phân vùng hệ thống rồi khởi
    # động lại. Không đáng liều trên máy DUY NHẤT của dự án.
    #
    # Nguồn 4 chỉ dùng được ở ĐÂY vì kịch bản không nghe (`tam_dung_nghe`). Với
    # cuộc gọi hội thoại thật thì PHẢI giữ nguồn 3, không thì AI nghe thấy chính
    # tiếng mình vừa tiêm rồi tự cắt lời liên tục.
    ap.add_argument("--ghi", default="",
                    help="ghi âm cả cuộc gọi (cả hai chiều) ra tệp WAV này")
    a = ap.parse_args()

    kich_ban = KICH_BAN
    if a.tep:
        dong = [l.strip() for l in Path(a.tep).read_text(encoding="utf-8").splitlines()]
        kich_ban = [l for l in dong if l]
        if not kich_ban:
            print(f"  tệp {a.tep} không có dòng nào")
            return 1

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    from backend.pipeline.text_normalizer import normalize_for_tts
    from backend.services import adb_service
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import FRAME_MS, PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    if a.ckpt:
        settings.f5tts_ckpt_path = a.ckpt
        if a.vocab:
            settings.f5tts_vocab_path = a.vocab
    if a.speed:
        settings.f5tts_speed = a.speed

    print("Nạp model ...")
    tts = F5TTSService()
    tts.load()
    print(f"  ckpt : {settings.f5tts_ckpt_path}")
    print(f"  giọng: {settings.f5tts_ref_audio}")
    print(f"  speed: {settings.f5tts_speed} | compile: {settings.f5tts_compile}\n")

    # SINH SẴN TOÀN BỘ trước khi gọi - khách không phải chờ giữa các câu.
    print("Sinh sẵn toàn bộ kịch bản ...")
    t0 = time.perf_counter()
    manh = []
    for i, c in enumerate(kich_ban, 1):
        w = await tts.synthesize(c, use_cache=False)
        manh.append(w)
        print(f"  {i}/{len(kich_ban)}  {len(w):>7} byte   {normalize_for_tts(c)[:62]}")
    print(f"  xong trong {(time.perf_counter()-t0):.1f}s, "
          f"tổng {sum(len(m) for m in manh)/1024:.0f} KB\n")

    if a.lien_mach:
        import io as _io

        import numpy as _np
        import soundfile as _sf

        from backend.services.tts_service import trim_silence
        khuc, sr_g = [], None
        for w in manh:
            y, sr_g = _sf.read(_io.BytesIO(w), dtype="float32")
            # Cắt lặng hai đầu MỖI mảnh: F5 chừa im lặng trước/sau, không cắt
            # thì ghép lại vẫn nghe ra từng câu rời đúng thứ đang muốn bỏ.
            khuc.append(trim_silence(y, sr_g))
        # Chèn 60ms giữa hai mảnh - đủ để không dính chữ vào nhau, ngắn hơn
        # nhiều so với quãng nghỉ tự nhiên nên tai nghe ra một mạch.
        # Quãng nghỉ THEO DẤU CÂU kết thúc mảnh trước. Phải chèn bằng code:
        # đo được F5 gần như LỜ dấu phẩy - thêm 55% dấu phẩy và 70% dấu chấm vào
        # văn bản chỉ làm số quãng nghỉ tăng 11% (45 -> 50), mật độ đứng yên
        # (8.5 -> 8.1 âm tiết mỗi lần nghỉ). Xem scripts/so_nhip_van_noi.py.
        # Người nói thật nghỉ KHÔNG ĐỀU: lướt qua dấu phẩy, dừng hẳn ở dấu chấm,
        # và treo lâu nhất sau câu hỏi để chờ người kia đáp.
        NGHI_MS = {",": 130, ";": 190, ":": 190, ".": 300, "!": 300, "?": 420}
        def khe(cau: str) -> _np.ndarray:
            d = NGHI_MS.get(cau.rstrip()[-1:], 220) if cau.strip() else 220
            return _np.zeros(int(sr_g * d / 1000), dtype="float32")

        phan = [khuc[0]]
        for i in range(1, len(khuc)):
            phan.append(khe(kich_ban[i - 1]))
            phan.append(khuc[i])
        ca_bai = _np.concatenate(phan)
        buf = _io.BytesIO()
        _sf.write(buf, ca_bai, sr_g, format="WAV", subtype="PCM_16")
        manh = [buf.getvalue()]
        print(f"  ghép LIỀN MẠCH: {len(ca_bai)/sr_g:.1f}s trong một dòng tiếng\n")

    if a.chi_luu:
        import io as _io2
        import wave as _wave
        p = Path(a.chi_luu)
        p.parent.mkdir(parents=True, exist_ok=True)
        if len(manh) == 1:
            p.write_bytes(manh[0])
        else:
            # Nhiều mảnh (không dùng --lien-mach): nối thô phần dữ liệu PCM.
            import soundfile as _sf2

            import numpy as _np2
            khuc, sr2 = [], None
            for w in manh:
                y, sr2 = _sf2.read(_io2.BytesIO(w), dtype="float32")
                khuc.append(y)
            _sf2.write(str(p), _np2.concatenate(khuc), sr2,
                       format="WAV", subtype="PCM_16")
        with _wave.open(str(p)) as f:
            giay = f.getnframes() / f.getframerate()
        print(f"  đã lưu {p}  ({giay:.1f}s, {p.stat().st_size/1024:.0f} KB)")
        return 0

    pipeline = StreamingPipeline(stt=STTService(), llm=LLMService(),
                                 tts=tts, rag=RAGService())
    bridge = PhoneCallBridge(pipeline, CallSession(customer_name="Khách"),
                             port=8123)
    bridge.tam_dung_nghe = True          # KHÔNG nghe, KHÔNG chạy AI

    khung_ghi: list[bytes] = []
    if a.ghi:
        # Móc vào vòng thu để giữ lại TỪNG khung 20ms máy gửi lên. Đặt trước
        # `bridge.start()`; móc này chạy TRƯỚC nhánh `tam_dung_nghe` nên vẫn
        # nhận đủ khung dù đang không nghe.
        bridge.theo_doi_khung = khung_ghi.append

    nguon = 4 if a.ghi else 3
    print(f"[1] Bật cầu tiếng ...")
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=nguon)
    print(f"    {msg}" + ("   [nguồn 4 = ghi cả hai chiều]" if a.ghi else ""))
    if not ok:
        return 1
    await bridge.start()

    try:
        print(f"[2] Gọi {a.so} ...")
        sh("input keyevent KEYCODE_WAKEUP")
        sh("wm dismiss-keyguard")
        await asyncio.sleep(0.6)
        sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
           f"--ei com.android.phone.extra.slot 1")

        print("[3] Chờ bắt máy — HÃY BẮT MÁY ...")
        truoc, noi = None, False
        for i in range(45):
            await asyncio.sleep(1)
            t = trang_thai()
            if t != truoc:
                print(f"    {i}s: {TEN_TT.get(t, f'mã {t}')}")
                truoc = t
            if t == 1:
                noi = True
                break
        if not noi:
            print("    không ai bắt máy")
            return 1

        await asyncio.sleep(0.8)
        ok_i, msg_i = await adb_service.set_uplink_injection(SERIAL, True, a.duong)
        print(f"    {msg_i}")
        if not ok_i:
            return 1

        bi_cat = False
        print(f"\n[4] Đọc kịch bản ({len(kich_ban)} câu) ...")
        for i, w in enumerate(manh, 1):
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc giữa chừng")
                break
            print(f"    câu {i}/{len(manh)}")
            await bridge.play(w)
            # chờ phát gần hết rồi mới đưa câu sau, để nghe liền mạch mà không
            # dồn cục làm phình đệm của điện thoại
            con_lai = 0.0
            while not bridge._out.empty():
                await asyncio.sleep(0.15)
                if trang_thai() != 1:
                    # Người kia cúp giữa chừng. PHẢI báo ra: ở chế độ liền mạch
                    # cả bài là MỘT mảnh, nên vòng ngoài chỉ chạy một lượt rồi
                    # in "Đọc xong" - nhìn từ log không phân biệt được với việc
                    # đọc trọn bài. Đã bị đúng chuyện này: bản ghi 26s trong khi
                    # log báo đọc xong 102s, mất công đi tìm lỗi luồng thu.
                    con_lai = bridge._out.qsize() * FRAME_MS / 1000.0
                    print(f"    NGƯỜI KIA CÚP MÁY — còn {con_lai:.0f}s chưa phát")
                    bridge.drop_pending_audio()
                    bi_cat = True
                    break
            if not a.lien_mach:
                await asyncio.sleep(0.35)     # nhịp nghỉ giữa câu
        if bi_cat:
            print("\n[5] KHÔNG đọc hết — cuộc gọi bị cúp giữa chừng.")
        else:
            print("\n[5] Đọc xong, giữ máy thêm 5s ...")
            await asyncio.sleep(5)
    finally:
        print("\n[6] Dọn dẹp ...")
        if a.ghi:
            import wave as _w
            from backend.services.phone_call_service import RATE_LEN as _RL
            p = Path(a.ghi)
            p.parent.mkdir(parents=True, exist_ok=True)
            with _w.open(str(p), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(_RL)
                f.writeframes(b"".join(khung_ghi))
            giay = sum(len(k) for k in khung_ghi) / 2 / _RL
            print(f"    đã ghi {p}  ({giay:.1f}s, {len(khung_ghi)} khung)")
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.set_uplink_injection(SERIAL, False, a.duong)
        await adb_service.stop_bridge(SERIAL, port=8123)
        print("    xong")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
