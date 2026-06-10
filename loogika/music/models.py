from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    requested_by: str
