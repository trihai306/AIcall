"""One orchestration path for semantic understanding and verified execution."""
import copy
import hashlib
import json
import time

from backend.pipeline.grounded_contracts import DialogueState, GroundedAnswer

PRODUCT_NAMES = {
    "loan": "vay tín chấp", "mortgage": "vay mua nhà",
    "savings": "tiết kiệm", "card": "thẻ tín dụng",
}


def product_family(name: str) -> str:
    from backend.pipeline.ngu_canh_tai_lieu import _ma
    return {"vay_tin_chap": "loan", "vay_mua_nha": "mortgage",
            "tiet_kiem": "savings", "the_tin_dung": "card",
            **{family: family for family in PRODUCT_NAMES}}.get(_ma(name), "unknown")


def _policy_metrics(policy):
    encoded = json.dumps([claim.model_dump(mode="json") for claim in policy.claims],
                         sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"grounded_policy_claims": len(policy.claims),
            "grounded_policy_errors": list(policy.errors),
            "grounded_policy_hash": hashlib.sha256(encoded).hexdigest()}


async def respond(llm, text, session, source_loader, metrics, *, _retried=False):
    """Commit validated state atomically; errors never release a guessed answer."""
    from backend.pipeline.grounded_sources import build_policy
    from backend.pipeline.grounded_dialogue import understand_turn, apply_understanding
    from backend.pipeline.grounded_executor import execute_turn

    started = time.perf_counter()
    family = product_family(session.product)
    original = getattr(session, "grounded_state", None)
    state = copy.deepcopy(original) if original is not None else DialogueState(product=family)
    state.product = family
    policy = None
    try:
        selected_name = PRODUCT_NAMES.get(family, session.product)
        policy = await build_policy(family, source_loader(selected_name), llm)
        metrics.update(_policy_metrics(policy))
        meaning = await understand_turn(llm, text, session.history, state, policy)
        if meaning.product in PRODUCT_NAMES and meaning.product != family:
            selected = PRODUCT_NAMES[meaning.product]
            policy = await build_policy(meaning.product, source_loader(selected), llm)
            metrics.update(_policy_metrics(policy))
            # The new source IDs and facts must be checked against the newly
            # selected product, not against the previous product's snippets.
            state.product = meaning.product
            meaning = await understand_turn(llm, text, session.history, state, policy)
            if meaning.product not in (state.product, "unknown"):
                raise ValueError("Ambiguous product selection")
            family = state.product
        metrics["grounded_decision"] = meaning.model_dump(mode="json")
        state = apply_understanding(state, meaning, session.history, text)
        from backend.models import scenarios_db
        answer = execute_turn(
            meaning, state, policy,
            organization=scenarios_db.ten_to_chuc(session.scenario),
            agent_name=scenarios_db.ten_nhan_vien(session.scenario),
        )
        if not isinstance(answer, GroundedAnswer) or not answer.text.strip():
            raise ValueError("No verified answer")
        if session.yeu_cau_huy:
            raise InterruptedError("Turn cancelled before state commit")
        display = PRODUCT_NAMES.get(family, session.product)
        current_version = hashlib.sha256(source_loader(display).encode("utf-8")).hexdigest()
        if current_version != policy.version:
            if _retried:
                raise ValueError("Source changed repeatedly during this turn")
            metrics["grounded_source_retried"] = True
            return await respond(llm, text, session, source_loader, metrics, _retried=True)
        session.grounded_state = state
        if family in PRODUCT_NAMES:
            session.product = PRODUCT_NAMES[family]
        metrics["grounded_intent"] = meaning.intent
        metrics["grounded_topic"] = meaning.topic
        metrics["grounded_source_version"] = policy.version
        metrics["grounded_evidence_refs"] = list(answer.evidence_refs)
        metrics["du_kien_vay"] = state.evidence()
        metrics["grounded_model"] = getattr(llm, "model", "")
        return answer
    except InterruptedError:
        raise
    except Exception as exc:
        metrics["grounded_error"] = type(exc).__name__
        # Error text can contain customer/model data; keep diagnostics concise.
        metrics["grounded_error_detail"] = str(exc)[:180]
        return GroundedAnswer(
            "Dạ em chưa đủ căn cứ để xác nhận ý này. Anh chị nói rõ lại "
            "thông tin muốn kiểm tra giúp em ạ.",
            "clarify_unverified", policy.version if policy else "",
        )
    finally:
        metrics["grounded_ms"] = round((time.perf_counter() - started) * 1000)
