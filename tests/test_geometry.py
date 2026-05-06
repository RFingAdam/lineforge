"""Phase 1.4 AC: geometry types validate, round-trip JSON, and export schema."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from atlc3.geometry import GEOMETRY_TYPES, export_jsonschema, from_dict
from atlc3.geometry.types import CPWG, Microstrip


class TestGeometryTypes:
    def test_all_seven_types_registered(self) -> None:
        # Phase 1 ships 8 (microstrip + embedded + 2 striplines + cpwg + 3 diffs)
        assert len(GEOMETRY_TYPES) == 8

    def test_microstrip_round_trip_json(self) -> None:
        m = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
        s = m.model_dump_json()
        restored = Microstrip.model_validate_json(s)
        assert restored == m

    def test_round_trip_via_dict(self) -> None:
        m = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
        d = json.loads(m.model_dump_json())
        restored = from_dict(d)
        assert restored == m

    def test_unit_strings_normalize_to_meters(self) -> None:
        m = Microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
        assert m.W == pytest.approx(6 * 25.4e-6)

    def test_negative_dimension_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Microstrip(W=-1e-6, H=1e-6, T=1e-6, er=4.4)

    def test_er_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Microstrip(W=1e-6, H=1e-6, T=1e-6, er=0.5)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Microstrip(W=1e-6, H=1e-6, T=1e-6, er=4.4, foo=1)  # type: ignore[call-arg]


class TestFromDict:
    def test_dispatch_by_type(self) -> None:
        d = {"type": "microstrip", "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4}
        result = from_dict(d)
        assert isinstance(result, Microstrip)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown geometry type"):
            from_dict({"type": "purple-twirl"})

    def test_missing_type_raises(self) -> None:
        with pytest.raises(KeyError):
            from_dict({"W": 1e-3})


class TestSchemaExport:
    def test_schema_has_oneof(self) -> None:
        schema = export_jsonschema()
        assert "oneOf" in schema
        assert len(schema["oneOf"]) == len(GEOMETRY_TYPES)

    def test_schema_has_discriminator(self) -> None:
        schema = export_jsonschema()
        assert schema["discriminator"]["propertyName"] == "type"

    def test_per_type_schema_includes_required_fields(self) -> None:
        schema = CPWG.model_json_schema()
        required = set(schema.get("required", []))
        for must_have in {"W", "S", "H", "T", "er"}:
            assert must_have in required
