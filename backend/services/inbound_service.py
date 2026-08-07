"""Bot nhận cuộc gọi đến (Điều 6: "Các yêu cầu cần đạt được của bot tiếp nhận
cuộc gọi vào — giống như bot gọi ra, tiếp nhận cuộc gọi, giao tiếp tự nhiên").

Một task theo dõi cho mỗi máy đã bật "tự nhận cuộc gọi". Thấy máy đổ chuông thì
đợi vài giây, bắt máy, mở phiên AI với kịch bản inbound rồi cắm vào đúng cầu
tiếng mà chiều gọi ra đang dùng.

KHÁC BIỆT DUY NHẤT so với gọi ra: AI KHÔNG NÓI TRƯỚC. Người ta gọi tới là họ
đang có việc cần nói; bot chào một câu ngắn rồi im để khách trình bày. Bot gọi
ra thì ngược lại — nó là bên chủ động nên phải mở lời.

Vì sao đợi vài giây rồi mới bắt máy: bắt ngay hồi chuông đầu nghe rất máy móc,
và phía tổng đài nhiều khi chưa nối xong đường tiếng ở thời điểm đó.
"""

import asyncio
import logging
import time

from backend.models import contacts_db, devices_db
from backend.services import adb_service

logger = logging.getLogger(__name__)

# Nhịp hỏi trạng thái máy. Mỗi lần là một lệnh adb (~50-150ms); 1 giây đủ nhanh
# để không lỡ một cuộc gọi (chuông đổ ít nhất 20 giây) mà không nghẽn cầu USB
# khi theo dõi cả chục máy.
_NHIP_S = 1.0

# Trần một cuộc gọi vào, giống chiều gọi ra.
_TRAN_CUOC_GOI_S = 600.0


class BoNhanCuocGoi:
    """Theo dõi một máy và tự bắt máy khi có cuộc gọi đến."""

    def __init__(self, device: dict, app_state):
        self.device = device
        self.app_state = app_state
        self.serial = device.get("address", "")
        self.task: asyncio.Task | None = None
        self._dung = asyncio.Event()
        self.dang_nghe = False
        self.cuoc_hien_tai: dict | None = None
        self.da_nhan = 0
        self.loi = ""

    async def start(self) -> tuple[bool, str]:
        if self.task and not self.task.done():
            return False, "Máy này đã đang theo dõi cuộc gọi đến"
        if self.device.get("kind") != "adb" or not self.serial:
            return False, "Chỉ máy trong phone farm (ADB) mới tự nhận cuộc gọi được"
        self._dung.clear()
        self.task = asyncio.create_task(self._theo_doi(), name=f"inbound-{self.serial}")
        self.dang_nghe = True
        logger.info(f"[gọi vào] bắt đầu theo dõi máy {self.device.get('name')}")
        return True, "Đã bật tự nhận cuộc gọi đến"

    async def stop(self) -> tuple[bool, str]:
        self._dung.set()
        self.dang_nghe = False
        if self.task and not self.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=10.0)
            except asyncio.TimeoutError:
                self.task.cancel()
            except Exception:
                pass
        return True, "Đã tắt tự nhận cuộc gọi đến"

    def trang_thai(self) -> dict:
        return {
            "device_id": self.device.get("device_id"),
            "name": self.device.get("name"),
            "serial": self.serial,
            "dang_nghe": self.dang_nghe,
            "da_nhan": self.da_nhan,
            "cuoc_hien_tai": self.cuoc_hien_tai,
            "loi": self.loi,
        }

    # --- vòng theo dõi ---------------------------------------------------

    async def _theo_doi(self):
        try:
            while not self._dung.is_set():
                trang_thai, chi_tiet = await adb_service.call_state(self.serial)
                if trang_thai == "ringing":
                    try:
                        await self._nhan_cuoc(chi_tiet)
                    except Exception as e:
                        self.loi = f"Lỗi khi nhận cuộc gọi: {e}"
                        logger.error(f"[gọi vào] {self.loi}", exc_info=True)
                    finally:
                        self.cuoc_hien_tai = None
                elif trang_thai == "unknown":
                    self.loi = chi_tiet
                await self._doi(_NHIP_S)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.loi = f"Vòng theo dõi dừng: {e}"
            logger.error(f"[gọi vào] {self.loi}", exc_info=True)
        finally:
            self.dang_nghe = False

    async def _doi(self, giay: float):
        try:
            await asyncio.wait_for(self._dung.wait(), timeout=max(0.1, giay))
        except asyncio.TimeoutError:
            pass

    async def _nhan_cuoc(self, _chi_tiet: str):
        from backend.services.phone_call_service import phone_calls

        so_goi_den = await adb_service.incoming_number(self.serial)
        logger.info(f"[gọi vào] máy {self.serial} đổ chuông từ {so_goi_den or 'số ẩn'}")

        cho = float(self.device.get("inbound_delay_s") or 2.0)
        await self._doi(cho)
        if self._dung.is_set():
            return

        # Khách có thể đã cúp trong lúc mình đợi.
        trang_thai, _ = await adb_service.call_state(self.serial)
        if trang_thai != "ringing":
            logger.info("[gọi vào] khách đã cúp trước khi bot kịp bắt máy")
            return

        ok, chi_tiet = await adb_service.answer(self.serial)
        if not ok:
            self.loi = chi_tiet
            logger.warning(f"[gọi vào] không bắt được máy: {chi_tiet}")
            return

        session = await self._mo_phien(so_goi_den)
        self.da_nhan += 1
        self.cuoc_hien_tai = {
            "so": so_goi_den, "session_id": session.session_id, "tu_luc": time.time(),
        }

        ok_voice, msg_voice = await phone_calls.start(
            self.serial, self.app_state.pipeline, session,
        )
        if not ok_voice:
            logger.warning(f"[gọi vào] không nối được đường tiếng: {msg_voice}")

        try:
            await self._chao_khach(session)
            await self._cho_ket_thuc(session)
        finally:
            if ok_voice:
                await phone_calls.stop(self.serial)
            await self._dong_phien(session)

    async def _mo_phien(self, so_goi_den: str):
        from backend.services import call_session_service as css

        # Số quen thì nạp tên và sản phẩm đang quan tâm vào phiên: "Dạ chào anh
        # Nam" nghe khác hẳn "Dạ chào anh/chị", và đó là thứ khách nhận ra ngay.
        contact = None
        if so_goi_den:
            chuan = contacts_db.normalize_phone(so_goi_den)
            got = await contacts_db.list_contacts(search=chuan, limit=1)
            contact = (got.get("contacts") or [None])[0]
            if contact:
                logger.info(f"[gọi vào] nhận ra số quen: {contact.get('name')}")

        return await css.mo_phien(
            self.app_state,
            contact=contact,
            caller_number=so_goi_den,
            direction="inbound",
            scenario_id=self.device.get("inbound_scenario_id", ""),
        )

    async def _chao_khach(self, session):
        """Chào một câu NGẮN rồi im.

        Khách gọi tới là họ có việc cần nói. Đọc hết kịch bản chào hàng vào mặt
        họ là cách nhanh nhất để bị cúp máy.
        """
        from backend.services.phone_call_service import phone_calls

        cau = (session.scenario or {}).get("opening_line") or "Dạ em nghe ạ."
        ten = session.customer_name
        if ten and ten != "Anh/Chị":
            cau = f"Dạ em chào {ten} ạ, em nghe ạ."

        bridge = phone_calls.get(self.serial)
        if bridge is None:
            return
        try:
            wav = await self.app_state.tts.synthesize(cau, voice=session.voice_name)
            if wav:
                await bridge.play(wav)
            session.add_turn("assistant", cau)
        except Exception as e:
            logger.warning(f"[gọi vào] không chào được: {e}")

    async def _cho_ket_thuc(self, session=None):
        from backend.services import transfer_service
        from backend.services.phone_call_service import phone_calls

        t0 = time.time()
        while not self._dung.is_set():
            ma, _ = await adb_service.precise_call_state(self.serial)
            if ma in (0, 7, 8):        # rảnh / vừa ngắt / đang ngắt
                break

            # Chuyển tiếp sang người thật. Với cuộc gọi VÀO thì đây là đường đi
            # thường gặp nhất, không phải ngoại lệ: người ta gọi tới hay có việc
            # nằm ngoài kịch bản.
            if session is not None:
                ly_do = transfer_service.can_chuyen_tiep(session)
                if ly_do:
                    ok, chi_tiet = await transfer_service.chuyen_tiep(
                        session, self.device, phone_calls.get(self.serial), ly_do
                    )
                    if ok:
                        break
                    logger.info(f"[gọi vào] không nối máy được: {chi_tiet}")
            if time.time() - t0 > _TRAN_CUOC_GOI_S:
                logger.warning(f"[gọi vào] quá {_TRAN_CUOC_GOI_S:.0f}s — cúp máy")
                await adb_service.hangup(self.serial)
                break
            await asyncio.sleep(_NHIP_S)

    async def _dong_phien(self, session):
        from backend.services import call_session_service as css
        await css.chot_phien(self.app_state, session, "done")


