"""Bộ quay số tự động: chạy một chiến dịch từ đầu đến cuối mà không cần người bấm.

Đây là chỗ ba mục của Điều 6 gặp nhau:
  - B1/B2  chọn kịch bản + nạp danh bạ  -> đọc từ `campaigns` và `contacts`
  - B3     gọi lại / khung giờ chạy      -> `contacts_db.finish_attempt` + `khung_gio`
  - Báo cáo                              -> mỗi cuộc gọi đóng lại thành một phiên

Kiến trúc: MỘT task cho mỗi chiến dịch, bên trong đẻ ra `concurrency` worker,
mỗi worker giữ một máy điện thoại. Không phải một task cho mỗi số — làm thế thì
"tạm dừng" phải đi tìm hàng trăm task để huỷ, và `concurrency` chỉ còn là lời
khuyên chứ không phải hàng rào.

Máy điện thoại là tài nguyên độc chiếm: một máy chỉ gọi được một cuộc tại một
thời điểm, nên số worker luôn bị chặn trên bởi số máy đang rảnh.
"""

import asyncio
import json
import logging
import time
from datetime import datetime

from backend.models import contacts_db, devices_db
from backend.services import (
    call_session_service, dialer_service, khung_gio, transfer_service,
)

logger = logging.getLogger(__name__)

# Thăm dò trạng thái cuộc gọi mỗi bao nhiêu giây. 0.8s là đủ nhanh để không bỏ
# lỡ một cuộc gọi ngắn, mà mỗi lần thăm là một lệnh adb (~50-150ms) nên nhanh
# hơn nữa thì chỉ tổ nghẽn cầu USB khi chạy nhiều máy.
_NHIP_THAM = 0.8

# Đổ chuông quá lâu coi như không ai bắt máy. Nhà mạng VN thường tự chuyển hộp
# thư thoại quanh giây thứ 25-30.
_CHO_BAT_MAY_S = 35.0

# Trần thời lượng một cuộc gọi. Không có trần thì một cuộc treo (khách để máy
# đó rồi bỏ đi) giữ máy điện thoại vô hạn và chiến dịch đứng im.
_TRAN_CUOC_GOI_S = 600.0

# Nghỉ giữa hai cuộc trên cùng một máy: để tổng đài kịp giải phóng kênh, và để
# không tạo ra chuỗi cuộc gọi đều tăm tắp trông như máy quét.
_NGHI_GIUA_CUOC_S = 3.0


