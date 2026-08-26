from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import shutil
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .config import AppConfig
from .index_store import DealIndex, DealIndexRow
from .processor import _pid_is_running

logger = logging.getLogger(__name__)
CLAIM_NAME = ".evaluation_claim.json"
EVALUATOR_VERSION = 3


class EvaluationError(RuntimeError):
    """A lot could not be evaluated safely."""


class ResponsesClient(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema() -> dict[str, Any]:
    source = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "retrieved_at": {"type": "string"},
        },
        "required": ["title", "url", "retrieved_at"],
    }
    card = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "game": {"type": "string"},
            "set_name": {"type": "string"},
            "set_code": {"type": ["string", "null"]},
            "collector_number": {"type": ["string", "null"]},
            "finish": {"type": "string", "enum": ["nonfoil", "foil", "etched", "unknown"]},
            "condition": {"type": "string"},
            "quantity": {"type": "integer", "minimum": 1},
            "identification_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "unit_market_low": {"type": ["number", "null"], "minimum": 0},
            "unit_market_high": {"type": ["number", "null"], "minimum": 0},
            "notes": {"type": "string"},
            "sources": {"type": "array", "items": source},
        },
        "required": [
            "name", "game", "set_name", "set_code", "collector_number", "finish",
            "condition", "quantity", "identification_confidence", "unit_market_low",
            "unit_market_high", "notes", "sources",
        ],
    }
    bulk_lot = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claimed_quantity": {"type": ["integer", "null"], "minimum": 1},
            "estimated_unitemized_quantity": {"type": ["integer", "null"], "minimum": 1},
            "market_low": {"type": ["number", "null"], "minimum": 0},
            "market_high": {"type": ["number", "null"], "minimum": 0},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "basis": {"type": "string"},
            "sources": {"type": "array", "items": source},
        },
        "required": [
            "claimed_quantity",
            "estimated_unitemized_quantity",
            "market_low",
            "market_high",
            "confidence",
            "basis",
            "sources",
        ],
    }
    visible_signal = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string"},
            "description": {"type": "string"},
            "quantity": {"type": "integer", "minimum": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["category", "description", "quantity", "confidence"],
    }
    visible_upside = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "signals": {"type": "array", "items": visible_signal},
            "incremental_market_low": {"type": ["number", "null"], "minimum": 0},
            "incremental_market_high": {"type": ["number", "null"], "minimum": 0},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "basis": {"type": "string"},
            "sources": {"type": "array", "items": source},
        },
        "required": [
            "signals",
            "incremental_market_low",
            "incremental_market_high",
            "confidence",
            "basis",
            "sources",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tcg": {"type": "string"},
            "asking_price": {"type": ["number", "null"], "minimum": 0},
            "cards": {"type": "array", "items": card},
            "bulk_lot": bulk_lot,
            "visible_upside": visible_upside,
            "unidentified_items": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "recommended_photos": {"type": "array", "items": {"type": "string"}},
            "review_required": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": [
            "tcg", "asking_price", "cards", "bulk_lot", "visible_upside",
            "unidentified_items", "uncertainties", "recommended_photos", "review_required",
            "summary",
        ],
    }


def _fingerprint(prepared: Path) -> str:
    digest = hashlib.sha256()
    for path in [prepared / "listing_data.json", *sorted((prepared / "Images").glob("*.jpg"))]:
        if not path.is_file():
            raise EvaluationError(f"Required prepared artifact is missing: {path.name}")
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _evaluation_needs_upgrade(payload: dict[str, Any]) -> bool:
    version = int(payload.get("evaluator_version", 1))
    calculation = payload.get("calculation", {})
    return version < EVALUATOR_VERSION or (
        version == EVALUATOR_VERSION
        and "visible_upside_ceiling_credit" not in calculation
    )


def _archive_previous_evaluation(lot: Path, payload: dict[str, Any]) -> Path:
    version = int(payload.get("evaluator_version", 1))
    destination = lot / f"Evaluation.previous-v{version}"
    if destination.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = lot / f"Evaluation.previous-v{version}-{timestamp}"
    (lot / "Evaluation").rename(destination)
    return destination


