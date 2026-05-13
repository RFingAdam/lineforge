"""Tests for lineforge.design_rules.pad_classification."""
from __future__ import annotations

import pytest

from lineforge.design_rules import PadCategory, classify_pad


class TestClassifyPad:
    def test_wifi_module_is_category_1(self):
        r = classify_pad(component_type="wifi_module", has_modular_grant=True)
        assert r.category == PadCategory.FOLLOW_REFERENCE
        assert any("reference layout" in g.lower() for g in r.guidance)
        assert any("modular" in risk.lower() for risk in r.risks_if_deviating)

    def test_lte_module_is_category_1(self):
        r = classify_pad(component_type="lte_module")
        assert r.category == PadCategory.FOLLOW_REFERENCE

    def test_ufl_connector_is_category_1(self):
        r = classify_pad(component_type="u.fl")
        assert r.category == PadCategory.FOLLOW_REFERENCE
        # Should reference connector datasheet
        assert any("connector" in g.lower() for g in r.guidance)

    @pytest.mark.parametrize("conn", ["sma", "mmcx", "rp-sma", "n_type"])
    def test_rf_connector_variants_all_category_1(self, conn):
        assert classify_pad(component_type=conn).category == PadCategory.FOLLOW_REFERENCE

    def test_triplexer_is_category_2(self):
        r = classify_pad(component_type="triplexer")
        assert r.category == PadCategory.OPTIMIZE
        assert any("pad_relief_advisor" in g.lower() for g in r.guidance)

    def test_diplexer_is_category_2(self):
        r = classify_pad(component_type="diplexer")
        assert r.category == PadCategory.OPTIMIZE

    def test_discrete_lc_is_category_2(self):
        r = classify_pad(component_type="discrete_lc")
        assert r.category == PadCategory.OPTIMIZE

    def test_user_designed_flag(self):
        """Explicit is_user_designed_rf flag forces Category 2."""
        r = classify_pad(component_type="custom_filter", is_user_designed_rf=True)
        assert r.category == PadCategory.OPTIMIZE

    def test_power_pad_is_category_3(self):
        r = classify_pad(component_type="power")
        assert r.category == PadCategory.STANDARD

    def test_low_speed_pad_is_category_3(self):
        r = classify_pad(component_type="low_speed_io")
        assert r.category == PadCategory.STANDARD

    def test_low_frequency_forces_category_3(self):
        """< 100 MHz operation → Category 3 even for RF-named components."""
        r = classify_pad(component_type="discrete_lc", operating_freq_ghz=0.05)
        assert r.category == PadCategory.STANDARD

    def test_rf_ic_category_1(self):
        for ic in ["lna", "mixer", "pa", "vco", "synthesizer"]:
            r = classify_pad(component_type=ic)
            assert r.category == PadCategory.FOLLOW_REFERENCE

    def test_unknown_defaults_to_category_1(self):
        """Ambiguous types get Category 1 as the safe default."""
        r = classify_pad(component_type="unknown_xyz_part")
        assert r.category == PadCategory.FOLLOW_REFERENCE
        assert any("ambiguous" in g.lower() for g in r.guidance)
