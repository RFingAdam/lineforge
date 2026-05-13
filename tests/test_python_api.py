"""Phase 1.7 AC: top-level convenience functions in the lineforge package."""

from __future__ import annotations

import pytest

import lineforge
from lineforge.results import DiffResult, TLineResult


class TestTopLevel:
    def test_microstrip_one_liner(self) -> None:
        r = lineforge.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        assert isinstance(r, TLineResult)
        assert 40 < r.z0 < 70

    def test_stripline_one_liner(self) -> None:
        r = lineforge.stripline(W="5mil", T="1.4mil", B="14mil", er=4.4)
        assert isinstance(r, TLineResult)
        assert 30 < r.z0 < 70

    def test_cpwg_one_liner(self) -> None:
        r = lineforge.cpwg(W="5mil", S="8mil", H="4mil", T="1.4mil", er=4.4)
        assert isinstance(r, TLineResult)

    def test_edge_coupled_diff_microstrip(self) -> None:
        r = lineforge.edge_coupled_diff(
            W="4mil",
            S="6mil",
            H="4mil",
            T="1.4mil",
            er=4.4,
            on="microstrip",
        )
        assert isinstance(r, DiffResult)

    def test_edge_coupled_diff_stripline(self) -> None:
        r = lineforge.edge_coupled_diff(
            W="4mil",
            S="6mil",
            H="14mil",
            T="1.4mil",
            er=4.4,
            on="stripline",
        )
        assert isinstance(r, DiffResult)

    def test_edge_coupled_diff_invalid_on(self) -> None:
        with pytest.raises(ValueError):
            lineforge.edge_coupled_diff(
                W="4mil",
                S="6mil",
                H="4mil",
                T="1.4mil",
                er=4.4,
                on="laser",
            )

    def test_solve_with_dict(self) -> None:
        r = lineforge.solve(
            {"type": "microstrip", "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4}
        )
        assert isinstance(r, TLineResult)

    def test_solve_with_geometry_model(self) -> None:
        geom = lineforge.Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        r = lineforge.solve(geom)
        assert isinstance(r, TLineResult)

    def test_frequency_string_parsed(self) -> None:
        r = lineforge.microstrip(
            W="6mil",
            H="4mil",
            T="1.4mil",
            er=4.4,
            tan_delta=0.02,
            frequency="1GHz",
        )
        assert r.frequency_hz == pytest.approx(1e9)
        assert r.dielectric_loss_db_per_in is not None

    def test_version_attribute(self) -> None:
        assert isinstance(lineforge.__version__, str)
        assert len(lineforge.__version__) > 0
