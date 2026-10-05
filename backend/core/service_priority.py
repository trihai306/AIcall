"""A new customer turn preempts background LLM training on the shared GPU."""

import asyncio
import time

_customer_lock = asyncio.Lock()
_background_gpu_lock = asyncio.Lock()
_active_customer_turns: set[object] = set()
_last_customer_activity = 0.0
CUSTOMER_COOLDOWN_S = 120.0


def _mark_customer_activity() -> None:
    global _last_customer_activity
    _last_customer_activity = time.monotonic()


def reserve_customer_turn(token: object) -> None:
    _active_customer_turns.add(token)
    _mark_customer_activity()


def release_customer_turn(token: object) -> None:
    _active_customer_turns.discard(token)
    _mark_customer_activity()


def customer_turns_active() -> bool:
    return bool(_active_customer_turns)


def customer_cooldown_remaining() -> float:
    return max(0.0, CUSTOMER_COOLDOWN_S - (time.monotonic() - _last_customer_activity))


def background_ai_busy_reason() -> str:
    """Lý do tác vụ chuẩn bị nền chưa được dùng chung GPU lúc này."""
    if customer_turns_active():
        return "Khách đang trao đổi; tạm dừng chuẩn bị thư viện."
    con_lai = customer_cooldown_remaining()
    if con_lai > 0:
        return f"Chờ khách yên lặng thêm {int(con_lai) + 1} giây."
    try:
        from backend.api.training import runner as llm_runner
        from backend.api.voice_training import runner as voice_runner
        if llm_runner.is_busy() or voice_runner.is_busy():
            return "Đang có tác vụ huấn luyện dùng GPU."
    except Exception:
        # Startup/test có thể chưa import được router; phần còn lại vẫn đủ để
        # ưu tiên khách, còn worker sẽ kiểm tra lại ở nhịp sau.
        pass
    return ""


def background_gpu_lock() -> asyncio.Lock:
    """One gate shared by background inference and customer admission."""
    return _background_gpu_lock


async def prepare_customer_service() -> None:
    """Cancel active LLM training and wait for production TTS/LLM to recover."""
    from backend.api.training import runner as llm_runner
    from backend.api.voice_training import runner as voice_runner
    from backend.core.vram import latest_service_ready_task

    _mark_customer_activity()
    async with _customer_lock:
        # A native F5 call cannot be interrupted safely. Wait for the one
        # already-started bounded background operation; the activity mark above
        # prevents the worker from starting another after it releases the gate.
        async with _background_gpu_lock:
            pass
        for runner, component in ((llm_runner, "train-llm"), (voice_runner, "train")):
            job_id = runner.running_job_id
            if job_id:
                job = runner.get(job_id)
                if job and job.status == "running" and job.component == component:
                    await asyncio.to_thread(runner.cancel, job_id)
        ready = latest_service_ready_task()
        if ready and not ready.done():
            await asyncio.wait_for(asyncio.shield(ready), timeout=90)