class CampaignRunner:
    """Chạy một chiến dịch. Tạo xong phải gọi `start()`."""

    def __init__(self, campaign_id: str, app_state):
        self.campaign_id = campaign_id
        self.app_state = app_state
        self.task: asyncio.Task | None = None
        self._dung = asyncio.Event()      # bật = dừng hẳn
        self._tam_dung = asyncio.Event()  # bật = tạm dừng, không nhận số mới
        self.trang_thai = "chua_chay"     # chua_chay|dang_chay|tam_dung|xong|loi
        self.ly_do = ""
        self.moc_mo_lai: float | None = None
        self.dang_goi: dict[str, dict] = {}   # device_id -> {phone, name, tu_luc}
        self.da_goi = 0
        self.da_nghe_may = 0
        self.bat_dau_luc: float | None = None
        self._nghe: set = set()           # các WebSocket đang xem tiến độ

    # --- vòng đời -------------------------------------------------------

    async def start(self) -> tuple[bool, str]:
        if self.task and not self.task.done():
            return False, "Chiến dịch này đang chạy rồi"

        campaign = await contacts_db.get_campaign(self.campaign_id)
        if campaign is None:
            return False, "Chiến dịch không tồn tại"

        thiet_bi = await self._lay_thiet_bi(campaign)
        if not thiet_bi:
            return False, (
                "Không có thiết bị nào để gọi — thêm máy ở trang Thiết bị, "
                "hoặc chọn máy cho chiến dịch này"
            )

        tong = await contacts_db.pending_summary(self.campaign_id)
        if tong["san_sang"] == 0 and tong["cho_goi_lai"] == 0:
            return False, "Chiến dịch không còn số nào để gọi"

        self._dung.clear()
        self._tam_dung.clear()
        self.bat_dau_luc = time.time()
        self.trang_thai = "dang_chay"
        self.ly_do = ""
        self.task = asyncio.create_task(self._chay(), name=f"campaign-{self.campaign_id}")
        await contacts_db.update_campaign(
            self.campaign_id, status="running", started_at=time.time(), paused_at=None
        )
        logger.info(
            f"[chiến dịch {self.campaign_id}] bắt đầu — {len(thiet_bi)} máy, "
            f"{tong['san_sang']} số sẵn sàng"
        )
        return True, f"Đã bắt đầu với {len(thiet_bi)} máy"

    async def pause(self) -> tuple[bool, str]:
        if self.trang_thai != "dang_chay":
            return False, "Chiến dịch không ở trạng thái đang chạy"
        self._tam_dung.set()
        self.trang_thai = "tam_dung"
        await contacts_db.update_campaign(
            self.campaign_id, status="paused", paused_at=time.time()
        )
        # Cuộc gọi đang nói được nói nốt: cắt ngang giữa câu là cách chắc chắn
        # nhất để khách cúp máy và ghi nhận sai kết quả.
        return True, "Đã tạm dừng — các cuộc đang gọi sẽ nói nốt rồi mới dừng"

    async def resume(self) -> tuple[bool, str]:
        if self.task is None or self.task.done():
            return await self.start()
        self._tam_dung.clear()
        self.trang_thai = "dang_chay"
        await contacts_db.update_campaign(self.campaign_id, status="running", paused_at=None)
        return True, "Đã tiếp tục"

    async def stop(self) -> tuple[bool, str]:
        self._dung.set()
        self._tam_dung.clear()
        if self.task and not self.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning(f"[chiến dịch {self.campaign_id}] không tự dừng sau 15s")
                self.task.cancel()
            except Exception:
                pass
        self.trang_thai = "xong" if self.trang_thai != "loi" else "loi"
        await contacts_db.update_campaign(self.campaign_id, status="paused")
        return True, "Đã dừng"

    # --- vòng chạy chính ------------------------------------------------

    async def _chay(self):
        try:
            campaign = await contacts_db.get_campaign(self.campaign_id)
            thiet_bi = await self._lay_thiet_bi(campaign)
            so_worker = max(1, min(int(campaign.get("concurrency") or 1), len(thiet_bi)))

            workers = [
                asyncio.create_task(self._worker(thiet_bi[i]), name=f"cd-worker-{i}")
                for i in range(so_worker)
            ]
            await asyncio.gather(*workers, return_exceptions=True)

            if not self._dung.is_set():
                self.trang_thai = "xong"
                await contacts_db.update_campaign(self.campaign_id, status="done")
                logger.info(
                    f"[chiến dịch {self.campaign_id}] xong — gọi {self.da_goi} số, "
                    f"{self.da_nghe_may} nghe máy"
                )
                await self._bao_xong()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.trang_thai = "loi"
            self.ly_do = str(e)
            logger.error(f"[chiến dịch {self.campaign_id}] hỏng: {e}", exc_info=True)
        finally:
            await self._day_tien_do()

    async def _worker(self, device: dict):
        """Một máy điện thoại, gọi hết số này tới số khác."""
        device_id = device["device_id"]
        while not self._dung.is_set():
            # Nạp lại cấu hình mỗi vòng: người dùng sửa khung giờ hoặc chính sách
            # gọi lại giữa chừng thì phải ăn ngay, không đợi khởi động lại.
            campaign = await contacts_db.get_campaign(self.campaign_id)
            if campaign is None:
                return

            ngu = await self._cho_toi_gio(campaign)
            if ngu is None:      # hết hạn chiến dịch
                return
            if ngu > 0:
                await self._doi(ngu)
                continue

            if self._tam_dung.is_set():
                await self._doi(2.0)
                continue

            contact = await contacts_db.claim_next(self.campaign_id)
            if contact is None:
                tong = await contacts_db.pending_summary(self.campaign_id)
                if tong["cho_goi_lai"] == 0:
                    return       # hết sạch số -> worker này nghỉ
                # Còn số nhưng chưa tới hạn gọi lại: ngủ tới mốc gần nhất.
                cho = max(5.0, min(300.0, (tong["moc_ke_tiep"] or 0) - time.time()))
                await self._doi(cho)
                continue

            try:
                await self._goi_mot_so(contact, device, campaign)
            except Exception as e:
                logger.error(
                    f"[chiến dịch {self.campaign_id}] lỗi khi gọi {contact['phone']}: {e}",
                    exc_info=True,
                )
                # Số đang mắc kẹt ở 'calling' — trả nó về hàng đợi, đừng để mất.
                await contacts_db.finish_attempt(
                    contact["contact_id"], "no_answer", campaign, note=f"Lỗi hệ thống: {e}"
                )
            finally:
                self.dang_goi.pop(device_id, None)

            await self._doi(_NGHI_GIUA_CUOC_S)

    async def _cho_toi_gio(self, campaign: dict) -> float | None:
        """0 = gọi được ngay, >0 = số giây phải đợi, None = hết hạn chiến dịch."""
        tz = khung_gio.mui_gio(campaign.get("timezone"))
        bay_gio = datetime.now(tz)
        khung = khung_gio.doc_khung(campaign.get("call_windows"))
        trang_thai, moc, ly_do = khung_gio.trang_thai(
            bay_gio, khung, campaign.get("start_date", ""), campaign.get("end_date", "")
        )

        if trang_thai == "chay":
            self.moc_mo_lai = None
            return 0.0
        if trang_thai == "het_han":
            self.ly_do = ly_do
            self.trang_thai = "xong"
            await contacts_db.update_campaign(self.campaign_id, status="done")
            logger.info(f"[chiến dịch {self.campaign_id}] {ly_do}")
            return None

        self.ly_do = ly_do
        self.moc_mo_lai = moc.timestamp() if moc else None
        return khung_gio.con_bao_lau(bay_gio, moc)

    async def _doi(self, giay: float):
        """Ngủ, nhưng tỉnh ngay khi có lệnh dừng."""
        try:
            await asyncio.wait_for(self._dung.wait(), timeout=max(0.1, giay))
        except asyncio.TimeoutError:
            pass

    # --- một cuộc gọi ---------------------------------------------------

    async def _goi_mot_so(self, contact: dict, device: dict, campaign: dict):
        from backend.services.phone_call_service import phone_calls

        phone = contact["phone"]
        device_id = device["device_id"]

        # Dựng phiên qua hàm dùng chung: bộ quay số tự động, nút "Gọi" tay và bot
        # nhận cuộc gọi vào phải cho ra phiên GIỐNG HỆT nhau. Xem
        # services/call_session_service.py.
        session = await call_session_service.mo_phien(
            self.app_state, contact=contact, campaign=campaign, direction="outbound",
        )

        self.dang_goi[device_id] = {
            "phone": phone, "name": contact.get("name", ""),
            "session_id": session.session_id, "tu_luc": time.time(),
        }
        await self._day_tien_do()

        ok, detail = await dialer_service.dial(device, phone)
        await devices_db.mark_status(device_id, "online" if ok else "error", "" if ok else detail)
        await contacts_db.record_attempt(
            contact["contact_id"], device_id=device_id, session_id=session.session_id,
            status="dialed" if ok else "failed", detail=detail, contact_status="calling",
        )
        self.da_goi += 1

        if not ok:
            session.outcome = "failed"
            await self._dong_phien(session, "failed")
            await contacts_db.finish_attempt(contact["contact_id"], "no_answer", campaign, detail)
            return

        # Máy trong phone farm: nối đường tiếng để AI nói chuyện được. Máy khác
        # (gateway HTTP, tổng đài) thì hệ thống chỉ bấm số, tiếng đi đường riêng.
        co_tieng = device.get("kind") == "adb" and bool(device.get("address"))
        if co_tieng:
            # PHẢI GIỐNG HỆT đường gọi một số ở api/phones.py. Trước đây chỗ này
            # thiếu cả `cho_bat_may` lẫn `chao_khi_bat_may`, và mất ba thứ:
            #
            # 1. ĐƯỜNG TIÊM không bao giờ được đặt. `set_uplink_injection` chỉ
            #    nằm trong `chao_khi_bat_may`. Đường tiêm có tác dụng TẮT MICRO
            #    rồi thay bằng tiếng AI - không đặt thì micro vẫn bật và khách
            #    nghe tiếng nền của phòng đặt máy. Người dùng báo đúng triệu
            #    chứng: "gọi ra tiếng gió".
            # 2. KHÔNG CHÀO. Khách bắt máy xong nghe im lặng.
            # 3. NGHE NGAY TỪ LÚC ĐỔ CHUÔNG. `tam_dung_nghe = cho_bat_may`, để
            #    mặc định False là vòng thu phiên âm tiếng hồi chuông và đốt mấy
            #    lượt rác trước khi khách kịp nói.
            ok_voice, msg_voice = await phone_calls.start(
                device["address"], self.app_state.pipeline, session,
                ghi_am=bool(campaign.get("record_calls", 1)),
                cho_bat_may=True,
            )
            if not ok_voice:
                logger.warning(f"[{phone}] không nối được đường tiếng: {msg_voice}")
            else:
                # Chạy NỀN: hàm này chờ tới 45s cho khách nhấc máy, mà vòng
                # `_cho_ket_qua` bên dưới cũng phải chạy song song để bắt trạng
                # thái cuộc gọi. Nó tự thoát khi phiên bị dừng.
                asyncio.create_task(
                    phone_calls.chao_khi_bat_may(device["address"]))

        try:
            ket_qua = await self._cho_ket_qua(device, session, campaign)
        finally:
            if co_tieng:
                await phone_calls.stop(device["address"])
            # Cúp máy dù kết quả gì: bỏ quên một cuộc đang mở thì máy đó không
            # gọi được số tiếp theo, và chiến dịch đứng lại ở đúng một máy.
            await dialer_service.hangup(device)

        session.outcome = ket_qua
        await self._dong_phien(session, ket_qua)
        await contacts_db.finish_attempt(contact["contact_id"], ket_qua, campaign)

        if ket_qua == "done":
            self.da_nghe_may += 1
        await self._bao_ket_thuc_cuoc(session, contact, ket_qua)
        await self._day_tien_do()

    async def _cho_ket_qua(self, device: dict, session, campaign: dict) -> str:
        """Bản của bộ quay số tự động - chỉ nối lệnh dừng của chiến dịch vào."""
        return await cho_ket_qua(device, session, campaign, self._dung)

    async def _dong_phien(self, session, ket_qua: str):
        await call_session_service.chot_phien(self.app_state, session, ket_qua)

    # --- thông báo ------------------------------------------------------

    async def _bao_ket_thuc_cuoc(self, session, contact: dict, ket_qua: str):
        if ket_qua != "done":
            return
        try:
            from backend.services import notify_service
            await notify_service.bao_cuoc_goi(session, contact)
        except Exception as e:
            # Gửi tin nhắn hỏng KHÔNG được làm dừng chiến dịch.
            logger.warning(f"Không gửi được thông báo cuộc gọi: {e}")

    async def _bao_xong(self):
        try:
            from backend.services import notify_service
            await notify_service.bao_chien_dich_xong(self.campaign_id, self.progress())
        except Exception as e:
            logger.warning(f"Không gửi được thông báo kết thúc chiến dịch: {e}")

    # --- tiến độ --------------------------------------------------------

    def progress(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "trang_thai": self.trang_thai,
            "ly_do": self.ly_do,
            "moc_mo_lai": self.moc_mo_lai,
            "da_goi": self.da_goi,
            "da_nghe_may": self.da_nghe_may,
            "ty_le_nghe_may": round(self.da_nghe_may / self.da_goi * 100, 1) if self.da_goi else 0.0,
            "dang_goi": list(self.dang_goi.values()),
            "bat_dau_luc": self.bat_dau_luc,
        }

    def theo_doi(self, ws):
        self._nghe.add(ws)

    def thoi_theo_doi(self, ws):
        self._nghe.discard(ws)

    async def _day_tien_do(self):
        if not self._nghe:
            return
        payload = {"type": "tien_do", **self.progress()}
        for ws in list(self._nghe):
            try:
                await ws.send_json(payload)
            except Exception:
                self._nghe.discard(ws)

    # --- phụ trợ --------------------------------------------------------

    @staticmethod
    async def _lay_thiet_bi(campaign: dict) -> list[dict]:
        """Các máy chiến dịch này được dùng, chỉ lấy máy đang online."""
        tat_ca = await devices_db.list_devices()
        chon = []
        raw = (campaign or {}).get("device_ids") or ""
        if raw:
            try:
                muon = set(json.loads(raw))
            except (ValueError, TypeError):
                muon = set()
            chon = [d for d in tat_ca if d["device_id"] in muon]
        if not chon:
            mac_dinh = await devices_db.get_default_device()
            chon = [mac_dinh] if mac_dinh else tat_ca
        return [d for d in chon if d and d.get("status") != "offline"]


