"""Tests for frequency-dependent dielectric properties."""

from __future__ import annotations

from pathlib import Path

import pytest

from lineforge.materials import MaterialRecord, load_json_pack
from lineforge.materials.dispersion import interpolate_log_freq, material_at_frequency


class TestInterpolateLogFreq:
    def test_endpoint_low(self) -> None:
        table = {1e9: 4.40, 1e10: 4.30}
        assert interpolate_log_freq(table, 1e9) == pytest.approx(4.40)

    def test_endpoint_high(self) -> None:
        table = {1e9: 4.40, 1e10: 4.30}
        assert interpolate_log_freq(table, 1e10) == pytest.approx(4.30)

    def test_below_range_clamps(self) -> None:
        table = {1e9: 4.40, 1e10: 4.30}
        assert interpolate_log_freq(table, 1e8) == pytest.approx(4.40)

    def test_above_range_clamps(self) -> None:
        table = {1e9: 4.40, 1e10: 4.30}
        assert interpolate_log_freq(table, 1e11) == pytest.approx(4.30)

    def test_log_midpoint(self) -> None:
        """A geometric-mean frequency should be at the linear midpoint."""
        table = {1e9: 4.40, 1e10: 4.30}
        # Mid-decade in log space: sqrt(1e9 * 1e10) ≈ 3.162e9
        assert interpolate_log_freq(table, 3.16227766e9) == pytest.approx(4.35, abs=1e-3)

    def test_three_point_table(self) -> None:
        """A 3-point table interpolates within the right segment."""
        table = {1e9: 3.71, 5e9: 3.66, 25e9: 3.59}
        # Between 1 and 5 GHz
        v_2_5 = interpolate_log_freq(table, 2.5e9)
        assert 3.66 < v_2_5 < 3.71
        # Between 5 and 25 GHz
        v_10 = interpolate_log_freq(table, 1e10)
        assert 3.59 < v_10 < 3.66

    def test_zero_freq_raises(self) -> None:
        with pytest.raises(ValueError, match="freq_hz must be positive"):
            interpolate_log_freq({1e9: 4.0, 2e9: 3.9}, 0.0)

    def test_single_point_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 points"):
            interpolate_log_freq({1e9: 4.0}, 5e9)


class TestMaterialAtFrequency:
    def test_no_freq_uses_constants(self) -> None:
        er, tan = material_at_frequency(
            er=4.4, tan_delta=0.02, er_freq=None, tan_freq=None, freq_hz=None
        )
        assert er == 4.4
        assert tan == 0.02

    def test_no_table_falls_back_to_constants(self) -> None:
        er, tan = material_at_frequency(
            er=4.4, tan_delta=0.02, er_freq=None, tan_freq=None, freq_hz=5e9
        )
        assert er == 4.4
        assert tan == 0.02

    def test_partial_table_only_er(self) -> None:
        """If only er_freq is given, tan_delta uses the constant."""
        er, tan = material_at_frequency(
            er=4.4,
            tan_delta=0.02,
            er_freq={1e9: 4.4, 1e10: 4.2},
            tan_freq=None,
            freq_hz=5e9,
        )
        assert 4.2 < er < 4.4
        assert tan == 0.02


class TestMaterialRecordDispersion:
    def test_at_frequency_with_table(self) -> None:
        m = MaterialRecord(
            rgb=(100, 100, 100),
            use="insul",
            er=4.0,
            tan_delta=0.01,
            er_freq={1e9: 4.4, 1e10: 4.2},
            tan_freq={1e9: 0.01, 1e10: 0.018},
            name="test material",
        )
        er, tan = m.at_frequency(5e9)
        assert 4.2 < er < 4.4
        assert 0.01 < tan < 0.018

    def test_at_frequency_without_table(self) -> None:
        m = MaterialRecord(rgb=(100, 100, 100), use="insul", er=4.0, tan_delta=0.01, name="bulk")
        er, tan = m.at_frequency(5e9)
        assert er == 4.0
        assert tan == 0.01

    def test_freezeable_with_dicts(self) -> None:
        """MaterialRecord is frozen=True; dict fields must work anyway."""
        from pydantic import ValidationError

        m = MaterialRecord(
            rgb=(100, 100, 100),
            use="insul",
            er=4.0,
            tan_delta=0.01,
            er_freq={1e9: 4.4, 1e10: 4.2},
            name="frozen test",
        )
        # Frozen: assignment must fail with Pydantic's ValidationError.
        with pytest.raises(ValidationError):
            m.er = 5.0  # type: ignore[misc]


