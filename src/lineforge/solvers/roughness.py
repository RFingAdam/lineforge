"""Conductor surface-roughness loss factors.

References:
    Hammerstad and Bekkadal, "Microstrip Handbook", ELAB report STF44 A74169, 1975.
    Groisse, Bardi, Biro, Preis, Richter, "Parameters of lossy cavity resonators calculated by the
    finite element method", IEEE Trans. Magnetics 32(3), 1996.
    Huray, "The Foundations of Signal Integrity", Wiley 2009, ch. 6 (snowball model).
    Simonovich, "Practical method for modeling conductor surface roughness using close packing of
    equal spheres", DesignCon 2015 (cannonball parameterisation from Rz).
"""

from __future__ import annotations

import math

from lineforge.materials.database import RoughnessSpec

_CANNONBALL_HEIGHT = 2.0 * (1.0 + math.sqrt(2.0))
_CANNONBALL_RATIO = 14.0 * 4.0 * math.pi / 36.0


def hammerstad_factor(delta_m: float, rms_m: float) -> float:
    return 1.0 + (2.0 / math.pi) * math.atan(1.4 * (rms_m / delta_m) ** 2)


def groisse_factor(delta_m: float, rms_m: float) -> float:
    return 1.0 + math.exp(-((delta_m / (2.0 * rms_m)) ** 1.6))


def huray_factor(delta_m: float, radius_m: float, ratio: float) -> float:
    x = delta_m / radius_m
    return 1.0 + 1.5 * ratio / (1.0 + x + 0.5 * x * x)


def cannonball_from_rz(rz_m: float) -> tuple[float, float]:
    return rz_m / _CANNONBALL_HEIGHT, _CANNONBALL_RATIO


def roughness_factor(spec: RoughnessSpec, delta_m: float) -> float:
    if spec.model == "hammerstad":
        assert spec.rms_um is not None
        return hammerstad_factor(delta_m, spec.rms_um * 1e-6)
    if spec.model == "groisse":
        assert spec.rms_um is not None
        return groisse_factor(delta_m, spec.rms_um * 1e-6)
    assert spec.radius_um is not None and spec.ratio is not None
    return huray_factor(delta_m, spec.radius_um * 1e-6, spec.ratio)


__all__ = [
    "cannonball_from_rz",
    "groisse_factor",
    "hammerstad_factor",
    "huray_factor",
    "roughness_factor",
]
