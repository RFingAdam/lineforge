"""Tests for lineforge.materials.laminates."""

from __future__ import annotations

import pytest

from lineforge.materials.laminates import laminate_lookup, list_laminates


class TestLaminateLookup:
    def test_exact_match(self):
        r = laminate_lookup("Isola 370HR")
        assert r.name == "Isola 370HR"
        assert r.matched_by == "exact"
        assert r.er > 0
        assert r.tan_delta > 0

    def test_alias_fr4_prepreg(self):
        r = laminate_lookup("FR4 prepreg")
        assert "Prepreg" in r.name
        assert r.matched_by == "alias"
        assert r.er == pytest.approx(3.7)

    def test_alias_fr4_core(self):
        r = laminate_lookup("FR4 core")
        assert "Core" in r.name
        assert r.matched_by == "alias"
        assert r.er == pytest.approx(4.2)

    def test_alias_fr4_nominal(self):
        r = laminate_lookup("FR4")
        assert r.matched_by == "alias"
        assert r.er == pytest.approx(4.4)

    def test_alias_short_name(self):
        r = laminate_lookup("RO4350B")
        assert r.name == "Rogers RO4350B"
        assert r.matched_by == "alias"

    def test_alias_megtron(self):
        r = laminate_lookup("M6")
        assert "Megtron 6" in r.name

    def test_case_insensitive(self):
        r1 = laminate_lookup("ISOLA 370HR")
        r2 = laminate_lookup("isola 370hr")
        assert r1.name == r2.name

    def test_unknown_raises(self):
        with pytest.raises(KeyError, match="No laminate"):
            laminate_lookup("Bogus Material XYZ")

    def test_frequency_interpolation(self):
        """Rogers RO4350B has er_freq table — verify interpolation."""
        laminate_lookup("Rogers RO4350B")
        r_at_10g = laminate_lookup("Rogers RO4350B", frequency_ghz=10)
        # er_freq table has 10 GHz point at εr=3.66 (or close)
        assert 3.5 < r_at_10g.er < 3.8

    def test_frequency_ghz_passed_through(self):
        r = laminate_lookup("Rogers RO4350B", frequency_ghz=2.5)
        assert r.frequency_ghz == 2.5

    def test_list_laminates_returns_sorted(self):
        names = list_laminates()
        assert len(names) >= 15
        assert names == sorted(names)
        # Spot-check
        assert "FR4 nominal (er=4.4)" in names
