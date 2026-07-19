"""
Time-control helpers.

Encodes Lichess-style time controls as ``"<base>+<inc>"`` where base is in
minutes and increment in seconds (e.g. ``"3+2"``). The server stores clocks
in milliseconds to keep SocketIO updates accurate; this module is the single
place that converts between human strings and milliseconds.
"""

from dataclasses import dataclass

# Preset time controls grouped like the Lichess interface.
TIME_CONTROL_PRESETS = {
    "Bullet": ["1+0", "2+1", "3+0"],
    "Blitz": ["3+2", "5+0", "5+3", "10+0"],
    "Rapid": ["10+5", "15+10", "30+0"],
    "Classical": ["30+20", "45+45", "60+30"],
}


@dataclass
class TimeControl:
    base_ms: int
    increment_ms: int
    label: str

    @property
    def base_seconds(self) -> int:
        return self.base_ms // 1000

    @property
    def increment_seconds(self) -> int:
        return self.increment_ms // 1000

    def parse(self) -> "TimeControl":
        return self

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "base_ms": self.base_ms,
            "increment_ms": self.increment_ms,
            "base_seconds": self.base_seconds,
            "increment_seconds": self.increment_seconds,
        }


def parse_time_control(spec: str) -> TimeControl:
    """Parse ``"base+inc"`` (minutes + seconds) into a ``TimeControl``."""
    spec = (spec or "5+3").strip()
    if "+" not in spec:
        # Assume whole minutes, no increment.
        spec = f"{spec}+0"
    base, _, inc = spec.partition("+")
    try:
        base_min = float(base)
        inc_sec = float(inc)
    except ValueError:
        base_min, inc_sec = 5.0, 3.0
    return TimeControl(
        base_ms=int(base_min * 60_000),
        increment_ms=int(inc_sec * 1000),
        label=spec,
    )


def format_clock(ms: int) -> str:
    """Format milliseconds as ``M:SS`` (or ``H:MM:SS`` past an hour)."""
    if ms is None or ms < 0:
        ms = 0
    total = ms // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def is_legal_custom_time_control(base_min: float, inc_sec: float) -> bool:
    """Validate a custom time control against sane limits."""
    if not (0 < base_min <= 180 and 0 <= inc_sec <= 120):
        return False
    return True
