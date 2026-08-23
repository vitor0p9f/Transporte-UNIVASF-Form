from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    label: str