class TestPcbExtendedPack:
    @pytest.fixture
    def pack_path(self) -> Path:
        return Path(__file__).parent.parent / "src/lineforge/materials/packs/pcb_extended.json"

    def test_loads(self, pack_path: Path) -> None:
        records = load_json_pack(pack_path)
        assert len(records) >= 18

    def test_rogers_ro4350b_dispersion(self, pack_path: Path) -> None:
        records = load_json_pack(pack_path)
        ro4350b = next(r for r in records if "RO4350B" in r.name)
        assert ro4350b.er_freq is not None
        # Datasheet: Dk barely changes 100 MHz → 10 GHz, then drops slightly at 40 GHz.
        assert ro4350b.at_frequency(1e9)[0] == pytest.approx(3.66, abs=1e-3)
        assert ro4350b.at_frequency(40e9)[0] == pytest.approx(3.65, abs=1e-3)

    def test_megtron_6_dispersion(self, pack_path: Path) -> None:
        records = load_json_pack(pack_path)
        m6 = next(r for r in records if "Megtron 6" in r.name)
        assert m6.er_freq is not None
        # Dk drifts from 3.71 (1 GHz) → 3.59 (25 GHz)
        er_low, _ = m6.at_frequency(1e9)
        er_high, _ = m6.at_frequency(25e9)
        assert er_low > er_high
        assert er_low == pytest.approx(3.71, abs=1e-3)
        assert er_high == pytest.approx(3.59, abs=1e-3)
        # tan_δ rises with frequency (lossy mode dispersion)
        _, tan_low = m6.at_frequency(1e9)
        _, tan_high = m6.at_frequency(25e9)
        assert tan_high > tan_low

    def test_isola_370hr_dispersion(self, pack_path: Path) -> None:
        records = load_json_pack(pack_path)
        i370 = next(r for r in records if "Isola 370HR" in r.name)
        assert i370.er_freq is not None
        # Datasheet 1 GHz Dk = 4.04, 10 GHz Dk = 3.92
        assert i370.at_frequency(1e9)[0] == pytest.approx(4.04, abs=1e-3)
        assert i370.at_frequency(1e10)[0] == pytest.approx(3.92, abs=1e-3)

    def test_legacy_records_no_freq_table_pass_through(self, pack_path: Path) -> None:
        """Materials without er_freq still work: at_frequency returns the constant."""
        records = load_json_pack(pack_path)
        ro3010 = next(r for r in records if "RO3010" in r.name)
        assert ro3010.er_freq is None
        er, tan = ro3010.at_frequency(5e9)
        assert er == ro3010.er
        assert tan == ro3010.tan_delta

    def test_all_vendor_names_present(self, pack_path: Path) -> None:
        """The pack covers the major laminate vendors per the plan."""
        records = load_json_pack(pack_path)
        names = " ".join(r.name for r in records)
        for vendor in [
            "RO4350B",
            "RO4003C",
            "RO3010",
            "RO3003",
            "Megtron 6",
            "Megtron 4",
            "Megtron 7",
            "Isola 370HR",
            "I-Tera",
            "Tachyon",
            "ITEQ IT-150",
            "ITEQ IT-180",
        ]:
            assert vendor in names, f"missing {vendor!r} from pcb_extended.json"
