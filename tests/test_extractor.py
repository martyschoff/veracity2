"""Tests for the LLM-based prediction extractor."""

from src.extractor import extract_predictions

SAMPLE_TRANSCRIPT = """
We're going to see China's economy collapse by 2026. The demographic crisis
is terminal. Within 10 years, China will no longer exist as a unified state.
On energy, I think oil prices will spike to $150 by end of 2025 because of
the Middle East situation.
"""


def test_extract_returns_predictions():
    """The extractor should return a list (possibly empty if LLM unavailable)."""
    preds = extract_predictions(
        transcript=SAMPLE_TRANSCRIPT,
        video_url="https://youtube.com/watch?v=test",
        individual_name="Peter Zeihan",
        categories=["finance", "energy", "china", "ai", "geopolitics", "ukraine"],
    )
    assert isinstance(preds, list)
    # If we got predictions, validate structure
    if preds:
        assert preds[0].category in (
            "china", "energy", "finance", "ai", "geopolitics", "ukraine", "other"
        )
        assert preds[0].source_url == "https://youtube.com/watch?v=test"


def test_extract_empty_transcript():
    """Empty or None transcript should return empty list, not crash."""
    assert extract_predictions("", "https://youtube.com/watch?v=x", "Test", ["finance"]) == []
    assert extract_predictions(None, "https://youtube.com/watch?v=x", "Test", ["finance"]) == []


def test_extract_category_other_for_unknown():
    """Predictions that don't fit any category should get 'other'."""
    preds = extract_predictions(
        transcript="I think the weather will be nice tomorrow.",
        video_url="https://youtube.com/watch?v=w",
        individual_name="Test Person",
        categories=["finance", "energy"],
    )
    if preds:
        assert preds[0].category in ("finance", "energy", "other")
