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


def test_v1_refuses_differing_per_port_references(tmp_path) -> None:
    """Touchstone 1.x has one R on the option line; the other ports' values would vanish."""
    f, s = _sample()
    with pytest.raises(ValueError, match="version=2"):
        to_touchstone_nport(f, s, tmp_path / "chan", z_ref=[50, 50, 75, 100], version=1)


def test_v1_accepts_a_uniform_per_port_reference_list(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan", z_ref=[50, 50, 50, 50], version=1)
    net = skrf.Network(str(path))
    np.testing.assert_allclose(net.s, s, atol=1e-9)


def test_v2_keeps_differing_per_port_references(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan", z_ref=[50, 50, 75, 100], version=2)
    assert "[Reference] 50 50 75 100" in path.read_text()


def test_dotted_stem_survives_the_suffix_swap(tmp_path) -> None:
    """``with_suffix('')`` would turn chan_v1.2.s4p into chan_v1.s4p."""
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan_v1.2.s4p", z_ref=50.0, version=1)
    assert path.name == "chan_v1.2.s4p"
    assert path.exists()
    assert not (tmp_path / "chan_v1.s4p").exists()


def test_v2_writes_one_matrix_row_per_line_in_the_canonical_order(tmp_path) -> None:
    f, s = _sample(ports=4, n=3)
    path = to_touchstone_nport(
        f,
        s,
        tmp_path / "chan",
        z_ref=[50, 50, 75, 100],
        mixed_mode_order=["D1,2", "C1,2", "D3,4", "C3,4"],
        version=2,
        comment="lineforge",
    )
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    keywords = [ln.split("]")[0] + "]" for ln in lines if ln.startswith("[")]
    assert keywords == [
        "[Version]",
        "[Number of Ports]",
        "[Number of Frequencies]",
        "[Reference]",
        "[Mixed-Mode Order]",
        "[Network Data]",
        "[End]",
    ]
    assert lines[1].startswith("# Hz S RI R ")
    body = lines[lines.index("[Network Data]") + 1 : -1]
    assert len(body) == 3 * 4  # one line per matrix row, not one per frequency
    for fi in range(3):
        first = body[fi * 4].split()
        assert len(first) == 1 + 2 * 4  # the frequency then row 1
        assert float(first[0]) == pytest.approx(f[fi])
        for i in range(1, 4):
            assert len(body[fi * 4 + i].split()) == 2 * 4  # rows 2..P carry no frequency


def test_v2_four_port_still_reads_back_through_skrf(tmp_path) -> None:
    f, s = _sample(ports=4)
    path = to_touchstone_nport(f, s, tmp_path / "chan", z_ref=50.0, version=2)
    net = skrf.Network(str(path))
    np.testing.assert_allclose(net.s, s, atol=1e-9)
    np.testing.assert_allclose(net.f, f)
