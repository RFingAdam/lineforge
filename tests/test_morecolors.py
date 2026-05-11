"""Phase 2.2 AC: MoreColors.txt parser matches atlc2 docs format."""

from __future__ import annotations

import pytest

from lineforge.materials.morecolors import (
    MoreColorsParseError,
    dedupe_keep_last,
    dump_json_pack,
    load_json_pack,
    parse_morecolors_text,
    to_morecolors_text,
)

# The exact sample from atlc2 docs
SAMPLE_DOC = """\
| red:  green:   blue:   use:    Ohms:    Er:     tanDelta:  Mu:  name:
250     20       20      +1       7.3     1       0          1    Cadmium
30      255      30      0        20.6    1       0          1    Lead
180     180      120     insul    0       6.0     0.0007     1    Mica
30      30       30      insul    0       3.5     0.0040     1    Hard rubber
100     140      170     insul    0       4       0.0030     1    Silicone
"""


class TestParser:
    def test_parses_atlc2_docs_sample(self) -> None:
        records = parse_morecolors_text(SAMPLE_DOC)
        assert len(records) == 5
        assert records[0].rgb == (250, 20, 20)
        assert records[0].use == "+1"
        assert records[0].name == "Cadmium"
        assert records[2].name == "Mica"
        assert records[2].er == pytest.approx(6.0)

    def test_preserves_multiword_name(self) -> None:
        records = parse_morecolors_text(SAMPLE_DOC)
        names = [r.name for r in records]
        assert "Hard rubber" in names

    def test_comments_ignored(self) -> None:
        text = "| this is a comment\n255 0 0 +1 1.7 1 0 1 my copper\n"
        records = parse_morecolors_text(text)
        assert len(records) == 1
        assert records[0].rgb == (255, 0, 0)
        assert records[0].name == "my copper"

    def test_blank_lines_allowed(self) -> None:
        text = "\n\n255 0 0 +1 1.7 1 0 1 copper\n\n0 255 0 0 1.7 1 0 1 ground\n"
        records = parse_morecolors_text(text)
        assert len(records) == 2

    def test_tabs_treated_as_blanks(self) -> None:
        text = "255\t0\t0\t+1\t1.7\t1\t0\t1\ttabbed copper\n"
        records = parse_morecolors_text(text)
        assert len(records) == 1
        assert records[0].name == "tabbed copper"

    def test_invalid_use_raises(self) -> None:
        text = "255 0 0 nonsense 1 1 0 1 something\n"
        with pytest.raises(MoreColorsParseError) as info:
            parse_morecolors_text(text)
        assert info.value.lineno == 1

    def test_too_few_fields_raises(self) -> None:
        text = "255 0 0 +1\n"
        with pytest.raises(MoreColorsParseError):
            parse_morecolors_text(text)

    def test_rgb_out_of_range_raises(self) -> None:
        text = "300 0 0 +1 1.7 1 0 1 broken\n"
        with pytest.raises(MoreColorsParseError):
            parse_morecolors_text(text)


class TestDedupe:
    def test_last_wins(self) -> None:
        text = "255 0 0 +1 1.7 1 0 1 first\n" "255 0 0 +1 1.7 1 0 1 second\n"
        records = parse_morecolors_text(text)
        deduped = dedupe_keep_last(records)
        assert len(deduped) == 1
        assert deduped[0].name == "second"


class TestRoundTrip:
    def test_text_round_trip_preserves_records(self) -> None:
        records = parse_morecolors_text(SAMPLE_DOC)
        text = to_morecolors_text(records)
        records2 = parse_morecolors_text(text)
        assert len(records) == len(records2)
        for a, b in zip(records, records2, strict=True):
            assert a.rgb == b.rgb
            assert a.use == b.use
            assert a.name == b.name


class TestJsonPack:
    def test_dump_and_load(self, tmp_path: object) -> None:
        records = parse_morecolors_text(SAMPLE_DOC)
        json_str = dump_json_pack(records, name="docs-sample")
        path = tmp_path / "pack.json"  # type: ignore[operator]
        path.write_text(json_str)
        records2 = load_json_pack(path)
        assert len(records) == len(records2)
        assert records[0].rgb == records2[0].rgb
