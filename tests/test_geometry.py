"""Phase 1.4 AC: geometry types validate, round-trip JSON, and export schema."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from atlc3.geometry import GEOMETRY_TYPES, export_jsonschema, from_dict
from atlc3.geometry.types import CPWG, Microstrip


class TestGeometryTypes:
    def test_all_geometry_types_registered(self) -> None:
        # 8 from Phase 1 + 1 ThreeWireGeometry from Phase B1
        assert len(GEOMETRY_TYPES) == 9

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


class TestRasterizeStriplineAsymmetricSplitEr:
    """Bitmap rasterizer must paint two distinct dielectrics for split εr."""

    def test_no_custom_lookup_when_bulk_only(self) -> None:
        from atlc3.geometry.builders import rasterize_stripline_asymmetric
        from atlc3.geometry.types import StriplineAsymmetric

        geom = StriplineAsymmetric(W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4)
        umap = rasterize_stripline_asymmetric(geom)
        # Bulk-only path leaves material_lookup at the default (built from atlc2 palette).
        # We only assert the umap is valid and queryable.
        assert umap.rgb.shape[2] == 3

    def test_custom_lookup_carries_exact_er(self) -> None:
        """When er_above != er_below, the synthesized records must carry the
        EXACT εr the user asked for (not the closest atlc2-default match)."""
        from atlc3.geometry.builders import rasterize_stripline_asymmetric
        from atlc3.geometry.types import StriplineAsymmetric

        geom = StriplineAsymmetric(
            W="5mil",
            T="1.4mil",
            H1="3mil",
            H2="9mil",
            er=4.0,
            er_above=4.5,
            er_below=3.7,
            tan_delta_above=0.020,
            tan_delta_below=0.005,
        )
        umap = rasterize_stripline_asymmetric(geom)
        ers = sorted(
            rec.er
            for rec in umap.material_lookup.values()
            if rec.use == "insul" and rec.name and "custom" in rec.name
        )
        assert ers == pytest.approx([3.7, 4.5])
        # tan_delta also carried through exactly
        td_above = next(
            rec.tan_delta
            for rec in umap.material_lookup.values()
            if rec.use == "insul" and rec.name and "above" in rec.name
        )
        td_below = next(
            rec.tan_delta
            for rec in umap.material_lookup.values()
            if rec.use == "insul" and rec.name and "below" in rec.name
        )
        assert td_above == pytest.approx(0.020)
        assert td_below == pytest.approx(0.005)

    def test_split_er_paints_two_distinct_colors(self) -> None:
        """The H1 region (above strip) and H2 region (below) must be painted
        with different RGB values when split-εr is set."""
        from atlc3.geometry.builders import rasterize_stripline_asymmetric
        from atlc3.geometry.types import StriplineAsymmetric

        geom = StriplineAsymmetric(
            W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.0, er_above=4.5, er_below=3.7
        )
        umap = rasterize_stripline_asymmetric(geom)
        # Sample a column well away from the strip (column 1, in the side margin).
        col = umap.rgb[:, 1, :]
        # Find rows with non-ground, non-vacuum content (the dielectric halves).
        # We just need two distinct dielectric colors to appear somewhere in the column.
        unique = {tuple(row) for row in col}
        # Drop ground (green) and vacuum (white) — what remains is dielectric color(s).
        unique.discard((0, 255, 0))
        unique.discard((255, 255, 255))
        assert len(unique) >= 2, (
            f"expected two distinct dielectric colors above/below the strip; "
            f"got {unique}"
        )


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
