"""Game configuration service — load/save contents.json."""

import json
import os
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "static" / "data"
CONTENTS_PATH = DATA_DIR / "contents.json"


class GamesService:
    def __init__(self):
        self._data: Optional[dict] = None

    def _load(self) -> dict:
        if self._data is None:
            with open(CONTENTS_PATH, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def get_games(self) -> list[dict]:
        return self._load()["games"]

    def get_game(self, game_id: str) -> Optional[dict]:
        for g in self.get_games():
            if g["id"] == game_id:
                return g
        return None

    def update_game(self, game_id: str, updates: dict):
        data = self._load()
        for i, g in enumerate(data["games"]):
            if g["id"] == game_id:
                for k, v in updates.items():
                    data["games"][i][k] = v
                break
        self._save(data)

    def _save(self, data: dict):
        with open(CONTENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._data = data
