"""跨日存续状态（LocalRunStore）。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EpisodeState:
    episode_id: str
    manage_area: str
    process_leaf: str
    started_on: str
    last_seen_on: str
    streak_days: int


class LocalRunStore:
    def __init__(self, root: Path):
        self.state_dir = root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.episodes_path = self.state_dir / "episodes.json"

    def load_episodes(self) -> dict[str, EpisodeState]:
        if not self.episodes_path.is_file():
            return {}
        try:
            raw = json.loads(self.episodes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        out: dict[str, EpisodeState] = {}
        for k, v in raw.items():
            out[k] = EpisodeState(**v)
        return out

    def save_episodes(self, episodes: dict[str, EpisodeState]) -> None:
        payload = {k: vars(v) for k, v in episodes.items()}
        self.episodes_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
