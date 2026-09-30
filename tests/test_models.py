from src.models import Individual, Prediction
from datetime import date

def test_individual_creation():
    ind = Individual(
        name="Peter Zeihan",
        handle="zeihan",
        sources=["https://youtube.com/@ZeihanonGeopolitics"],
        categories=["geopolitics", "energy", "china"],
    )
    assert ind.name == "Peter Zeihan"
    assert ind.handle == "zeihan"
    assert "geopolitics" in ind.categories
    assert ind.primary_category == "geopolitics"


def test_doomberg_individual():
    ind = Individual(
        name="Doomberg",
        handle="doomberg",
        sources=["https://newsletter.doomberg.com"],
        categories=["energy", "finance"],
    )
    assert ind.primary_category == "energy"


def test_prediction_creation():
    pred = Prediction(
        id="pred_001",
        individual_name="Peter Zeihan",
        date=date(2024, 3, 15),
        category="china",
        claim="China will collapse within 10 years",
        source_url="https://youtube.com/watch?v=abc123",
        transcript_excerpt="...",
        verdict=None,
    )
    assert pred.individual_name == "Peter Zeihan"
    assert pred.verdict is None
    assert pred.created_at is not None
