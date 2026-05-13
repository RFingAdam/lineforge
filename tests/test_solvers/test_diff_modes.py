"""Tests for the direct odd/even-mode bitmap solver (`solvers.diff_modes`).

The module runs two Laplace solves for a usermap that contains red (+1) and
blue (-1) conductors representing a differential pair:

    odd  : V(+1) = +1, V(-1) = -1
    even : V(+1) = +1, V(-1) = +1

and returns Z_odd / Z_even / Z_diff (= 2·Z_odd) / Z_common (= Z_even/2).

`solve_modes` always extends the usermap to atlc2's 3200×3200 simulation grid
which is prohibitively slow for unit tests. We monkeypatch
`extension.extend` to a near-identity (small pad) so the Laplace solves
finish in seconds while still exercising every line of diff_modes.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.solvers import diff_modes


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `extension.extend` with a small-pad identity so tests run in
    seconds. The behavioral semantics (replicated edges + V=0 boundary) are
    preserved at smaller scale."""

    def _small_extend(usermap: Usermap, **_kwargs: object) -> Usermap:
        # 4 px of edge replication is enough to keep the Dirichlet boundary
        # off the conductors without blowing the grid up to 3200×3200.
        return usermap.replicate_edges(4)

    monkeypatch.setattr(diff_modes.extension, "extend", _small_extend)


def _make_symmetric_diff_pair(
    *,
    n: int = 31,
    red_box: tuple[int, int, int, int] = (13, 18, 6, 11),
    blue_box: tuple[int, int, int, int] = (13, 18, 20, 25),
    ground_top_rows: int = 1,
    ground_bottom_rows: int = 1,
    pixel_width_m: float = 1e-4,
) -> Usermap:
    """Build a 31×31 vacuum cavity with two symmetric red/blue strips and
    a top + bottom green ground plane."""
    rgb = np.full((n, n, 3), 255, dtype=np.uint8)  # white = vacuum
    rgb[:ground_top_rows, :] = (0, 255, 0)
    rgb[n - ground_bottom_rows :, :] = (0, 255, 0)
    y0, y1, x0, x1 = red_box
    rgb[y0:y1, x0:x1] = (255, 0, 0)
    y0, y1, x0, x1 = blue_box
    rgb[y0:y1, x0:x1] = (0, 0, 255)
    return Usermap(
        rgb,
        UsermapMetadata(pixel_width_m=pixel_width_m, name="symdiff", source="test"),
    )


def _make_asymmetric_diff_pair(*, n: int = 31) -> Usermap:
    """Asymmetric: blue closer to bottom ground than red."""
    return _make_symmetric_diff_pair(
        n=n,
        red_box=(10, 15, 6, 11),
        blue_box=(16, 21, 20, 25),
    )


class TestSolveModesValidation:
    """`solve_modes` requires both +1 and -1 conductor pixels."""

    def test_missing_minus_one_raises(self) -> None:
        rgb = np.full((11, 11, 3), 255, dtype=np.uint8)
        rgb[0, :] = (0, 255, 0)
        rgb[-1, :] = (0, 255, 0)
        rgb[5, 5] = (255, 0, 0)  # only red
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="t", source="test"))
        with pytest.raises(ValueError, match="requires both"):
            diff_modes.solve_modes(um)

    def test_missing_plus_one_raises(self) -> None:
        rgb = np.full((11, 11, 3), 255, dtype=np.uint8)
        rgb[0, :] = (0, 255, 0)
        rgb[-1, :] = (0, 255, 0)
        rgb[5, 5] = (0, 0, 255)  # only blue
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4, name="t", source="test"))
        with pytest.raises(ValueError, match="requires both"):
            diff_modes.solve_modes(um)


