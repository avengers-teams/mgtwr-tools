from dataclasses import dataclass


@dataclass
class ChartSpec:
    key: str
    label: str
    requires_beta: bool = False

