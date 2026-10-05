import asyncio
import sys
from types import ModuleType, SimpleNamespace

from backend.core import vram
from backend.core.service_priority import prepare_customer_service


class FakeRunner:
    def __init__(self, running=True):
        self.running_job_id = "job" if running else None
        self.job = SimpleNamespace(status="running", component="train-llm")
        self.cancelled = False

    def get(self, job_id):
        assert job_id == "job"
        return self.job

    def cancel(self, job_id):
        assert job_id == "job"
        self.cancelled = True
        self.job.status = "cancelled"


def _fake_module(monkeypatch, name, runner):
    module = ModuleType(name)
    module.runner = runner
    monkeypatch.setitem(sys.modules, name, module)


def test_customer_preempts_training_and_waits_for_restore(monkeypatch):
    llm = FakeRunner()
    voice = FakeRunner(False)
    _fake_module(monkeypatch, "backend.api.training", llm)
    _fake_module(monkeypatch, "backend.api.voice_training", voice)

    async def scenario():
        restored = False

        async def restore():
            nonlocal restored
            await asyncio.sleep(0.01)
            restored = True

        task = asyncio.create_task(restore())
        monkeypatch.setattr(vram, "latest_service_ready_task", lambda: task)
        await prepare_customer_service()
        assert llm.cancelled
        assert restored

    asyncio.run(scenario())


def test_customer_waits_for_restore_after_job_status_clears(monkeypatch):
    _fake_module(monkeypatch, "backend.api.training", FakeRunner(False))
    _fake_module(monkeypatch, "backend.api.voice_training", FakeRunner(False))

    async def scenario():
        task = asyncio.create_task(asyncio.sleep(0.01))
        monkeypatch.setattr(vram, "latest_service_ready_task", lambda: task)
        await prepare_customer_service()
        assert task.done()

    asyncio.run(scenario())
