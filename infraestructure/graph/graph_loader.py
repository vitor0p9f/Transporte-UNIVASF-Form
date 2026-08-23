import json
from pathlib import Path
from typing import Any

type GraphData = dict[str, Any]

def graph_loader(file_path: Path) -> GraphData:
    if not file_path.is_file():
        raise FileNotFoundError(f"Graph file not found: {file_path}")

    with file_path.open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    return data
