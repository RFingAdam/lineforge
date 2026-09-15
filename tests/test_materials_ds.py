"""Causal dielectric parameters and roughness metadata on MaterialRecord."""

from __future__ import annotations

import json
import math

import pytest

from lineforge.materials.database import DSParams, MaterialRecord, RoughnessSpec
from lineforge.materials.morecolors import dump_json_pack, load_json_pack


def test_ds_fit_point_reproduces_anchor_and_is_lossy() -> None:
    ds = DSParams.fit_point(er=4.3, tan_delta=0.02, f_ref_hz=1e9)
    e = ds.er_complex(1e9)
    assert e.real == pytest.approx(4.3, rel=1e-9)
    assert -e.imag / e.real == pytest.approx(0.02, rel=1e-9)
    assert ds.er_complex(1e6).real > ds.er_complex(1e10).real
    assert ds.er_complex(1e7).imag < 0


def test_material_er_complex_prefers_ds_then_tables_then_constants() -> None:
    ds = DSParams.fit_point(er=3.66, tan_delta=0.0037, f_ref_hz=1e10)
    m_ds = MaterialRecord(
        rgb=(1, 2, 3), use="insul", er=3.66, tan_delta=0.0037, name="ro4350-ds", ds_params=ds
    )
    m_tab = MaterialRecord(
        rgb=(1, 2, 4),
        use="insul",
        er=3.66,
        tan_delta=0.0037,
        name="ro4350-tab",
        er_freq={1e8: 3.66, 4e10: 3.65},
        tan_freq={1e8: 0.004, 4e10: 0.0048},
    )
    m_const = MaterialRecord(rgb=(1, 2, 5), use="insul", er=3.66, tan_delta=0.0037, name="ro4350")
    assert m_ds.er_complex(1e10).real == pytest.approx(3.66, rel=1e-9)
    assert m_tab.er_complex(1e8).real == pytest.approx(3.66)
    assert m_tab.er_complex(4e10) == pytest.approx(complex(3.65, -3.65 * 0.0048))
    assert m_const.er_complex(1e9) == pytest.approx(complex(3.66, -3.66 * 0.0037))


def test_roughness_spec_and_pack_roundtrip(tmp_path) -> None:
    rough = RoughnessSpec(model="huray", radius_um=0.5, ratio=4.887)
    cu = MaterialRecord(rgb=(255, 0, 0), use="+1", name="rough copper", roughness=rough)
    text = dump_json_pack([cu], name="t", version="1.0.0")
    data = json.loads(text)
    assert data["materials"][0]["roughness"]["model"] == "huray"
    path = tmp_path / "pack.json"
    path.write_text(text)
    back = load_json_pack(path)
    assert back[0].roughness == rough
    assert back[0].ds_params is None


def test_roughness_spec_requires_model_parameters() -> None:
    with pytest.raises(ValueError):
        RoughnessSpec(model="hammerstad")
    with pytest.raises(ValueError):
        RoughnessSpec(model="huray", radius_um=0.5)
    assert RoughnessSpec(model="huray", rz_um=6.0).radius_um == pytest.approx(
        6.0 / (2 * (1 + math.sqrt(2)))
    )
