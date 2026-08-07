import asyncio
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.models.db import save_session
from backend.pipeline.session_manager import CallSession
from backend.pipeline.streaming_pipeline import FILLER_PHRASES

logger = logging.getLogger(__name__)
router = APIRouter()

# Strong refs so an in-flight warmup task is not garbage collected.
_warmups: set[asyncio.Task] = set()


def _warm_fillers(tts, voice: str):
    """Pre-synthesize this voice's fillers in the background.

    Without them get_filler() returns None and the call loses the instant
    "Dạ vâng ạ" that hides most of the pipeline latency.
    """
    async def run():
        try:
            await tts.presynthesize_fillers(FILLER_PHRASES, voice=voice)
        except Exception as e:
            logger.warning(f"Filler warmup for '{voice}' failed: {e}")

    task = asyncio.create_task(run())
    _warmups.add(task)
    task.add_done_callback(_warmups.discard)


async def _flush_on_disconnect(session: CallSession):
    """Chốt phiên khi trình duyệt ngắt kết nối. Luôn await, nên luôn chạy xong.

    Đi qua `call_session_service.chot_phien` chứ không chỉ `save_session`: có
    thế thì phiên chat thử cũng được chấm chất lượng và tóm tắt như cuộc gọi
    thật, và hiện đúng trong trang Báo cáo. Trước đây chỉ lưu lịch sử, nên mọi
    phiên mở từ trình duyệt đều là dòng trống không lọc được.
    """
    from backend.main import app_state
    from backend.services import call_session_service as css

    try:
        await css.chot_phien(app_state, session)
    except Exception as e:
        logger.error(f"Chốt phiên khi ngắt kết nối hỏng: {e}")
        try:
            await save_session(session, ended=True)   # ít nhất giữ lại bản ghi
        except Exception:
            pass


@router.websocket("/ws/campaign/{campaign_id}")
async def websocket_campaign(websocket: WebSocket, campaign_id: str):
    """Đẩy tiến độ chiến dịch lên giao diện theo thời gian thực.

    Chỉ đẩy khi có thay đổi (bắt đầu một cuộc, kết thúc một cuộc) chứ không đẩy
    theo nhịp: chiến dịch chạy vài tiếng, đẩy mỗi giây là vài chục nghìn tin
    nhắn cho một con số hầu như đứng yên.
    """
    from backend.services.campaign_runner import campaigns

    await websocket.accept()
    runner = campaigns.get(campaign_id)
    if runner is None:
        await websocket.send_json({
            "type": "loi",
            "message": "Chiến dịch này không chạy — bấm Bắt đầu trước",
        })
        await websocket.close()
        return

    runner.theo_doi(websocket)
    try:
        await websocket.send_json({"type": "tien_do", **runner.progress()})
        while True:
            # Không mong nhận gì từ client; recv() ở đây chỉ để phát hiện ngắt
            # kết nối. Không có nó thì server giữ WebSocket chết mãi mãi.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS chiến dịch {campaign_id} đóng: {e}")
    finally:
        runner.thoi_theo_doi(websocket)


