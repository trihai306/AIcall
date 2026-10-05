import asyncio

import pytest

from backend.services import llm_service as ls


class _InventoryClient:
    def __init__(
        self,
        models,
        *,
        delay=0.0,
        error=None,
        capabilities=None,
        show_delay=0.0,
        show_error=None,
    ):
        self.models = models
        self.delay = delay
        self.error = error
        self.capabilities = capabilities or {}
        self.show_delay = show_delay
        self.show_error = show_error
        self.list_calls = 0
        self.show_calls = []

    async def list(self):
        self.list_calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return {"models": [{"model": name} for name in self.models]}

    async def show(self, model):
        self.show_calls.append(model)
        if self.show_delay:
            await asyncio.sleep(self.show_delay)
        if self.show_error:
            raise self.show_error
        return {"capabilities": self.capabilities.get(model, [])}


def _service(model: str, client: _InventoryClient) -> ls.LLMService:
    service = ls.LLMService.__new__(ls.LLMService)
    service.model = model
    service.client = client
    service._ho_tro_think = True
    return service


def _configure(monkeypatch, *, selector="selector:9b", response="", fallbacks=""):
    monkeypatch.setattr(ls.settings, "llm_auto_routing", True)
    monkeypatch.setattr(ls.settings, "llm_selector_model", selector)
    monkeypatch.setattr(ls.settings, "llm_response_model", response)
    monkeypatch.setattr(ls.settings, "llm_fallback_models", fallbacks)


def test_selector_uses_exact_available_role_model_without_mutating_production(monkeypatch):
    _configure(monkeypatch, selector="selector")
    client = _InventoryClient(["selector:latest", "production:latest"])
    production = _service("production", client)

    selected = asyncio.run(production.route_for("answer_selection"))

    assert selected is not production
    assert selected.model == "selector"
    assert selected.client is client
    assert selected._ho_tro_think is False
    assert production.model == "production"
    assert production._ho_tro_think is True


def test_response_empty_config_uses_existing_production_service(monkeypatch):
    _configure(monkeypatch, response="")
    client = _InventoryClient(["production:latest"])
    production = _service("production", client)

    selected = asyncio.run(production.route_for("response"))

    assert selected is production
    assert production.model == "production"


def test_only_explicit_fallback_can_replace_missing_role_and_production(monkeypatch):
    _configure(
        monkeypatch,
        selector="missing-selector:9b",
        fallbacks="missing:7b, approved:7b",
    )
    client = _InventoryClient(["experimental-a:2b", "approved:7b", "experimental-b:2b"])
    production = _service("missing-production:9b", client)

    selected = asyncio.run(production.route_for("answer_selection"))

    assert selected.model == "approved:7b"
    assert production.model == "missing-production:9b"


def test_unapproved_installed_candidates_are_never_promoted(monkeypatch):
    _configure(monkeypatch, selector="missing-selector:9b")
    client = _InventoryClient(["experimental-a:2b", "experimental-b:2b"])
    production = _service("production:9b", client)

    selected = asyncio.run(production.route_for("answer_selection"))

    assert selected is production
    assert selected.model == "production:9b"


@pytest.mark.parametrize("models", [[], None])
def test_empty_or_unavailable_inventory_preserves_production(monkeypatch, models):
    _configure(monkeypatch)
    client = (
        _InventoryClient([], error=OSError("Ollama unavailable"))
        if models is None
        else _InventoryClient(models)
    )
    production = _service("production:9b", client)

    selected = asyncio.run(production.route_for("answer_selection"))

    assert selected is production
    assert production.model == "production:9b"


def test_auto_routing_disabled_does_not_query_inventory(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(ls.settings, "llm_auto_routing", False)
    client = _InventoryClient(["selector:9b"])
    production = _service("production:9b", client)

    assert asyncio.run(production.route_for("answer_selection")) is production
    assert client.list_calls == 0


def test_concurrent_routes_share_one_inventory_refresh_and_keep_model_stable(monkeypatch):
    _configure(monkeypatch, selector="selector:9b", response="response:9b")
    client = _InventoryClient(["selector:9b", "response:9b"], delay=0.02)
    production = _service("production:9b", client)

    async def run_routes():
        tasks = ["answer_selection", "response"] * 10
        return await asyncio.gather(*(production.route_for(task) for task in tasks))

    selected = asyncio.run(run_routes())

    assert client.list_calls == 1
    assert [item.model for item in selected] == ["selector:9b", "response:9b"] * 10
    assert all(item.client is client for item in selected)
    assert production.model == "production:9b"


def test_alternate_thinking_model_capability_is_loaded_once_concurrently(monkeypatch):
    _configure(monkeypatch, response="custom-chat:7b")
    client = _InventoryClient(
        ["custom-chat:7b"],
        capabilities={"custom-chat:7b": ["completion", "thinking"]},
        show_delay=0.02,
    )
    production = _service("production:9b", client)
    production._ho_tro_think = False

    async def run_routes():
        return await asyncio.gather(*(production.route_for("response") for _ in range(12)))

    selected = asyncio.run(run_routes())

    assert client.list_calls == 1
    assert client.show_calls == ["custom-chat:7b"]
    assert all(service is selected[0] for service in selected)
    assert selected[0]._nen_think("Dạ về lãi suất thì,") is True
    assert production._ho_tro_think is False
    assert production.model == "production:9b"


def test_capability_timeout_keeps_cached_name_heuristic_without_mutating_production(
    monkeypatch,
):
    _configure(monkeypatch, response="custom-chat:7b")
    client = _InventoryClient(["custom-chat:7b"], show_delay=0.05)
    production = _service("production:9b", client)
    production._ho_tro_think = False
    monkeypatch.setattr(production, "_CAPABILITY_TIMEOUT_S", 0.001)

    async def route_twice():
        first = await production.route_for("response")
        second = await production.route_for("response")
        return first, second

    first, second = asyncio.run(route_twice())

    assert first is second
    assert first._ho_tro_think is None
    assert first._nen_think("Dạ,") is False
    assert client.show_calls == ["custom-chat:7b"]
    assert production._ho_tro_think is False


def test_unknown_task_is_rejected_before_routing(monkeypatch):
    _configure(monkeypatch)
    production = _service("production:9b", _InventoryClient(["production:9b"]))

    with pytest.raises(ValueError, match="Unsupported LLM routing task"):
        asyncio.run(production.route_for("training"))
