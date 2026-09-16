"""The solvers package re-exports the N-conductor entry points its submodules define."""

from __future__ import annotations

import lineforge.solvers as solvers

EXPECTED = (
    "SolverBudgetExceeded",
    "WheelerResult",
    "cannonball_from_rz",
    "groisse_factor",
    "hammerstad_factor",
    "huray_factor",
    "roughness_factor",
    "solve_impedance_matrix",
    "solve_wheeler_resistance",
)


def test_each_name_imports_from_the_package() -> None:
    for name in EXPECTED:
        assert name in solvers.__all__, f"{name} missing from lineforge.solvers.__all__"
        assert getattr(solvers, name, None) is not None, f"{name} not importable"


def test_the_names_are_the_submodules_objects() -> None:
    from lineforge.solvers import faraday, roughness, wheeler

    assert solvers.solve_wheeler_resistance is wheeler.solve_wheeler_resistance
    assert solvers.WheelerResult is wheeler.WheelerResult
    assert solvers.solve_impedance_matrix is faraday.solve_impedance_matrix
    assert solvers.SolverBudgetExceeded is faraday.SolverBudgetExceeded
    assert solvers.roughness_factor is roughness.roughness_factor
    assert solvers.cannonball_from_rz is roughness.cannonball_from_rz