@router.websocket("/ws/call/{session_id}")
async def websocket_call(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time voice conversation."""
    from backend.main import app_state

    await websocket.accept()
    logger.info(f"WebSocket connected: session={session_id}")

    session = app_state.sessions.get(session_id)
    if not session:
        session = app_state.sessions.create(customer_name="Khách hàng")
        session_id = session.session_id

    await websocket.send_json({
        "type": "connected",
        "session_id": session.session_id,
    })

    # Lượt chạy trong task riêng thay vì await thẳng trong vòng lặp. Trước đây
    # await thẳng nên vòng lặp không đọc được tin tiếp theo cho tới khi lượt cũ
    # xong: khách gửi tin mới thì lượt cũ vẫn sinh nốt tiếng và gửi đi hết. Đo
    # được 3 mảnh (~8 giây tiếng) tới nơi sau khi khách đã gửi tin mới, và khách
    # phải ngồi nghe hết lượt cũ mới tới lượt mình.
    luot_task: asyncio.Task | None = None

    async def huy_luot_cu():
        """Dừng lượt đang chạy. Chờ nó dừng hẳn rồi mới cho lượt mới bắt đầu -
        hai lượt cùng ghi vào một WebSocket sẽ trộn lẫn mảnh audio của nhau.

        Nếu vừa có cắt lời (`yeu_cau_huy` đang bật) thì CHỜ lượt cũ tự dừng ở
        điểm an toàn thay vì cắt cứng ngay: cắt cứng lúc STT chưa xong là mất
        luôn câu khách vừa nói, không còn gì để ghép vào câu sắp tới. Khách nói
        đè rồi nói tiếp một mạch thì `audio_end` của lượt mới tới chỉ vài mili
        giây sau `barge_in` - không chờ ở đây là hỏng đúng trường hợp thường gặp
        nhất.
        """
        nonlocal luot_task
        if luot_task and not luot_task.done():
            if session.yeu_cau_huy:
                try:
                    await asyncio.wait_for(asyncio.shield(luot_task), timeout=2.0)
                except asyncio.CancelledError:
                    # Qua shield thì lỗi này có hai nguồn: lượt cũ bị cắt (bỏ
                    # qua, đi tiếp), hay chính vòng nhận tin đang bị dừng (phải
                    # để nó lan ra). CancelledError kế thừa BaseException nên
                    # `except Exception` không bắt được - phải ghi riêng.
                    if not luot_task.cancelled():
                        raise
                except (asyncio.TimeoutError, Exception):
                    pass
            if not luot_task.done():
                luot_task.cancel()
                try:
                    await luot_task
                except (asyncio.CancelledError, Exception):
                    pass
                # Cắt cứng thật thì vẫn giữ những gì đã kịp vào lịch sử.
                if session.yeu_cau_huy:
                    session.danh_dau_bi_cat()
        luot_task = None

    async def chay_luot(coro):
        """Bọc lỗi giống hệt khối try/except cũ, vì lỗi trong task không còn nổi
        lên vòng lặp nữa."""
        try:
            await coro
        except asyncio.CancelledError:
            logger.info("Lượt bị huỷ vì khách gửi tin mới")
            raise
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
                await websocket.send_json(
                    {"type": "turn_complete", "full_response": "", "metrics": {}}
                )
            except Exception:
                pass   # socket đã đóng

    async def bat_dau_luot(data: dict, coro_factory):
        nonlocal luot_task
        await huy_luot_cu()
        # Dọn cờ trước khi mở lượt mới: nếu cờ được đặt đúng lúc lượt cũ vừa kết
        # thúc thì không ai tiêu thụ, để nguyên là lượt mới vừa sinh đã tự huỷ.
        session.yeu_cau_huy = False
        # Số lượt do client cấp: hai bên không cần đồng bộ đếm, client chỉ việc
        # so số nó gửi đi với số nhận về.
        session.turn_id = int(data.get("turn_id", session.turn_id + 1))
        luot_task = asyncio.create_task(chay_luot(coro_factory()))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "audio":
                audio_bytes = base64.b64decode(data.get("data", ""))
                await bat_dau_luot(data, lambda: app_state.pipeline.process_turn(
                    audio_bytes=audio_bytes, session=session, ws=websocket,
                ))

            # --- Luồng streaming: client đẩy PCM 16kHz ngay trong lúc khách nói ---
            # Trước đây client thu xong hết mới giải mã webm rồi gửi một cục, nên
            # toàn bộ thời gian mã hoá + tải lên nằm SAU khi khách dứt lời. Giờ nó
            # chạy song song với lời nói.
            elif msg_type == "audio_chunk":
                try:
                    session.push_audio(base64.b64decode(data.get("data", "")))
                    # Đoán trước: có đủ tiếng thì phiên âm tạm + nạp sẵn RAG.
                    await app_state.pipeline.speculate(session)
                except Exception as e:
                    logger.warning(f"audio_chunk lỗi: {e}")

            elif msg_type == "audio_end":
                hut = session.do_hut_tieng()
                if hut:
                    muc = logger.warning if hut["hut_pct"] >= 10 else logger.info
                    muc("Tiếng nhận được %.2fs / khách nói %.2fs -> hụt %.1f%%",
                        hut["giay_nhan"], hut["giay_thuc"], hut["hut_pct"])
                audio_bytes = session.take_audio()
                if not audio_bytes:
                    await websocket.send_json({"type": "turn_complete", "full_response": "", "metrics": {}})
                else:
                    await bat_dau_luot(data, lambda: app_state.pipeline.process_turn(
                        audio_bytes=audio_bytes, session=session, ws=websocket,
                    ))

            # Khách nói đè lên trong lúc AI đang trả lời. Client phát hiện tại chỗ
            # (nhanh hơn nhiều so với để server dò, và chính client mới là bên
            # đang phát tiếng) rồi báo lên đây để dừng sinh tiếp.
            elif msg_type == "barge_in":
                if luot_task and not luot_task.done():
                    # Xin dừng bằng cờ, KHÔNG cắt cứng: cắt giữa lúc STT chưa
                    # xong là mất luôn câu khách vừa nói, không còn gì để ghép.
                    # Pipeline thấy cờ ở điểm an toàn sẽ tự kết thúc và gửi
                    # turn_complete kèm bi_cat_loi. Tiếng thì client đã tự dừng.
                    session.yeu_cau_huy = True
                    logger.info("Khách cắt lời AI - xin dừng lượt đang chạy")

                    async def cat_cung_neu_khong_dung(t=luot_task):
                        try:
                            await asyncio.wait_for(asyncio.shield(t), timeout=3.0)
                        except asyncio.TimeoutError:
                            logger.warning("Lượt không tự dừng sau 3s - cắt cứng")
                            await huy_luot_cu()
                            if session.yeu_cau_huy:
                                session.yeu_cau_huy = False
                                session.danh_dau_bi_cat()
                                try:
                                    await websocket.send_json({
                                        "type": "turn_complete", "full_response": "",
                                        "metrics": {"bi_cat_loi": True}})
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    asyncio.create_task(cat_cung_neu_khong_dung())

            elif msg_type == "text":
                text = data.get("text", "")
                if text.strip():
                    await bat_dau_luot(data, lambda: app_state.pipeline.process_text_turn(
                        text=text, session=session, ws=websocket,
                    ))

            # Khách đang gõ, chưa bấm gửi: nạp sẵn RAG cho câu dở dang. Đối xứng
            # với "audio_chunk" -> speculate() của đường thoại.
            elif msg_type == "prefetch":
                text = data.get("text", "")
                if text.strip():
                    try:
                        await app_state.pipeline.prefetch_text(text, session)
                    except Exception as e:
                        logger.debug(f"prefetch lỗi (bỏ qua): {e}")

            elif msg_type == "set_session":
                session.customer_name = data.get("customer_name", session.customer_name)
                session.product = data.get("product", session.product)
                # Số điện thoại: cuộc gọi thật lấy từ danh bạ, còn ở trang Hội
                # thoại thì không có đường nào đặt - mà thiếu nó thì công cụ
                # `tra_ho_so_khach` không tra được và không thử được tính năng.
                if data.get("phone"):
                    session.phone = str(data["phone"]).strip()
                await websocket.send_json({"type": "session_updated", "session": session.to_dict()})

            elif msg_type == "set_voice":
                voice_name = data.get("voice_name", "default")
                voices = app_state.tts.list_voices()
                voice = next((v for v in voices if v["name"] == voice_name), None)
                if voice:
                    # Per-session only: another call on another line keeps its
                    # own voice. Load the reference now so the first turn does
                    # not pay for it.
                    resolved = await app_state.tts.ensure_voice(voice_name)
                    session.voice_name = resolved
                    _warm_fillers(app_state.tts, resolved)
                    await websocket.send_json({"type": "voice_updated", "voice": resolved})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Runs on every exit path, including an unexpected error above.
        # Huỷ lượt còn đang chạy: khách đóng tab giữa chừng mà không dừng thì nó
        # sinh nốt tiếng rồi ghi vào socket đã đóng, vừa phí GPU vừa đẻ lỗi.
        await huy_luot_cu()
        await _flush_on_disconnect(session)