class CampaignManager:
    """Giữ các chiến dịch đang chạy. Một chiến dịch một runner."""

    def __init__(self):
        self._runners: dict[str, CampaignRunner] = {}

    def get(self, campaign_id: str) -> CampaignRunner | None:
        return self._runners.get(campaign_id)

    def progress(self, campaign_id: str) -> dict | None:
        runner = self._runners.get(campaign_id)
        return runner.progress() if runner else None

    def all_progress(self) -> list[dict]:
        return [r.progress() for r in self._runners.values()]

    async def start(self, campaign_id: str, app_state) -> tuple[bool, str]:
        runner = self._runners.get(campaign_id)
        if runner and runner.task and not runner.task.done():
            if runner.trang_thai == "tam_dung":
                return await runner.resume()
            return False, "Chiến dịch này đang chạy rồi"
        runner = CampaignRunner(campaign_id, app_state)
        self._runners[campaign_id] = runner
        return await runner.start()

    async def pause(self, campaign_id: str) -> tuple[bool, str]:
        runner = self._runners.get(campaign_id)
        if runner is None:
            return False, "Chiến dịch này không chạy"
        return await runner.pause()

    async def resume(self, campaign_id: str, app_state) -> tuple[bool, str]:
        runner = self._runners.get(campaign_id)
        if runner is None:
            return await self.start(campaign_id, app_state)
        return await runner.resume()

    async def stop(self, campaign_id: str) -> tuple[bool, str]:
        runner = self._runners.pop(campaign_id, None)
        if runner is None:
            return False, "Chiến dịch này không chạy"
        return await runner.stop()

    async def stop_all(self):
        """Tắt máy: dừng mọi chiến dịch để không bỏ số nào ở trạng thái 'calling'."""
        for campaign_id in list(self._runners):
            try:
                await self.stop(campaign_id)
            except Exception as e:
                logger.warning(f"Không dừng được chiến dịch {campaign_id}: {e}")