class TestSolveModesSymmetric:
    """Symmetric geometry: spot-check sanity bounds + algebraic identities."""

    @pytest.fixture
    def result(self) -> diff_modes.DiffModeResult:
        um = _make_symmetric_diff_pair()
        return diff_modes.solve_modes(um)

    def test_returns_DiffModeResult(self, result: diff_modes.DiffModeResult) -> None:
        assert isinstance(result, diff_modes.DiffModeResult)
        assert result.method == "bitmap-direct-mode"

    def test_all_impedances_positive(self, result: diff_modes.DiffModeResult) -> None:
        assert result.z_odd > 0
        assert result.z_even > 0
        assert result.z_diff > 0
        assert result.z_common > 0

    def test_z_diff_equals_two_z_odd(self, result: diff_modes.DiffModeResult) -> None:
        """Documented identity: Z_diff = 2 · Z_odd."""
        assert result.z_diff == pytest.approx(2.0 * result.z_odd, rel=1e-9)

    def test_z_common_equals_half_z_even(self, result: diff_modes.DiffModeResult) -> None:
        """Documented identity: Z_common = Z_even / 2."""
        assert result.z_common == pytest.approx(result.z_even / 2.0, rel=1e-9)

    def test_eps_eff_vacuum(self, result: diff_modes.DiffModeResult) -> None:
        """Vacuum cavity ⇒ ε_eff ≈ 1 for both modes."""
        assert result.eps_eff_odd == pytest.approx(1.0, abs=1e-6)
        assert result.eps_eff_even == pytest.approx(1.0, abs=1e-6)

    def test_eps_eff_finite(self, result: diff_modes.DiffModeResult) -> None:
        """ε_eff stays finite for both modes (no NaN / Inf from solver)."""
        assert np.isfinite(result.eps_eff_odd)
        assert np.isfinite(result.eps_eff_even)


class TestSolveModesAsymmetric:
    """Asymmetric placement still satisfies the published identities."""

    def test_asymmetric_geometry_solves(self) -> None:
        um = _make_asymmetric_diff_pair()
        r = diff_modes.solve_modes(um)
        assert r.z_odd > 0
        assert r.z_even > 0
        assert r.z_diff == pytest.approx(2.0 * r.z_odd, rel=1e-9)
        assert r.z_common == pytest.approx(r.z_even / 2.0, rel=1e-9)


class TestSolveModesNoGround:
    """Differential pair with no explicit +0 conductor — the replicated-edge
    boundary acts as the implicit V=0 reference."""

    def test_no_ground_runs_without_error(self) -> None:
        n = 31
        rgb = np.full((n, n, 3), 255, dtype=np.uint8)  # all vacuum
        rgb[13:18, 6:11] = (255, 0, 0)
        rgb[13:18, 20:25] = (0, 0, 255)
        um = Usermap(
            rgb,
            UsermapMetadata(pixel_width_m=1e-4, name="noground", source="test"),
        )
        r = diff_modes.solve_modes(um)
        assert r.z_odd > 0
        assert r.z_even > 0


class TestSolveModesDielectric:
    """Add a dielectric (FR4-like) between the strips and check ε_eff > 1."""

    def test_eps_eff_increases_with_dielectric(self) -> None:
        n = 31
        rgb = np.full((n, n, 3), 255, dtype=np.uint8)
        rgb[:1, :] = (0, 255, 0)
        rgb[-1:, :] = (0, 255, 0)
        # Fill mid-rows with FR4 dielectric color
        rgb[9:22, :] = (223, 247, 136)
        # Red / blue strips inside the dielectric region
        rgb[13:18, 6:11] = (255, 0, 0)
        rgb[13:18, 20:25] = (0, 0, 255)
        um = Usermap(
            rgb,
            UsermapMetadata(pixel_width_m=1e-4, name="fr4diff", source="test"),
        )
        r = diff_modes.solve_modes(um)
        # FR4 εr ≈ 4.4 → ε_eff somewhere between 1 and 4.4 for the partial fill
        assert 1.0 < r.eps_eff_odd <= 4.5
        assert 1.0 < r.eps_eff_even <= 4.5
        assert r.z_odd > 0
        assert r.z_even > 0


class TestDiffModeResultModel:
    """Pydantic model basics."""

    def test_model_validates_positive_z(self) -> None:
        r = diff_modes.DiffModeResult(
            z_odd=45.0,
            z_even=55.0,
            z_diff=90.0,
            z_common=27.5,
            eps_eff_odd=2.5,
            eps_eff_even=2.5,
        )
        assert r.method == "bitmap-direct-mode"

    def test_model_rejects_nonpositive_z(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            diff_modes.DiffModeResult(
                z_odd=-1.0,
                z_even=55.0,
                z_diff=90.0,
                z_common=27.5,
                eps_eff_odd=2.5,
                eps_eff_even=2.5,
            )
