from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tcg_resale_evaluator.config import AppConfig, config_from_environment
from tcg_resale_evaluator.evaluator import (
    EvaluationError,
    _calculate,
    _enforce_web_evidence,
    evaluate_lot,
)
from tcg_resale_evaluator.index_store import DealIndex, DealIndexRow


class FakeResponses:
    def __init__(self, payload: dict[str, object], *, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            id="resp_test",
            output_text=json.dumps(self.payload),
            usage=SimpleNamespace(to_dict=lambda: {"input_tokens": 100, "output_tokens": 50}),
        )


class SequencedResponses(FakeResponses):
    def __init__(self, payload: dict[str, object], outputs: list[str]) -> None:
        super().__init__(payload)
        self.outputs = outputs

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        return SimpleNamespace(
            id=f"resp_test_{len(self.calls)}",
            output_text=output,
            usage=SimpleNamespace(to_dict=lambda: {"input_tokens": 100, "output_tokens": 50}),
        )


def _payload(*, asking_price: float | None = None, review: bool = False) -> dict[str, object]:
    return {
        "tcg": "Magic: The Gathering",
        "asking_price": asking_price,
        "cards": [
            {
                "name": "Test Card",
                "game": "Magic: The Gathering",
                "set_name": "Test Set",
                "set_code": "TST",
                "collector_number": "1",
                "finish": "nonfoil",
                "condition": "Near Mint assumed from front only",
                "quantity": 2,
                "identification_confidence": 0.95,
                "unit_market_low": 40.0,
                "unit_market_high": 50.0,
                "notes": "Fronts visible.",
                "sources": [
                    {
                        "title": "Example market",
                        "url": "https://example.test/card",
                        "retrieved_at": "2026-08-26",
                    }
                ],
            }
        ],
        "bulk_lot": {
            "claimed_quantity": None,
            "estimated_unitemized_quantity": None,
            "market_low": None,
            "market_high": None,
            "confidence": 0.0,
            "era_profile": "unknown",
            "era_confidence": 0.0,
            "era_basis": "No unitemized cards represented.",
            "basis": "No additional bulk represented.",
            "sources": [],
        },
        "visible_upside": {
            "signals": [],
            "incremental_market_low": None,
            "incremental_market_high": None,
            "confidence": 0.0,
            "basis": "No unpriced good-card signals visible.",
            "sources": [],
        },
        "unidentified_items": [],
        "uncertainties": ["Card backs are not visible."],
        "recommended_photos": ["Add one clear photo of all card backs."],
        "review_required": review,
        "summary": "Two copies identified.",
    }


def _completed_lot(config: AppConfig) -> Path:
    config.ensure_layout()
    lot = config.completed_dir / "LOT-TEST"
    images = lot / "Prepared" / "Images"
    images.mkdir(parents=True)
    Image.new("RGB", (100, 150), "blue").save(images / "possible_card_image_001.jpg")
    (lot / "Prepared" / "listing_data.json").write_text(
        json.dumps({"lot_id": lot.name, "image_count": 1, "duplicate_count": 0}),
        encoding="utf-8",
    )
    (lot / "Prepared" / "contact_sheet.jpg").write_bytes(
        (images / "possible_card_image_001.jpg").read_bytes()
    )
    return lot


