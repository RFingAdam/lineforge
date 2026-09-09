"""Optimizer results must use the same solver as the search objective."""

from typing import Any

import pytest

from lineforge.optimize import optimize_for


def test_full_solver_result_preserves_loss_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    from lineforge.geometry import builders
    from lineforge.solvers import cgp, lrs

    monkeypatch.setattr(builders, "rasterize", lambda geom: geom)

    def full(geom: Any, *, frequency_hz: float) -> dict[str, float]:
        assert frequency_hz == 1e9
        return {"rs": geom.W * 1e6}

    def unexpected_cgp(*args: Any, **kwargs: Any) -> None:
        pytest.fail("full optimization must not return a CGP-only result")

    monkeypatch.setattr(lrs, "solve_full", full)
    monkeypatch.setattr(cgp, "solve_cgp", unexpected_cgp)
    result = optimize_for(
        template={"type": "microstrip", "H": "4mil", "T": "1mil", "er": 4.4},
        vary={"W": ("1mil", "10mil")},
        target={"rs": 100.0},
        solver="full",
        frequency_hz=1e9,
    )
    assert result.success
    assert result.metric["rs"] == pytest.approx(100.0, rel=0.01)
