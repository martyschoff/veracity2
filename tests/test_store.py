import json, tempfile, os
from src.models import Individual, Prediction
from src.store import Store
from datetime import date


def test_store_add_and_retrieve():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = Store(f.name)
    ind = Individual(
        name="Peter Zeihan",
        handle="zeihan",
        sources=["https://youtube.com/@ZeihanonGeopolitics"],
        categories=["geopolitics"],
    )
    store.add_individual(ind)
    pred = Prediction(
        id="p1",
        individual_name="Peter Zeihan",
        date=date(2024, 1, 15),
        category="china",
        claim="China collapses",
        source_url="https://youtube.com/watch?v=x",
        transcript_excerpt="...",
        verdict=None,
    )
    store.add_prediction(pred)
    loaded = Store(f.name)
    assert len(loaded.individuals()) == 1
    assert len(loaded.get_predictions_for("Peter Zeihan")) == 1
    os.unlink(f.name)


def test_store_no_duplicates():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = Store(f.name)
    ind = Individual(
        name="Doomberg",
        handle="doomberg",
        sources=["https://newsletter.doomberg.com"],
        categories=["finance", "energy"],
    )
    store.add_individual(ind)
    store.add_individual(ind)  # should not duplicate
    assert len(Store(f.name).individuals()) == 1
    os.unlink(f.name)


def test_store_prediction_no_duplicates():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = Store(f.name)
    ind = Individual(
        name="Doomberg",
        handle="doomberg",
        sources=["https://newsletter.doomberg.com"],
        categories=["energy", "finance"],
    )
    store.add_individual(ind)
    pred = Prediction(
        id="p99",
        individual_name="Doomberg",
        date=date(2024, 2, 1),
        category="energy",
        claim="Oil to $150",
        source_url="https://youtube.com/watch?v=y",
        transcript_excerpt="oil spike",
        verdict=None,
    )
    store.add_prediction(pred)
    store.add_prediction(pred)  # duplicate id, should not add
    assert len(Store(f.name).get_predictions_for("Doomberg")) == 1
    os.unlink(f.name)


def test_store_predictions_for_category():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = Store(f.name)
    ind = Individual(
        name="Peter Zeihan",
        handle="zeihan",
        sources=["https://youtube.com/@ZeihanonGeopolitics"],
        categories=["geopolitics"],
    )
    store.add_individual(ind)
    p1 = Prediction(
        id="c1",
        individual_name="Peter Zeihan",
        date=date(2024, 3, 1),
        category="china",
        claim="China collapses",
        source_url="https://youtube.com/watch?v=a",
        transcript_excerpt="...",
        verdict=None,
    )
    p2 = Prediction(
        id="c2",
        individual_name="Peter Zeihan",
        date=date(2024, 3, 2),
        category="energy",
        claim="Oil spikes",
        source_url="https://youtube.com/watch?v=b",
        transcript_excerpt="...",
        verdict=None,
    )
    store.add_prediction(p1)
    store.add_prediction(p2)
    loaded = Store(f.name)
    assert len(loaded.predictions_for_category("china")) == 1
    assert len(loaded.predictions_for_category("energy")) == 1
    assert len(loaded.get_all()) == 2
    os.unlink(f.name)