def _claim(lot: Path) -> bool:
    claim = lot / CLAIM_NAME
    payload = json.dumps({"pid": os.getpid(), "claimed_at": _utc_now()}).encode("utf-8")
    try:
        descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            owner = int(json.loads(claim.read_text(encoding="utf-8")).get("pid", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False
        if _pid_is_running(owner):
            return False
        try:
            claim.unlink()
        except OSError:
            return False
        return _claim(lot)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    return True


def _data_url(path: Path, max_bytes: int) -> str:
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise EvaluationError(f"Prepared image is empty or exceeds the evaluation limit: {path.name}")
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _actual_web_urls(response: Any) -> set[str]:
    if not hasattr(response, "output"):
        return set()
    if hasattr(response, "to_dict"):
        payload = response.to_dict()
    elif hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        payload = {"output": response.output}
    urls: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            candidate = value.get("url")
            if _safe_source_url(candidate) is not None:
                urls.add(str(candidate).strip())
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload.get("output", []))
    return urls


def _enforce_web_evidence(result: dict[str, Any], actual_urls: set[str]) -> None:
    if not actual_urls:
        return
    missing_evidence = False
    for card in result.get("cards", []):
        card["sources"] = [
            source
            for source in card.get("sources", [])
            if str(source.get("url", "")).strip() in actual_urls
        ]
        if (
            card.get("unit_market_low") is not None
            and card.get("unit_market_high") is not None
            and not card["sources"]
        ):
            card["unit_market_low"] = None
            card["unit_market_high"] = None
            missing_evidence = True
    bulk = result.get("bulk_lot", {})
    bulk["sources"] = [
        source
        for source in bulk.get("sources", [])
        if str(source.get("url", "")).strip() in actual_urls
    ]
    if (
        bulk.get("market_low") is not None
        and bulk.get("market_high") is not None
        and not bulk.get("sources")
    ):
        bulk["market_low"] = None
        bulk["market_high"] = None
        missing_evidence = True
    upside = result.get("visible_upside", {})
    upside["sources"] = [
        source
        for source in upside.get("sources", [])
        if str(source.get("url", "")).strip() in actual_urls
    ]
    if (
        upside.get("incremental_market_low") is not None
        and upside.get("incremental_market_high") is not None
        and not upside.get("sources")
    ):
        upside["incremental_market_low"] = None
        upside["incremental_market_high"] = None
        missing_evidence = True
    if missing_evidence:
        result["review_required"] = True
        result.setdefault("uncertainties", []).append(
            "One or more quoted prices lacked a matching web-search source and were excluded."
        )


def _request(client: ResponsesClient, config: AppConfig, lot: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = lot / "Prepared"
    listing_data = (prepared / "listing_data.json").read_text(encoding="utf-8")
    image_paths = sorted((prepared / "Images").glob("*.jpg"))[: config.evaluation_max_images]
    if not image_paths:
        raise EvaluationError("No prepared images are available for evaluation.")
    indexed = DealIndex(config.index_csv).find(lot.name) or {}
    known_asking = indexed.get("asking_price", "").strip()
    asking_instruction = (
        f"The master index records an asking price of ${known_asking}; copy it exactly."
        if known_asking
        else "No asking price is recorded; use a clearly visible listing price or return null."
    )
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Evaluate this TCG resale lot in USD. Your primary objective is to extract useful "
                "card-level evidence from the photos, not to reject the lot for ordinary uncertainty. "
                "Inspect every individual image systematically and list every visible card whose name "
                "you can identify with reasonable confidence (about 0.60 or higher), even when its exact "
                "set, collector number, finish, or condition is uncertain. If the card name is readable "
                "but the printing is unclear, use set_name='Unknown printing', use null collector_number, "
                "and price the cheapest commonly traded English nonfoil printing conservatively. State "
                "that basis in notes. Do not exclude a named card merely because its back, corners, or "
                "foil treatment are not shown. Never invent a name that is not reasonably supported. "
                "Image-file duplicates are described in listing_data and must not inflate physical "
                "quantity.\n\n"
                "Also value the unitemized remainder as bulk when the listing text or photos support a "
                "quantity estimate. bulk_lot.market_low/high must cover only the remaining unsorted cards "
                "after the individually listed visible cards, so do not double-count. Use conservative "
                "current bulk comps and clearly distinguish seller-claimed quantity from visible evidence. "
                "Use web search for current card and bulk evidence; prefer sold or reputable marketplace "
                "data. retrieved_at must be today's ISO date. Set review_required only when no meaningful "
                "valuation is possible or a specific ambiguity could reverse the recommended deal action. "
                "Routine printing, finish, or condition uncertainty should cause a conservative discount "
                "and a check item, not automatic REVIEW.\n\n"
                "Crucially, do not value visibly promising but unreadable cards at zero. Record objective "
                "visual signals in visible_upside when the photos clearly show cards likely worth more than "
                "ordinary bulk, such as old/vintage borders, foil or etched shine, rare or mythic symbols, "
                "showcase/full-art treatments, serialized or promotional styling, or recognizable Pokémon "
                "holo/ultra-rare treatments. Assign a conservative incremental_market_low/high for those "
                "specific visible cards using current category-level comps. This is the value ABOVE their "
                "ordinary bulk allocation and must exclude every card already priced in cards, so it cannot "
                "double-count either singles or bulk. Use a low estimate when identity, printing, or condition "
                "is unclear, but a clear good-card signal must raise the resale estimate and buying ceiling. "
                "Do not add upside for boxes, unseen cards, ordinary modern cards, glare, or merely possible "
                "hits. Asking price may be null.\n\n"
                f"{asking_instruction}\nLot ID: {lot.name}\nPrepared metadata:\n{listing_data}"
            ),
        }
    ]
    contact = prepared / "contact_sheet.jpg"
    transmitted = [contact, *image_paths] if contact.is_file() else image_paths
    if sum(path.stat().st_size for path in transmitted) > config.evaluation_max_total_image_bytes:
        raise EvaluationError("Prepared images exceed the total evaluation upload limit.")
    if contact.is_file():
        content.append({"type": "input_image", "image_url": _data_url(contact, config.evaluation_max_image_bytes), "detail": "low"})
    for path in image_paths:
        content.append({"type": "input_image", "image_url": _data_url(path, config.evaluation_max_image_bytes), "detail": "original"})

    response = client.create(
        model=config.openai_model,
        store=False,
        reasoning={"effort": "medium"},
        max_output_tokens=config.evaluation_max_output_tokens,
        max_tool_calls=config.evaluation_max_tool_calls,
        tools=[{"type": "web_search"}],
        include=["web_search_call.action.sources"],
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": "tcg_lot_evaluation", "strict": True, "schema": _schema()}},
    )
    output_text = getattr(response, "output_text", "")
    if not output_text:
        raise EvaluationError("The evaluation service returned no structured result.")
    try:
        result = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise EvaluationError("The evaluation service returned invalid JSON.") from exc
    _enforce_web_evidence(result, _actual_web_urls(response))
    if known_asking:
        try:
            result["asking_price"] = float(known_asking)
        except ValueError:
            logger.warning("Ignoring invalid indexed asking price for %s", lot.name)
    usage_obj = getattr(response, "usage", None)
    if hasattr(usage_obj, "to_dict"):
        usage = usage_obj.to_dict()
    elif isinstance(usage_obj, dict):
        usage = usage_obj
    else:
        usage = {}
    return result, {"response_id": getattr(response, "id", ""), "model": config.openai_model, "usage": usage}


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _inline(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def _safe_source_url(value: object) -> str | None:
    url = str(value).strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _calculate(raw: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    priced = [card for card in raw["cards"] if card["unit_market_low"] is not None and card["unit_market_high"] is not None]
    singles_low = sum(float(card["unit_market_low"]) * int(card["quantity"]) for card in priced)
    singles_high = sum(float(card["unit_market_high"]) * int(card["quantity"]) for card in priced)
    bulk = raw.get("bulk_lot", {})
    bulk_low = float(bulk.get("market_low") or 0)
    bulk_high = float(bulk.get("market_high") or 0)
    upside = raw.get("visible_upside", {})
    upside_low = float(upside.get("incremental_market_low") or 0)
    upside_high = float(upside.get("incremental_market_high") or 0)
    upside_confidence = float(upside.get("confidence") or 0)
    upside_ceiling_credit = upside_low + (
        max(0.0, upside_high - upside_low) * upside_confidence * 0.50
    )
    gross_low = singles_low + bulk_low + upside_low
    gross_high = singles_high + bulk_high + upside_high
    expected_resale = (gross_low + gross_high) / 2
    fees = expected_resale * config.platform_fee_rate
    shipping = config.default_shipping_cost if expected_resale > 0 else 0.0
    expected_net_before_buy = expected_resale - fees - shipping
    base_resale_low = singles_low + bulk_low
    base_resale_high = singles_high + bulk_high
    base_expected_resale = (base_resale_low + base_resale_high) / 2
    base_shipping = config.default_shipping_cost if base_expected_resale > 0 else 0.0
    base_net_before_buy = (
        base_expected_resale
        - (base_expected_resale * config.platform_fee_rate)
        - base_shipping
    )
    max_buy_without_upside = max(
        0.0,
        math.floor(
            min(
                base_resale_low * config.max_buy_fraction,
                base_net_before_buy * 0.70,
            )
        ),
    )
    ceiling_resale_basis = singles_low + bulk_low + upside_ceiling_credit
    max_buy = max(
        0.0,
        math.floor(
            min(
                ceiling_resale_basis * config.max_buy_fraction,
                expected_net_before_buy * 0.70,
            )
        ),
    )
    expected_profit = max(0.0, expected_net_before_buy - max_buy)
    asking = raw.get("asking_price")
    if gross_high <= 0:
        verdict = "REVIEW"
    elif asking is None:
        verdict = "CONDITIONAL"
    elif float(asking) <= max_buy * 0.90:
        verdict = "BUY WITH CHECKS" if raw.get("review_required") else "BUY"
    elif float(asking) <= max_buy:
        verdict = "NEGOTIATE WITH CHECKS" if raw.get("review_required") else "NEGOTIATE"
    else:
        verdict = "PASS"
    return {
        "gross_resale_low": round(gross_low, 2),
        "gross_resale_high": round(gross_high, 2),
        "expected_resale": round(expected_resale, 2),
        "estimated_fees": round(fees, 2),
        "singles_resale_low": round(singles_low, 2),
        "singles_resale_high": round(singles_high, 2),
        "bulk_resale_low": round(bulk_low, 2),
        "bulk_resale_high": round(bulk_high, 2),
        "visible_upside_low": round(upside_low, 2),
        "visible_upside_high": round(upside_high, 2),
        "visible_upside_ceiling_credit": round(upside_ceiling_credit, 2),
        "estimated_shipping": round(shipping, 2),
        "max_buy": round(max_buy, 2),
        "max_buy_without_visible_upside": round(max_buy_without_upside, 2),
        "visible_upside_ceiling_increase": round(
            max(0.0, max_buy - max_buy_without_upside), 2
        ),
        "expected_profit_at_max_buy": round(expected_profit, 2),
        "roi_at_max_buy_percent": round(expected_profit / max_buy * 100, 1) if max_buy else 0,
        "verdict": verdict,
        "priced_card_count": len(priced),
        "identified_card_count": len(raw["cards"]),
    }


def _recommendations(lot_id: str, raw: dict[str, Any], calc: dict[str, Any]) -> str:
    asking = raw.get("asking_price")
    headline = calc["verdict"]
    if headline == "CONDITIONAL":
        action = f"Offer no more than **{_money(calc['max_buy'])}**. Enter the seller's asking price for a final BUY/PASS comparison."
    elif headline == "REVIEW":
        action = f"Do not make a final offer yet. Conditional ceiling: **{_money(calc['max_buy'])}** after the checks below."
    elif headline in {"BUY", "BUY WITH CHECKS"}:
        action = f"Buy at the listed {_money(float(asking))}; calculated ceiling is **{_money(calc['max_buy'])}**."
        if headline == "BUY WITH CHECKS":
            action += " Confirm the seller, quantity, and pickup contents before paying."
    elif headline in {"NEGOTIATE", "NEGOTIATE WITH CHECKS"}:
        action = f"Negotiate to **{_money(calc['max_buy'])} or less**."
    else:
        action = f"Pass at {_money(float(asking))}; calculated ceiling is **{_money(calc['max_buy'])}**."
    lines = [
        f"# {headline}: {lot_id}", "", action, "", "## Numbers", "",
        f"- Estimated resale: **{_money(calc['gross_resale_low'])}–{_money(calc['gross_resale_high'])}**",
        f"- Visible priced singles: {_money(calc['singles_resale_low'])}–{_money(calc['singles_resale_high'])}",
        f"- Visible good-card upside: {_money(calc['visible_upside_low'])}–{_money(calc['visible_upside_high'])}",
        f"- Upside credited toward ceiling: {_money(calc['visible_upside_ceiling_credit'])}",
        (
            f"- Ceiling impact from visible upside: **+"
            f"{_money(calc['visible_upside_ceiling_increase'])}** "
            f"({_money(calc['max_buy_without_visible_upside'])} without it → "
            f"{_money(calc['max_buy'])} with it)"
        ),
        f"- Unitemized bulk estimate: {_money(calc['bulk_resale_low'])}–{_money(calc['bulk_resale_high'])}",
        f"- Expected profit if bought at the ceiling: **{_money(calc['expected_profit_at_max_buy'])}**",
        f"- Estimated ROI at the ceiling: **{calc['roi_at_max_buy_percent']:.1f}%**",
        f"- Assumed fees: {_money(calc['estimated_fees'])}; shipping/materials: {_money(calc['estimated_shipping'])}",
        "", "## Identified cards", "",
    ]
    for card in raw["cards"]:
        price = "price needs verification"
        if card["unit_market_low"] is not None and card["unit_market_high"] is not None:
            price = f"{_money(float(card['unit_market_low']))}–{_money(float(card['unit_market_high']))} each"
        detail = ", ".join(
            _inline(part)
            for part in [card["set_name"], card.get("collector_number"), card["finish"]]
            if part
        )
        lines.append(f"- {card['quantity']}× **{_inline(card['name'])}** — {detail}; {price}")
    if not raw["cards"]:
        lines.append("- No individual card names were sufficiently visible.")
    upside = raw.get("visible_upside", {})
    if upside.get("signals"):
        lines.extend(["", "## Visible upside", ""])
        for signal in upside["signals"]:
            lines.append(
                f"- {signal['quantity']}× **{_inline(signal['category'])}** — "
                f"{_inline(signal['description'])} "
                f"({float(signal['confidence']) * 100:.0f}% confidence)"
            )
        if (
            upside.get("incremental_market_low") is not None
            and upside.get("incremental_market_high") is not None
        ):
            lines.append(
                f"- Adds **{_money(float(upside['incremental_market_low']))}–"
                f"{_money(float(upside['incremental_market_high']))}** above ordinary bulk: "
                f"{_inline(upside.get('basis', 'conservative visible-card premium'))}"
            )
    bulk = raw.get("bulk_lot", {})
    if bulk.get("market_low") is not None and bulk.get("market_high") is not None:
        lines.extend(
            [
                "",
                "## Bulk remainder",
                "",
                (
                    f"- {_money(float(bulk['market_low']))}–"
                    f"{_money(float(bulk['market_high']))}: "
                    f"{_inline(bulk.get('basis', 'conservative bulk estimate'))}"
                ),
            ]
        )
    checks = [*raw["uncertainties"], *raw["recommended_photos"]]
    if checks:
        lines.extend(["", "## Check before buying", ""])
        lines.extend(f"- {_inline(item)}" for item in checks)
    lines.extend(["", f"Updated: {_utc_now()}", "", "Prices are estimates, not guarantees. Open `Evaluation/evaluation_summary.md` for sources and detail.", ""])
    return "\n".join(lines)


def _summary(lot_id: str, raw: dict[str, Any], calc: dict[str, Any]) -> str:
    lines = [_recommendations(lot_id, raw, calc), "## Price sources", ""]
    seen: set[str] = set()
    for card in raw["cards"]:
        for source in card["sources"]:
            url = _safe_source_url(source["url"])
            if url and url not in seen:
                seen.add(url)
                lines.append(
                    f"- [{_inline(source['title'])}]({url}) — retrieved "
                    f"{_inline(source['retrieved_at'])}"
                )
    for source in raw.get("bulk_lot", {}).get("sources", []):
        url = _safe_source_url(source["url"])
        if url and url not in seen:
            seen.add(url)
            lines.append(
                f"- [{_inline(source['title'])}]({url}) — retrieved "
                f"{_inline(source['retrieved_at'])}"
            )
    for source in raw.get("visible_upside", {}).get("sources", []):
        url = _safe_source_url(source["url"])
        if url and url not in seen:
            seen.add(url)
            lines.append(
                f"- [{_inline(source['title'])}]({url}) — retrieved "
                f"{_inline(source['retrieved_at'])}"
            )
    if not seen:
        lines.append("- No usable price source was returned; manual review is required.")
    lines.append("")
    return "\n".join(lines)


def evaluate_lot(config: AppConfig, lot: Path, client: ResponsesClient) -> Path | None:
    prepared = lot / "Prepared"
    if not prepared.is_dir() or not (prepared / "listing_data.json").is_file():
        return None
    fingerprint = _fingerprint(prepared)
    completed = lot / "Evaluation" / "evaluation.json"
    existing: dict[str, Any] | None = None
    if completed.is_file():
        existing = json.loads(completed.read_text(encoding="utf-8"))
        if existing.get("input_fingerprint") != fingerprint:
            raise EvaluationError(
                "Prepared inputs changed after evaluation; remove Evaluation to review intentionally."
            )
        if not _evaluation_needs_upgrade(existing):
            phone_copy = lot / "recommendations.md"
            if not phone_copy.is_file():
                phone_copy.write_text(
                    (lot / "Evaluation" / "recommendations.md").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            return lot / "Evaluation"
    if not _claim(lot):
        return None
    claim = lot / CLAIM_NAME
    building = lot / "Evaluation.__building__"
    try:
        if existing is not None and (lot / "Evaluation").is_dir():
            archived = _archive_previous_evaluation(lot, existing)
            logger.info("Archived previous evaluation for %s at %s", lot.name, archived.name)
        if building.exists():
            shutil.rmtree(building)
        building.mkdir()
        raw, api_usage = _request(client, config, lot)
        calc = _calculate(raw, config)
        payload = {
            "schema_version": 1, "evaluator_version": EVALUATOR_VERSION,
            "lot_id": lot.name, "evaluated_at": _utc_now(),
            "input_fingerprint": fingerprint, "identification": raw, "calculation": calc,
        }
        (building / "evaluation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (building / "api_usage.json").write_text(json.dumps(api_usage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sources = [source for card in raw["cards"] for source in card["sources"]]
        sources.extend(raw.get("bulk_lot", {}).get("sources", []))
        sources.extend(raw.get("visible_upside", {}).get("sources", []))
        (building / "price_sources.json").write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        recommendations = _recommendations(lot.name, raw, calc)
        (building / "evaluation_summary.md").write_text(_summary(lot.name, raw, calc), encoding="utf-8")
        (building / "recommendations.md").write_text(recommendations, encoding="utf-8")
        building.rename(lot / "Evaluation")
        (lot / "recommendations.md").write_text(recommendations, encoding="utf-8")
        try:
            DealIndex(config.index_csv).upsert(
                DealIndexRow(
                    lot_id=lot.name,
                    status="Evaluated",
                    folder=str(lot),
                    tcg=raw["tcg"],
                    asking_price=(
                        "" if raw.get("asking_price") is None else str(raw["asking_price"])
                    ),
                    verdict=calc["verdict"],
                    max_buy=f"{calc['max_buy']:.2f}",
                    expected_resale=f"{calc['expected_resale']:.2f}",
                    expected_profit=f"{calc['expected_profit_at_max_buy']:.2f}",
                    roi_percent=f"{calc['roi_at_max_buy_percent']:.1f}",
                    notes=raw["summary"],
                ),
                preserve_existing=True,
                overwrite_fields={
                    "tcg",
                    "asking_price",
                    "verdict",
                    "max_buy",
                    "expected_resale",
                    "expected_profit",
                    "roi_percent",
                },
            )
        except OSError:
            logger.exception("Could not update master deal index for %s", lot.name)
        logger.info("Evaluated lot %s: %s", lot.name, calc["verdict"])
        return lot / "Evaluation"
    except Exception as exc:
        logger.exception("Evaluation failed for %s", lot.name)
        if building.exists():
            shutil.rmtree(building)
        if not (lot / "Evaluation" / "evaluation.json").is_file():
            (lot / "evaluation_error.json").write_text(
                json.dumps(
                    {"lot_id": lot.name, "failed_at": _utc_now(), "reason": str(exc)},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        raise
    finally:
        claim.unlink(missing_ok=True)


def _openai_responses() -> ResponsesClient:
    if not os.getenv("OPENAI_API_KEY"):
        raise EvaluationError("OPENAI_API_KEY is not configured.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise EvaluationError("The OpenAI package is not installed.") from exc
    return OpenAI().responses


class EvaluationWorker:
    def __init__(self, config: AppConfig, *, on_status: Callable[[str], None] | None = None, client: ResponsesClient | None = None) -> None:
        self.config = config
        self.on_status = on_status or (lambda _: None)
        self.client = client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.ai_enabled:
            logger.info("Automated evaluation is disabled; set TCG_AI_ENABLED=1 to enable it")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="evaluation-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            client = self.client or _openai_responses()
        except EvaluationError as exc:
            self.on_status(f"Automated evaluation unavailable: {exc}")
            return
        while not self._stop.is_set():
            did_work = False
            for lot in sorted(self.config.completed_dir.iterdir(), key=lambda path: path.name.casefold()):
                if self._stop.is_set() or not lot.is_dir() or lot.name.startswith("."):
                    continue
                evaluation_complete = (lot / "Evaluation" / "evaluation.json").is_file()
                phone_copy_complete = (lot / "recommendations.md").is_file()
                upgrade_needed = False
                if evaluation_complete:
                    try:
                        payload = json.loads(
                            (lot / "Evaluation" / "evaluation.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        upgrade_needed = _evaluation_needs_upgrade(payload)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        logger.exception("Could not inspect evaluation version for %s", lot.name)
                if (evaluation_complete and phone_copy_complete and not upgrade_needed) or (
                    not evaluation_complete and (lot / "evaluation_error.json").is_file()
                ):
                    continue
                try:
                    if evaluate_lot(self.config, lot, client) is not None:
                        did_work = True
                        self.on_status(f"{lot.name}: recommendation ready")
                except Exception as exc:
                    logger.exception("Evaluation worker error for %s", lot.name)
                    self.on_status(f"{lot.name}: evaluation needs review ({exc})")
            self._stop.wait(1.0 if did_work else self.config.evaluation_poll_seconds)
