"""Tests for the units helper."""

from __future__ import annotations

import pytest

from lineforge.units import awg_to_meters, parse_frequency, parse_length


class TestParseLength:
    def test_bare_meters(self) -> None:
        assert parse_length(1.5e-4) == pytest.approx(1.5e-4)

    def test_mil_string(self) -> None:
        assert parse_length("6 mil") == pytest.approx(6 * 25.4e-6)

    def test_mil_no_space(self) -> None:
        assert parse_length("6mil") == pytest.approx(6 * 25.4e-6)

    def test_mm(self) -> None:
        assert parse_length("4 mm") == pytest.approx(4e-3)

    def test_inches(self) -> None:
        assert parse_length("0.5 in") == pytest.approx(0.0127)

    def test_awg_30(self) -> None:
        # AWG 30 ≈ 0.255 mm
        assert parse_length("30AWG") == pytest.approx(2.55e-4, rel=2e-2)

    def test_awg_with_space(self) -> None:
        assert parse_length("30 AWG") == pytest.approx(parse_length("30AWG"))

    def test_scientific_in_meters(self) -> None:
        assert parse_length("13e-3 m") == pytest.approx(13e-3)

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_length("blah")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_length("   ")


class TestAwgToMeters:
    @pytest.mark.parametrize(
        ("awg", "expected_mm"),
        [
            (10, 2.588),
            (20, 0.812),
            (30, 0.255),
            (40, 0.0799),
        ],
    )
    def test_known_values(self, awg: int, expected_mm: float) -> None:
        assert awg_to_meters(awg) * 1e3 == pytest.approx(expected_mm, rel=1e-2)


class TestParseFrequency:
    def test_bare_hz(self) -> None:
        assert parse_frequency(1e9) == pytest.approx(1e9)

    def test_ghz_string(self) -> None:
        assert parse_frequency("2.4 GHz") == pytest.approx(2.4e9)

    def test_mhz(self) -> None:
        assert parse_frequency("100 MHz") == pytest.approx(1e8)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_frequency("not-a-frequency")
