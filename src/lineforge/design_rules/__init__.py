"""Design-rules layer: decision frameworks for PCB RF design.

These are not analytical solvers but structured decision logic that
encodes engineering practice: when to follow a reference design vs when
to optimize, how to budget RF performance contributions across path
elements, and so on. Each rule returns guidance plus the reasoning so
agents and engineers can document their decisions.
"""

from __future__ import annotations

from lineforge.design_rules.pad_classification import (
    PadCategory,
    PadClassification,
    classify_pad,
)

__all__ = ["PadCategory", "PadClassification", "classify_pad"]