def test_evaluation_creates_phone_recommendation_artifacts_and_updates_index(
    tmp_path: Path,
) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    DealIndex(config.index_csv).upsert(
        DealIndexRow(lot_id=lot.name, created_at="2026-01-01", asking_price="35")
    )
    client = FakeResponses(_payload())

    destination = evaluate_lot(config, lot, client)

    assert destination == lot / "Evaluation"
    assert {
        "api_usage.json",
        "evaluation.json",
        "evaluation_summary.md",
        "price_sources.json",
        "recommendations.md",
    } == {path.name for path in destination.iterdir()}
    phone_text = (lot / "recommendations.md").read_text(encoding="utf-8")
    assert "# BUY: LOT-TEST" in phone_text
    assert "Offer no more" not in phone_text
    assert "Add one clear photo" in phone_text
    evaluation = json.loads((destination / "evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["identification"]["asking_price"] == 35.0
    assert evaluation["evaluator_version"] == 4
    assert evaluation["calculation"]["max_buy"] == 44.0
    row = DealIndex(config.index_csv).find(lot.name)
    assert row is not None
    assert row["created_at"] == "2026-01-01"
    assert row["verdict"] == "BUY"
    request = client.calls[0]
    assert request["store"] is False
    assert request["tools"] == [{"type": "web_search"}]
    assert request["max_tool_calls"] == 6
    assert request["text"]["format"]["type"] == "json_schema"  # type: ignore[index]
    assert request["reasoning"] == {"effort": "medium"}
    content = request["input"][0]["content"]  # type: ignore[index]
    image_details = [item["detail"] for item in content if item["type"] == "input_image"]
    assert image_details == ["low", "original"]
    assert "list every visible card" in content[0]["text"]
    assert "a clear good-card signal must raise" in content[0]["text"]


def test_evaluation_is_idempotent_and_does_not_call_api_twice(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    client = FakeResponses(_payload())

    first = evaluate_lot(config, lot, client)
    second = evaluate_lot(config, lot, client)

    assert first == second == lot / "Evaluation"
    assert len(client.calls) == 1


def test_truncated_json_is_retried_once_and_then_succeeds(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    (lot / "evaluation_error.json").write_text('{"reason":"previous failure"}')
    client = SequencedResponses(_payload(), ['{"tcg":"Magic', json.dumps(_payload())])

    destination = evaluate_lot(config, lot, client)

    assert destination == lot / "Evaluation"
    assert len(client.calls) == 2
    usage = json.loads((destination / "api_usage.json").read_text(encoding="utf-8"))
    assert usage["attempts"] == 2
    assert not (lot / "evaluation_error.json").exists()


def test_idempotent_pass_repairs_missing_phone_copy(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    client = FakeResponses(_payload())
    evaluate_lot(config, lot, client)
    (lot / "recommendations.md").unlink()

    evaluate_lot(config, lot, client)

    assert (lot / "recommendations.md").is_file()
    assert len(client.calls) == 1


def test_missing_asking_price_produces_conditional_phone_guidance(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)

    evaluate_lot(config, lot, FakeResponses(_payload()))

    text = (lot / "recommendations.md").read_text(encoding="utf-8")
    assert "# CONDITIONAL" in text
    assert "Offer no more than" in text


def test_review_required_adds_checks_without_discarding_clear_value(tmp_path: Path) -> None:
    calculation = _calculate(_payload(asking_price=20, review=True), AppConfig(tmp_path))
    assert calculation["verdict"] == "BUY WITH CHECKS"


def test_bulk_floor_and_partial_card_identification_contribute_to_deal_math(
    tmp_path: Path,
) -> None:
    payload = _payload(asking_price=1, review=True)
    payload["cards"].append(  # type: ignore[union-attr]
        {
            "name": "Partially identified card",
            "game": "Magic: The Gathering",
            "set_name": "Unknown printing",
            "set_code": None,
            "collector_number": None,
            "finish": "unknown",
            "condition": "unknown",
            "quantity": 1,
            "identification_confidence": 0.65,
            "unit_market_low": None,
            "unit_market_high": None,
            "notes": "Name visible; price not verified.",
            "sources": [],
        }
    )
    payload["bulk_lot"] = {
        "claimed_quantity": 10_000,
        "estimated_unitemized_quantity": 9_997,
        "market_low": 180.0,
        "market_high": 250.0,
        "confidence": 0.5,
        "era_profile": "unknown",
        "era_confidence": 0.0,
        "era_basis": "Era cannot be assessed.",
        "basis": "Conservative bulk remainder.",
        "sources": [],
    }

    calculation = _calculate(payload, AppConfig(tmp_path))

    assert calculation["bulk_resale_low"] == 180.0
    assert calculation["gross_resale_low"] == 260.0
    assert calculation["identified_card_count"] == 2
    assert calculation["priced_card_count"] == 1
    assert calculation["max_buy"] > 0
    assert calculation["verdict"] == "BUY WITH CHECKS"


def test_visible_good_cards_raise_resale_and_buying_ceiling(tmp_path: Path) -> None:
    baseline = _payload(asking_price=1, review=True)
    baseline["cards"] = []
    baseline["bulk_lot"]["market_low"] = 100.0  # type: ignore[index]
    baseline["bulk_lot"]["market_high"] = 200.0  # type: ignore[index]
    without_upside = _calculate(baseline, AppConfig(tmp_path))

    baseline["visible_upside"] = {
        "signals": [
            {
                "category": "visible old-border or foil cards",
                "description": "Five distinct cards show clear above-bulk visual traits.",
                "quantity": 5,
                "confidence": 0.8,
            }
        ],
        "incremental_market_low": 40.0,
        "incremental_market_high": 100.0,
        "confidence": 0.7,
        "basis": "Conservative category-level premium above ordinary bulk.",
        "sources": [],
    }
    with_upside = _calculate(baseline, AppConfig(tmp_path))

    assert with_upside["visible_upside_low"] == 40.0
    assert with_upside["visible_upside_ceiling_credit"] == 61.0
    assert with_upside["gross_resale_low"] == without_upside["gross_resale_low"] + 40.0
    assert with_upside["max_buy"] > without_upside["max_buy"]
    assert with_upside["max_buy_without_visible_upside"] == without_upside["max_buy"]
    assert with_upside["visible_upside_ceiling_increase"] == (
        with_upside["max_buy"] - without_upside["max_buy"]
    )


def test_older_mixed_bulk_uses_visible_cards_as_purchase_backstop(tmp_path: Path) -> None:
    payload = _payload(asking_price=100, review=True)
    payload["cards"][0]["unit_market_low"] = 50.0  # type: ignore[index]
    payload["cards"][0]["unit_market_high"] = 60.0  # type: ignore[index]
    payload["bulk_lot"] = {
        "claimed_quantity": 1_000,
        "estimated_unitemized_quantity": 998,
        "market_low": 50.0,
        "market_high": 100.0,
        "confidence": 0.7,
        "era_profile": "older_or_mixed",
        "era_confidence": 0.8,
        "era_basis": "Visible cards span older and newer frames.",
        "basis": "Conservative older mixed remainder.",
        "sources": [],
    }

    calculation = _calculate(payload, AppConfig(tmp_path))

    assert calculation["singles_resale_low"] == 100.0
    assert calculation["visible_cards_net_low"] == 77.0
    assert calculation["visible_gross_coverage_percent"] == 100.0
    assert calculation["visible_backstop_applied"] is True
    assert calculation["max_buy"] == 100.0
    assert calculation["visible_backstop_ceiling_increase"] > 0
    assert calculation["verdict"] == "BUY WITH CHECKS"


def test_modern_bulk_does_not_activate_visible_value_backstop(tmp_path: Path) -> None:
    payload = _payload(asking_price=100, review=True)
    payload["cards"][0]["unit_market_low"] = 50.0  # type: ignore[index]
    payload["cards"][0]["unit_market_high"] = 60.0  # type: ignore[index]
    payload["bulk_lot"] = {
        "claimed_quantity": 1_000,
        "estimated_unitemized_quantity": 998,
        "market_low": 50.0,
        "market_high": 100.0,
        "confidence": 0.7,
        "era_profile": "mostly_modern",
        "era_confidence": 0.9,
        "era_basis": "Visible remainder is recent product.",
        "basis": "Modern bulk remainder.",
        "sources": [],
    }

    calculation = _calculate(payload, AppConfig(tmp_path))

    assert calculation["visible_backstop_applied"] is False
    assert calculation["max_buy"] < 100.0
    assert calculation["verdict"] == "PASS"


def test_api_failure_is_recorded_without_partial_artifacts(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    client = FakeResponses(_payload(), error=RuntimeError("temporary outage"))

    with pytest.raises(RuntimeError, match="temporary outage"):
        evaluate_lot(config, lot, client)

    assert not (lot / "Evaluation").exists()
    assert not (lot / "Evaluation.__building__").exists()
    assert not (lot / ".evaluation_claim.json").exists()
    error = json.loads((lot / "evaluation_error.json").read_text(encoding="utf-8"))
    assert "temporary outage" in error["reason"]


def test_changed_inputs_are_not_silently_reevaluated(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    client = FakeResponses(_payload())
    evaluate_lot(config, lot, client)
    (lot / "Prepared" / "listing_data.json").write_text('{"changed": true}', encoding="utf-8")

    with pytest.raises(EvaluationError, match="inputs changed"):
        evaluate_lot(config, lot, client)
    assert len(client.calls) == 1


def test_older_evaluation_is_archived_and_upgraded_once(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _completed_lot(config)
    first_payload = _payload()
    first_payload["cards"] = []
    client = FakeResponses(first_payload)
    evaluate_lot(config, lot, client)
    evaluation_path = lot / "Evaluation" / "evaluation.json"
    legacy = json.loads(evaluation_path.read_text(encoding="utf-8"))
    legacy["evaluator_version"] = 1
    evaluation_path.write_text(json.dumps(legacy), encoding="utf-8")
    client.payload = _payload()

    evaluate_lot(config, lot, client)

    assert (lot / "Evaluation.previous-v1" / "evaluation.json").is_file()
    upgraded = json.loads(evaluation_path.read_text(encoding="utf-8"))
    assert upgraded["evaluator_version"] == 4
    assert len(client.calls) == 2


def test_ai_configuration_is_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TCG_AI_ENABLED", raising=False)
    assert not config_from_environment(tmp_path).ai_enabled
    monkeypatch.setenv("TCG_AI_ENABLED", "yes")
    monkeypatch.setenv("TCG_OPENAI_MODEL", "configured-model")
    config = config_from_environment(tmp_path)
    assert config.ai_enabled
    assert config.openai_model == "configured-model"


def test_default_model_prioritizes_practical_vision_quality(tmp_path: Path) -> None:
    assert AppConfig(tmp_path).openai_model == "gpt-5.6-terra"


def test_prices_without_matching_web_tool_evidence_are_excluded() -> None:
    payload = _payload()

    _enforce_web_evidence(payload, {"https://different.example/source"})

    card = payload["cards"][0]  # type: ignore[index]
    assert card["unit_market_low"] is None
    assert card["unit_market_high"] is None
    assert payload["review_required"] is True
