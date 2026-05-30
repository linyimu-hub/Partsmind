"""
Unit tests for Agent tools.
All external calls (OpenAI, DB) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.tools.lookup_tool import check_vehicle_compatibility

# ── Compatibility tool (pure function, no mocks needed) ───────────────────────
SAMPLE_PRODUCT = {
    "id": "abc",
    "name": "Brake Pad Set",
    "compatible_vehicles": [
        {"make": "Toyota", "model": "Camry", "year_from": 2018, "year_to": 2023},
        {"make": "Honda",  "model": "Accord","year_from": 2019, "year_to": 2024},
    ],
}


def test_compatibility_match():
    result = check_vehicle_compatibility(SAMPLE_PRODUCT, "Toyota", "Camry", 2020)
    assert result["compatible"] is True
    assert "Toyota" in result["reason"]


def test_compatibility_year_out_of_range():
    result = check_vehicle_compatibility(SAMPLE_PRODUCT, "Toyota", "Camry", 2015)
    assert result["compatible"] is False


def test_compatibility_wrong_make():
    result = check_vehicle_compatibility(SAMPLE_PRODUCT, "Ford", "F150", 2021)
    assert result["compatible"] is False
    assert "Toyota" in result["reason"] or "Honda" in result["reason"]


def test_compatibility_no_vehicle_specified():
    result = check_vehicle_compatibility(SAMPLE_PRODUCT, None, None, None)
    assert result["compatible"] is None


def test_compatibility_no_vehicle_data():
    product_no_compat = {**SAMPLE_PRODUCT, "compatible_vehicles": []}
    result = check_vehicle_compatibility(product_no_compat, "Toyota", "Camry", 2020)
    assert result["compatible"] is None
    assert "not available" in result["reason"]


# ── Vision tool (mocked OpenAI) ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_vision_tool_returns_structured_output():
    mock_response_json = """{
        "part_name": "brake pad",
        "part_category": "brake",
        "brand_visible": "Bosch",
        "part_number_visible": null,
        "condition": "new",
        "key_attributes": {"material": "ceramic", "position": "front"},
        "search_terms": ["brake pad", "ceramic brake", "Bosch brake"],
        "identification_confidence": 0.92,
        "notes": "Standard front brake pad"
    }"""

    with patch("app.agent.tools.vision_tool._client") as mock_client:
        mock_choice = MagicMock()
        mock_choice.message.content = mock_response_json
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[mock_choice])
        )

        from app.agent.tools.vision_tool import run_vision_tool
        result = await run_vision_tool("fake_base64_data", "image/jpeg")

    assert result["part_name"] == "brake pad"
    assert result["identification_confidence"] == 0.92
    assert "brake pad" in result["search_terms"]


@pytest.mark.asyncio
async def test_vision_tool_handles_markdown_wrapped_json():
    """Model sometimes wraps JSON in markdown code fences."""
    wrapped = '```json\n{"part_name": "air filter", "part_category": "filter", "brand_visible": null, "part_number_visible": null, "condition": "new", "key_attributes": {}, "search_terms": ["air filter"], "identification_confidence": 0.85, "notes": ""}\n```'

    with patch("app.agent.tools.vision_tool._client") as mock_client:
        mock_choice = MagicMock()
        mock_choice.message.content = wrapped
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[mock_choice])
        )

        from app.agent.tools.vision_tool import run_vision_tool
        result = await run_vision_tool("fake_base64", "image/png")

    assert result["part_name"] == "air filter"
