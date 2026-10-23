from dataclasses import dataclass, field

@dataclass(frozen=True)
class Region:
    name: str
    start: int
    data: bytes
    executable: bool
    writable: bool = False

@dataclass(frozen=True)
class Seed:
    address: int
    name: str
    source: str

@dataclass(frozen=True)
class Image:
    format: str
    arch: str
    bits: int
    entry: int
    regions: list[Region]
    seeds: list[Seed]
    metadata: dict = field(default_factory=dict)