campaigns = CampaignManager()


async def _doi_hoac_dung(dung: asyncio.Event, giay: float):
    """Ngủ, nhưng tỉnh ngay khi có lệnh dừng."""
    try:
        await asyncio.wait_for(dung.wait(), timeout=max(0.1, giay))
    except asyncio.TimeoutError:
        pass


async def cho_ket_qua(device: dict, session, campaign: dict | None,
                      dung: asyncio.Event) -> str:
    """Theo dõi cuộc gọi tới lúc kết thúc. Trả về done|no_answer|busy|voicemail.

    Máy ADB đọc được trạng thái chi tiết nên phân biệt được đổ chuông với đã
    nhấc máy. Thiết bị khác không đọc được gì, nên chỉ chờ hết thời gian rồi
    báo 'done' — người dùng sửa lại kết quả bằng tay ở trang Danh bạ.

    HÀM DÙNG CHUNG cho cả hai đường gọi, và phải như thế.

    Tới 2026-08-12 đây còn là phương thức riêng của bộ quay số tự động, còn nút
    "Gọi" ở trang Danh bạ (`phones._dial_contact`) thì quay số xong là trả về
    luôn, không ai trông cuộc gọi nữa. Khách tắt máy thì ba thứ cùng kẹt:
    trạng thái số đứng mãi ở "đang gọi"; phiên không được chốt nên cuộc gọi
    không có dòng nào trong Báo cáo; và nặng nhất là CẦU TIẾNG cùng đường tiêm
    uplink vẫn mở - máy đó không gọi được số tiếp theo.

    `campaign` được phép là None: gọi tay ngoài chiến dịch thì không có chính
    sách hộp thư thoại nào để áp.
    """
    from backend.services import adb_service

    if device.get("kind") != "adb":
        await _doi_hoac_dung(dung, min(_TRAN_CUOC_GOI_S, 60.0))
        return "done"

    serial = device["address"]
    t0 = time.time()
    da_nghe = False

    while not dung.is_set():
        ma, mo_ta = await adb_service.precise_call_state(serial)

        if ma == 1:                       # đang nói chuyện
            if not da_nghe:
                da_nghe = True
                logger.info(f"[{session.phone}] khách đã bắt máy")
        elif ma in (0, 7, 8):             # rảnh / vừa ngắt / đang ngắt
            if da_nghe:
                break
            # Ngắt mà chưa từng đổ chuông và chưa tới 8 giây: gần như luôn là
            # máy bận hoặc thuê bao không liên lạc được. Đổ chuông rồi mới
            # ngắt thì là khách chủ động không nghe.
            if time.time() - t0 < 8.0:
                return "busy"
            return "no_answer"
        elif ma == -1:
            # Không đọc được trạng thái (ROM cũ, rút cáp). Không đoán bừa:
            # chờ hết giờ rồi báo no_answer còn hơn báo 'done' cho một cuộc
            # chưa chắc đã kết nối.
            logger.debug(f"[{session.phone}] không đọc được trạng thái: {mo_ta}")

        if da_nghe:
            # Bot bí / khách đòi gặp người thật -> nối máy cho chuyên viên.
            # Kiểm ở đây vì chỉ vòng này mới cầm được thiết bị.
            ly_do = transfer_service.can_chuyen_tiep(session)
            if ly_do:
                from backend.services.phone_call_service import phone_calls
                ok_ct, chi_tiet = await transfer_service.chuyen_tiep(
                    session, device, phone_calls.get(serial), ly_do
                )
                if ok_ct:
                    return "done"     # cuộc gọi giờ thuộc về chuyên viên
                logger.info(f"[{session.phone}] không nối máy được: {chi_tiet}")

            # Hộp thư thoại: bộ dò đặt cờ này từ trong đường tiếng (F7).
            if session.la_hop_thu_thoai:
                if ((campaign or {}).get("on_voicemail") or "hangup") == "hangup":
                    logger.info(f"[{session.phone}] vào hộp thư thoại — cúp máy")
                    return "voicemail"
            if time.time() - t0 > _TRAN_CUOC_GOI_S:
                logger.warning(f"[{session.phone}] quá {_TRAN_CUOC_GOI_S:.0f}s — cúp máy")
                break
        elif time.time() - t0 > _CHO_BAT_MAY_S:
            return "no_answer"

        await asyncio.sleep(_NHIP_THAM)

    if not da_nghe:
        return "no_answer"
    # Khách bắt máy nhưng không nói câu nào: vẫn là cuộc gọi có kết nối, để
    # phần chất lượng (F14) phân loại tiếp chứ đừng gộp vào 'không nghe máy'.
    return "voicemail" if session.la_hop_thu_thoai else "done"
