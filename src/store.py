"""JSON file storage for veracity2 — MVP, no database needed."""

from __future__ import annotations

import json
import os
from typing import Any

from src.models import Individual, Prediction


class Store:
    """A JSON-file backed store for individuals and predictions."""

    def __init__(self, path: str):
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the file with empty structure if it doesn't exist."""
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._write_raw({"individuals": [], "predictions": []})

    def _read_raw(self) -> dict[str, Any]:
        """Read raw JSON from disk. Returns empty structure if file is corrupt/empty."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"individuals": [], "predictions": []}
                data.setdefault("individuals", [])
                data.setdefault("predictions", [])
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            return {"individuals": [], "predictions": []}

    def _write_raw(self, data: dict[str, Any]) -> None:
        """Write raw JSON to disk."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # -- Individuals --

    def add_individual(self, ind: Individual) -> None:
        """Add an individual, deduplicating by name."""
        data = self._read_raw()
        existing_names = {i["name"] for i in data["individuals"]}
        if ind.name not in existing_names:
            data["individuals"].append(ind.to_dict())
            self._write_raw(data)

    def individuals(self) -> list[Individual]:
        """Return all individuals."""
        data = self._read_raw()
        return [
            Individual(
                name=i["name"],
                handle=i["handle"],
                sources=i.get("sources", []),
                categories=i.get("categories", []),
                correct_count=i.get("correct_count", 0),
                wrong_count=i.get("wrong_count", 0),
            )
            for i in data["individuals"]
        ]

    def get_individual(self, name: str) -> Individual | None:
        """Return a specific individual by name, or None."""
        for ind in self.individuals():
            if ind.name == name:
                return ind
        return None

    # -- Predictions --

    def add_prediction(self, pred: Prediction) -> None:
        """Add a prediction, deduplicating by id."""
        data = self._read_raw()
        existing_ids = {p["id"] for p in data["predictions"]}
        if pred.id not in existing_ids:
            data["predictions"].append(pred.to_dict())
            self._write_raw(data)

    def get_predictions_for(self, individual_name: str) -> list[Prediction]:
        """Return all predictions for a given individual."""
        data = self._read_raw()
        return [
            Prediction.from_dict(p)
            for p in data["predictions"]
            if p.get("individual_name") == individual_name
        ]

    def predictions_for_category(self, category: str) -> list[Prediction]:
        """Return all predictions for a given category."""
        data = self._read_raw()
        return [
            Prediction.from_dict(p)
            for p in data["predictions"]
            if p.get("category") == category
        ]

    def get_all(self) -> list[Prediction]:
        """Return all predictions."""
        data = self._read_raw()
        return [Prediction.from_dict(p) for p in data["predictions"]]

    def get_all_raw(self) -> dict[str, Any]:
        """Return the raw JSON data (for templating / API)."""
        return self._read_raw()
