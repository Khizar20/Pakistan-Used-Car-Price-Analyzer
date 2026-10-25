"""Phase 7 canonical palette has readable foregrounds in both themes."""

import json
from pathlib import Path

import pytest

TOKENS = json.loads((Path(__file__).parents[2] / "web/design/tokens.json").read_text())


def luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels
    ]
    return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("foreground", ["ink", "muted", "motorway", "signal"])
def test_text_palette_meets_wcag_aa(theme: str, foreground: str) -> None:
    levels = sorted(
        (luminance(TOKENS[theme][foreground]), luminance(TOKENS[theme]["paper"]))
    )
    assert (levels[1] + 0.05) / (levels[0] + 0.05) >= 4.5
