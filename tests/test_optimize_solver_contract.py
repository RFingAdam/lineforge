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


@pytest.mark.parametrize(
    ("vary", "target", "max_iter", "message"),
    [
        ({}, {"z0": 50.0}, 100, "vary must contain"),
        ({"W": ("1mil", "10mil")}, {}, 100, "target must contain"),
        ({"W": ("10mil", "1mil")}, {"z0": 50.0}, 100, "bound must be finite"),
        ({"W": ("1mil", "10mil")}, {"z0": float("nan")}, 100, "target values"),
        ({"W": ("1mil", "10mil")}, {"z0": 50.0}, 0, "max_iter"),
    ],
)
def test_optimizer_rejects_invalid_contract_inputs(
    vary: dict[str, tuple[float | str, float | str]],
    target: dict[str, float],
    max_iter: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        optimize_for(
            template={"type": "microstrip", "H": "4mil", "T": "1mil", "er": 4.4},
            vary=vary,
            target=target,
            max_iter=max_iter,
        )
