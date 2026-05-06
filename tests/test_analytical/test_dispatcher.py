"""Phase 1.5 AC: dispatcher routes any geometry to its analytical solver."""

from __future__ import annotations

import pytest

from atlc3.analytical import solve
from atlc3.geometry.types import (
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
)
from atlc3.results import DiffResult, TLineResult


class TestDispatcher:
    @pytest.mark.parametrize(
        "geometry",
        [
            Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4),
            EmbeddedMicrostrip(
                W="6mil", H="4mil", H2="4mil", T="1.4mil", er=4.4, er2=3.5,
            ),
            StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4),
            StriplineAsymmetric(W="5mil", T="1.4mil", H1="4mil", H2="8mil", er=4.4),
            CPWG(W="5mil", S="8mil", H="4mil", T="1.4mil", er=4.4),
        ],
    )
    def test_single_line_returns_tline(self, geometry: object) -> None:
        result = solve(geometry)  # type: ignore[arg-type]
        assert isinstance(result, TLineResult)
        assert result.z0 > 0

    @pytest.mark.parametrize(
        "geometry",
        [
            EdgeCoupledDiffMicrostrip(W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4),
            EdgeCoupledDiffStripline(W="4mil", S="6mil", B="14mil", T="1.4mil", er=4.4),
            BroadsideCoupledDiffStripline(
                W="5mil", H1="4mil", H_between="4mil", T="0.7mil", er=4.4,
            ),
        ],
    )
    def test_diff_returns_diff_result(self, geometry: object) -> None:
        result = solve(geometry)  # type: ignore[arg-type]
        assert isinstance(result, DiffResult)
        assert result.z_diff > 0

    def test_unknown_geometry_raises(self) -> None:
        class _NotAGeometry:
            pass

        with pytest.raises(TypeError):
            solve(_NotAGeometry())  # type: ignore[arg-type]

    def test_frequency_propagated(self) -> None:
        geom = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4, tan_delta=0.02)
        result = solve(geom, frequency_hz=1e9)
        assert isinstance(result, TLineResult)
        assert result.frequency_hz == 1e9
        assert result.dielectric_loss_db_per_in is not None