class QuanLyGoiVao:
    """Giữ các bộ theo dõi đang chạy, khoá theo device_id."""

    def __init__(self):
        self._bo: dict[str, BoNhanCuocGoi] = {}

    def trang_thai(self) -> list[dict]:
        return [b.trang_thai() for b in self._bo.values()]

    async def bat(self, device_id: str, app_state) -> tuple[bool, str]:
        device = await devices_db.get_device(device_id)
        if device is None:
            return False, "Thiết bị không tồn tại"

        cu = self._bo.get(device_id)
        if cu and cu.task and not cu.task.done():
            return False, "Máy này đã bật tự nhận cuộc gọi rồi"

        bo = BoNhanCuocGoi(device, app_state)
        ok, chi_tiet = await bo.start()
        if ok:
            self._bo[device_id] = bo
            await devices_db.update_device(device_id, inbound_enabled=1)
        return ok, chi_tiet

    async def tat(self, device_id: str) -> tuple[bool, str]:
        bo = self._bo.pop(device_id, None)
        await devices_db.update_device(device_id, inbound_enabled=0)
        if bo is None:
            return False, "Máy này không bật tự nhận cuộc gọi"
        return await bo.stop()

    async def tat_het(self):
        for device_id in list(self._bo):
            try:
                await self.tat(device_id)
            except Exception as e:
                logger.warning(f"Không tắt được bộ nhận cuộc gọi {device_id}: {e}")

    async def khoi_phuc(self, app_state):
        """Bật lại các máy đã đánh dấu inbound_enabled từ lần chạy trước."""
        so = 0
        for device in await devices_db.list_devices():
            if device.get("inbound_enabled") and device.get("kind") == "adb":
                ok, _ = await self.bat(device["device_id"], app_state)
                so += 1 if ok else 0
        if so:
            logger.info(f"  Đã bật lại tự nhận cuộc gọi trên {so} máy")
        return so


goi_vao = QuanLyGoiVao()
