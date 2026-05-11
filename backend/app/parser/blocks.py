"""Block-level representation of parsed document content.

A Block is the unit the UI viewer ties to its source (page/slide number,
bbox). The DOCX writer also lays out blocks in reading order. Serialized to
JSON one file per Material under backend/data/parsed/<id>.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class Block:
    page: int                                    # 1-based
    kind: str                                    # "text" | "image_ocr" | "table" | "caption"
    text: str
    bbox: Optional[tuple[float, float, float, float]] = None  # (x0, y0, x1, y1)
    order: int = 0                               # in-page reading order


@dataclass
class ParseResult:
    blocks: list[Block] = field(default_factory=list)
    page_count: int = 0
    used_ocr: bool = False
    parser_version: str = ""

    def plain_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text and b.text.strip())

    def char_count(self) -> int:
        return sum(len(b.text or "") for b in self.blocks)


def blocks_to_json(blocks: Iterable[Block]) -> list[dict]:
    return [asdict(b) for b in blocks]


def write_blocks_json(path: Path, blocks: Iterable[Block]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = blocks_to_json(blocks)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
