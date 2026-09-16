"""N-port Touchstone export round-trips through scikit-rf and writes version 2 headers."""

from __future__ import annotations

import numpy as np
import pytest

skrf = pytest.importorskip("skrf")

from lineforge.touchstone import to_touchstone_nport  # noqa: E402  (skrf import-skip above)


def _sample(ports: int = 4, n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    f = np.linspace(1e9, 5e9, n)
    rng = np.random.default_rng(1)
    s = (rng.normal(size=(n, ports, ports)) + 1j * rng.normal(size=(n, ports, ports))) * 0.1
    return f, s


def test_v1_roundtrip(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan", z_ref=50.0)
    assert path.suffix == ".s4p"
    net = skrf.Network(str(path))
    np.testing.assert_allclose(net.s, s, atol=1e-9)
    np.testing.assert_allclose(net.f, f)


def test_v2_header_and_mixed_mode(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(
        f,
        s,
        tmp_path / "chan.s4p",
        z_ref=[50, 50, 50, 50],
        mixed_mode_order=["D1,2", "C1,2", "D3,4", "C3,4"],
        version=2,
    )
    text = path.read_text()
    assert "[Version] 2.0" in text
    assert "[Number of Ports] 4" in text
    assert "[Reference] 50 50 50 50" in text
    assert "[Mixed-Mode Order] D1,2 C1,2 D3,4 C3,4" in text
    assert "[Number of Frequencies] 5" in text
    assert text.strip().endswith("[End]")


def test_v2_two_port_roundtrip(tmp_path) -> None:
    f, s = _sample(ports=2)
    path = to_touchstone_nport(f, s, tmp_path / "chan2", z_ref=50.0, version=2)
    text = path.read_text()
    assert "[Two-Port Data Order] 12_21" in text
    net = skrf.Network(str(path))
    np.testing.assert_allclose(net.s, s, atol=1e-9)
    np.testing.assert_allclose(net.f, f)


def test_shape_validation(tmp_path) -> None:
    f, s = _sample()
    with pytest.raises(ValueError):
        to_touchstone_nport(f[:-1], s, tmp_path / "bad")
