"""Nhả và nạp lại VRAM quanh các job train.

Cả train LLM lẫn train giọng đều gặp cùng một vấn đề: GPU 12GB, mà F5-TTS
(trong chính tiến trình backend) và Ollama đang giữ một phần. Không nhả ra thì
train OOM.

Tách riêng vì hai module API cần y hệt nhau - chép hai bản thì sớm muộn cũng
lệch, và lệch ở đây nghĩa là một trong hai đường train âm thầm thiếu VRAM.
"""

import asyncio
import logging
import subprocess

logger = logging.getLogger(__name__)

# asyncio chỉ giữ tham chiếu YẾU tới task đang chạy: không giữ ở đâu đó thì bộ
# thu gom rác có thể huỷ task theo dõi giữa chừng, và dịch vụ sẽ không bao giờ
# được nạp lại sau khi train xong.
_tasks_nen: set = set()


def _vram_trong_mib() -> int | None:
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.mem_get_info()[0] / 1024**2)
    except Exception:
        pass
    return None


def giai_phong_vram(job, ollama_models: set[str] | None = None) -> None:
    """Nhả F5-TTS trong tiến trình này và yêu cầu Ollama nhả model.

    Ghi thẳng vào log của job để người dùng thấy được đã nhả bao nhiêu, thay vì
    phải đoán khi train báo hết bộ nhớ.
    """
    from backend.main import app_state

    try:
        ket_qua = app_state.tts.unload()
        truoc, sau = ket_qua.get("vram_free_truoc_mib"), ket_qua.get("vram_free_sau_mib")
        if truoc is not None:
            job.log(f"Nhả F5-TTS: VRAM trống {truoc} -> {sau} MiB")
        else:
            job.log(f"F5-TTS: {ket_qua.get('ghi_chu', 'đã nhả')}")
    except Exception as e:
        job.log(f"[WARN] Không nhả được F5-TTS: {e}")
        logger.exception("unload TTS hỏng")

    # Ollama giữ model trong VRAM tới khi hết thời gian chờ. Dừng tay để lấy
    # lại ngay thay vì đợi.
    da_dung = False
    for ten in (ollama_models or set()):
        if not ten:
            continue
        try:
            r = subprocess.run(["ollama", "stop", ten], capture_output=True, timeout=30)
            da_dung = da_dung or r.returncode == 0
        except Exception:
            pass
    if ollama_models:
        job.log("Đã yêu cầu Ollama nhả model" if da_dung
                else "[WARN] Không gọi được 'ollama stop' (thiếu ollama trong PATH?)")

    free = _vram_trong_mib()
    if free is not None:
        job.log(f"VRAM trống trước khi train: {round(free / 1024, 1)} GB")


async def nap_lai_tts(job) -> None:
    """Nạp lại F5-TTS. Gọi dù job thành công, lỗi hay bị huỷ."""
    from backend.main import app_state

    try:
        await asyncio.get_running_loop().run_in_executor(None, app_state.tts.load)
        job.log("Đã nạp lại F5-TTS")
    except Exception as e:
        job.log(f"[ERROR] Nạp lại F5-TTS hỏng: {e}")
        logger.exception("nạp lại TTS sau train hỏng")


def theo_doi_roi_don(job, xong=None):
    """Tạo task chờ job kết thúc rồi nạp lại dịch vụ.

    `xong` là coroutine-function nhận job, chạy TRƯỚC khi nạp lại TTS - dùng cho
    việc riêng của từng loại train (ví dụ chuyển .env sang model mới).

    Trả về task và tự giữ tham chiếu, nên bên gọi không cần nhớ làm việc đó.
    """
    async def _chay():
        try:
            await job.task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("job ném lỗi")
        if xong is not None:
            try:
                await xong(job)
            except Exception:
                logger.exception("bước dọn riêng hỏng")
        await nap_lai_tts(job)

    t = asyncio.create_task(_chay())
    _tasks_nen.add(t)
    t.add_done_callback(_tasks_nen.discard)
    return t
