"""Usermap: the bitmap representation of a transmission line cross-section.

A usermap is a 2D grid of pixels, each tagged with a material from the
:mod:`lineforge.materials` database. The numerical solvers consume usermaps and
produce V/E/J fields back on the same grid.

I/O:
    - :meth:`Usermap.from_bmp` / :meth:`from_png` / :meth:`from_tiff`: atlc/atlc2
      compatible bitmap inputs (no de-aliasing, exact RGB lookup).
    - :meth:`Usermap.from_json` / :meth:`to_json`: lineforge-native format that
      stores the material codes directly (no RGB round-trip needed).
    - :meth:`Usermap.to_bmp`: write atlc2-readable BMP.

Edge replication:
    atlc2 replicates the edge pixels outward when extending the simulation to
    its 3200×3200 grid; the four corner pixels are replicated diagonally. This
    is exposed via :meth:`replicate_edges` for use by the solver's open-boundary
    extension (Phase 2.9).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from lineforge.materials import ATLC2_DEFAULTS, MaterialRecord, build_lookup
from lineforge.units import parse_length


class UsermapMetadata(BaseModel):
    """Sidecar metadata for a usermap (saved alongside in JSON I/O)."""

    model_config = ConfigDict(extra="forbid")

    pixel_width_m: float = Field(..., gt=0, description="Pixel side length [m].")
    name: str = Field("untitled", description="Human-readable name.")
    source: str | None = Field(None, description="Original source file or rasterizer.")
    notes: str = Field("", description="Free-form notes.")


class Usermap:
    """A bitmap cross-section with material assignments.

    Stored as:
        - ``rgb`` : ``(H, W, 3)`` uint8 array (the literal pixel colors).
        - ``materials`` : list of :class:`MaterialRecord` indexed by ``codes``.
        - ``codes`` : ``(H, W)`` int16 array of material indices into ``materials``.
                      ``-1`` marks pixels with no recognized material (treated as
                      ``vacuum`` by the solvers, with a warning).
        - ``conductor_ids`` : ``(H, W)`` int32 array of conductor identity.
                      ``-1`` non-conductor, ``0`` reference, ``1..N`` signal
                      conductors, ``-2`` floating. For RGB-built maps this is
                      derived from each material's ``use`` role; label-built
                      maps (:meth:`from_labels`) may supply it directly.
        - ``meta`` : :class:`UsermapMetadata` (pixel width, name, etc.).

    The class is mutable for the rasterizers (Phase 2.5), but the solvers should
    treat it as effectively read-only.
    """

    def __init__(
        self,
        rgb: np.ndarray,
        meta: UsermapMetadata,
        material_lookup: dict[tuple[int, int, int], MaterialRecord] | None = None,
        unknown_warning: bool = True,
        *,
        _codes: np.ndarray | None = None,
        _materials: list[MaterialRecord] | None = None,
        _conductor_ids: np.ndarray | None = None,
    ) -> None:
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError(f"rgb array must have shape (H, W, 3), got {rgb.shape}")
        if rgb.dtype != np.uint8:
            rgb = rgb.astype(np.uint8)
        self.rgb: np.ndarray = rgb
        self.meta: UsermapMetadata = meta
        self.material_lookup = material_lookup or build_lookup()

        if _codes is not None and _materials is not None:
            self.materials = list(_materials)
            self.codes = _codes.astype(np.int16)
        else:
            self.materials, self.codes = self._codes_from_rgb(rgb, unknown_warning)
        if _conductor_ids is not None:
            self.conductor_ids: np.ndarray = _conductor_ids.astype(np.int32)
        else:
            self.conductor_ids = self._conductor_ids_from_roles()

    def _codes_from_rgb(
        self, rgb: np.ndarray, unknown_warning: bool
    ) -> tuple[list[MaterialRecord], np.ndarray]:
        packed = (
            (rgb[:, :, 0].astype(np.int32) << 16)
            | (rgb[:, :, 1].astype(np.int32) << 8)
            | rgb[:, :, 2].astype(np.int32)
        )
        uniq, inverse = np.unique(packed, return_inverse=True)
        materials: list[MaterialRecord] = []
        code_of_unique = np.full(len(uniq), -1, dtype=np.int16)
        unknown: list[tuple[int, int, int]] = []
        for i, value in enumerate(uniq.tolist()):
            key = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
            mat = self.material_lookup.get(key)
            if mat is None:
                unknown.append(key)
                continue
            code_of_unique[i] = len(materials)
            materials.append(mat)
        codes = code_of_unique[inverse.reshape(rgb.shape[:2])]
        if unknown and unknown_warning:
            import warnings

            warnings.warn(
                f"{len(unknown)} pixel color(s) not in the material database; "
                f"treating as vacuum: {sorted(unknown)[:5]}{'...' if len(unknown) > 5 else ''}",
                stacklevel=3,
            )
        return materials, codes

    def _conductor_ids_from_roles(self) -> np.ndarray:
        ids = np.full(self.codes.shape, -1, dtype=np.int32)
        for idx, mat in enumerate(self.materials):
            sel = self.codes == idx
            if mat.use == "+1":
                ids[sel] = 1
            elif mat.use == "-1":
                ids[sel] = 2
            elif mat.use == "0":
                ids[sel] = 0
            elif mat.use == "float":
                ids[sel] = -2
        return ids

    @classmethod
    def from_labels(
        cls,
        material_ids: np.ndarray,
        materials: list[MaterialRecord],
        *,
        pixel_width_m: float,
        conductor_ids: np.ndarray | None = None,
        name: str = "labels",
    ) -> Usermap:
        """Build a usermap from integer label maps; ``-1`` in ``material_ids`` is vacuum."""
        material_ids = np.asarray(material_ids)
        if material_ids.ndim != 2:
            raise ValueError("material_ids must be 2-D")
        if material_ids.max(initial=-1) >= len(materials):
            raise ValueError("material_ids references a material outside the list")
        if material_ids.min(initial=-1) < -1:
            raise ValueError("material_ids values must be -1 (vacuum) or a material index")
        cid = np.asarray(conductor_ids) if conductor_ids is not None else None
        if cid is not None and cid.shape != material_ids.shape:
            raise ValueError("conductor_ids must match material_ids in shape")
        h, w = material_ids.shape
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        for idx, mat in enumerate(materials):
            rgb[material_ids == idx] = mat.rgb
        meta = UsermapMetadata(pixel_width_m=pixel_width_m, name=name, source="labels")
        u = cls(
            rgb,
            meta,
            unknown_warning=False,
            _codes=material_ids.astype(np.int16),
            _materials=materials,
            _conductor_ids=conductor_ids,
        )
        if cid is not None:
            conductor_material = np.zeros(material_ids.shape, dtype=bool)
            for idx, mat in enumerate(materials):
                if mat.is_conductor:
                    conductor_material |= material_ids == idx
            marked = (cid >= 0) | (cid == -2)
            if marked.any() and not conductor_material[marked].all():
                raise ValueError("conductor_ids marks a pixel whose material is not a conductor")
        return u

    @property
    def n_signal_conductors(self) -> int:
        return int(self.conductor_ids.max(initial=0))

    # ------------------------------------------------------------------
    @property
    def shape(self) -> tuple[int, int]:
        """``(height, width)`` in pixels."""
        h, w, _ = self.rgb.shape
        return (h, w)

    @property
    def pixel_width_m(self) -> float:
        return self.meta.pixel_width_m

    def material_at(self, y: int, x: int) -> MaterialRecord | None:
        """Material at pixel ``(y, x)``. Returns None for unrecognized pixels."""
        idx = int(self.codes[y, x])
        return self.materials[idx] if idx >= 0 else None

    # ------------------------------------------------------------------
    # Solver-friendly views
    # ------------------------------------------------------------------

    def conductor_mask(self, use: str | int | None = None) -> np.ndarray:
        """Boolean mask of conductor pixels.

        Parameters
        ----------
        use
            Optional filter. ``"+1"``, ``"-1"``, ``"0"``, ``"float"`` to select
            one role by the material's atlc2 use code; an ``int`` to select one
            entry of :attr:`conductor_ids` directly (``0`` reference, ``1..N``
            signal conductors, ``-2`` floating); ``None`` (default) for all
            conductor pixels.
        """
        if isinstance(use, int) and not isinstance(use, bool):
            id_mask: np.ndarray = self.conductor_ids == use
            return id_mask
        mask = np.zeros(self.shape, dtype=bool)
        for idx, mat in enumerate(self.materials):
            if mat.is_conductor and (use is None or mat.use == use):
                mask |= self.codes == idx
        if use is None:
            mask |= self.conductor_ids >= 0
            mask |= self.conductor_ids == -2
        return mask

    def insulator_mask(self) -> np.ndarray:
        out = np.zeros(self.shape, dtype=bool)
        for idx, mat in enumerate(self.materials):
            if mat.is_insulator:
                out |= self.codes == idx
        return out

    def er_field(self) -> np.ndarray:
        """Per-pixel relative permittivity. Defaults to vacuum (1.0) for unknown pixels."""
        out = np.ones(self.shape, dtype=np.float64)
        for idx, mat in enumerate(self.materials):
            out[self.codes == idx] = mat.er
        return out

    def tan_delta_field(self) -> np.ndarray:
        out = np.zeros(self.shape, dtype=np.float64)
        for idx, mat in enumerate(self.materials):
            out[self.codes == idx] = mat.tan_delta
        return out

    def voltage_bc_field(self) -> tuple[np.ndarray, np.ndarray]:
        """Returns (mask, value) arrays for Dirichlet voltage BCs.

        Where ``mask[y, x]`` is True, the pixel has a fixed voltage ``value[y, x]``.
        Float and insulator pixels have ``mask=False``.
        """
        mask = np.zeros(self.shape, dtype=bool)
        value = np.zeros(self.shape, dtype=np.float64)
        for idx, mat in enumerate(self.materials):
            v = mat.voltage_bc
            if v is None:
                continue
            sel = self.codes == idx
            mask |= sel
            value[sel] = v
        return mask, value

    def resistivity_field_ohm_m(self) -> np.ndarray:
        """Per-pixel resistivity in Ω·m.

        atlc2's database stores resistivity in **µΩ·cm** despite the column
        being labeled "Ohms:": for copper the value is 1.7241, which is
        1.7241 µΩ·cm = 1.7241e-8 Ω·m (CRC handbook). Conversion factor: 1e-8.
        """
        out = np.full(self.shape, 1e8, dtype=np.float64)  # large for insulators
        for idx, mat in enumerate(self.materials):
            out[self.codes == idx] = mat.resistivity_ohm_cm * 1e-8
        return out

    # ------------------------------------------------------------------
    # Edge replication (atlc2 §"pixels at the edge of the Usermap are special")
    # ------------------------------------------------------------------

    def replicate_edges(self, pad: int) -> Usermap:
        """Pad the usermap by ``pad`` pixels in each direction by replicating edges.

        The four corner pixels are replicated diagonally, matching atlc2's docs.
        """
        h, w, _ = self.rgb.shape
        new_rgb = np.empty((h + 2 * pad, w + 2 * pad, 3), dtype=np.uint8)
        # Center
        new_rgb[pad : pad + h, pad : pad + w] = self.rgb
        # Sides (replicate)
        new_rgb[:pad, pad : pad + w] = self.rgb[0:1, :, :]  # top
        new_rgb[pad + h :, pad : pad + w] = self.rgb[-1:, :, :]  # bottom
        new_rgb[pad : pad + h, :pad] = self.rgb[:, 0:1, :]  # left
        new_rgb[pad : pad + h, pad + w :] = self.rgb[:, -1:, :]  # right
        # Corners
        new_rgb[:pad, :pad] = self.rgb[0, 0]
        new_rgb[:pad, pad + w :] = self.rgb[0, -1]
        new_rgb[pad + h :, :pad] = self.rgb[-1, 0]
        new_rgb[pad + h :, pad + w :] = self.rgb[-1, -1]

        new_codes = np.pad(self.codes, pad, mode="edge")
        new_conductor_ids = np.pad(self.conductor_ids, pad, mode="edge")

        return Usermap(
            new_rgb,
            UsermapMetadata(
                pixel_width_m=self.meta.pixel_width_m,
                name=self.meta.name + " (edge-replicated)",
                source=self.meta.source,
                notes=self.meta.notes,
            ),
            material_lookup=self.material_lookup,
            unknown_warning=False,
            _codes=new_codes,
            _materials=self.materials,
            _conductor_ids=new_conductor_ids,
        )

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @classmethod
    def from_bmp(
        cls,
        path: str | Path,
        *,
        pixel_width: str | float,
        material_lookup: dict[tuple[int, int, int], MaterialRecord] | None = None,
    ) -> Usermap:
        return cls._from_image(path, "bmp", pixel_width, material_lookup)

    @classmethod
    def from_png(
        cls,
        path: str | Path,
        *,
        pixel_width: str | float,
        material_lookup: dict[tuple[int, int, int], MaterialRecord] | None = None,
    ) -> Usermap:
        return cls._from_image(path, "png", pixel_width, material_lookup)

    @classmethod
    def from_tiff(
        cls,
        path: str | Path,
        *,
        pixel_width: str | float,
        material_lookup: dict[tuple[int, int, int], MaterialRecord] | None = None,
    ) -> Usermap:
        return cls._from_image(path, "tiff", pixel_width, material_lookup)

    @classmethod
    def _from_image(
        cls,
        path: str | Path,
        fmt: str,
        pixel_width: str | float,
        material_lookup: dict[tuple[int, int, int], MaterialRecord] | None,
    ) -> Usermap:
        path = Path(path)
        with Image.open(path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            rgb = np.asarray(img, dtype=np.uint8)

        meta = UsermapMetadata(
            pixel_width_m=parse_length(pixel_width),
            name=path.stem,
            source=str(path),
        )
        return cls(rgb, meta, material_lookup=material_lookup)

    def to_bmp(self, path: str | Path) -> None:
        Image.fromarray(self.rgb, mode="RGB").save(path, format="BMP")

    def to_png(self, path: str | Path) -> None:
        Image.fromarray(self.rgb, mode="RGB").save(path, format="PNG")

    def to_tiff(self, path: str | Path) -> None:
        Image.fromarray(self.rgb, mode="RGB").save(path, format="TIFF")

    @classmethod
    def from_json(cls, path: str | Path) -> Usermap:
        """Load a usermap from the lineforge-native JSON format."""
        blob: dict[str, Any] = json.loads(Path(path).read_text())
        rgb = np.array(blob["rgb"], dtype=np.uint8)
        meta = UsermapMetadata.model_validate(blob["meta"])
        return cls(rgb, meta)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "format": "lineforge.usermap",
                    "version": "1.0.0",
                    "meta": self.meta.model_dump(),
                    "shape": list(self.shape),
                    "rgb": self.rgb.tolist(),
                },
            )
        )


def _build_default_lookup() -> dict[tuple[int, int, int], MaterialRecord]:
    return {m.rgb: m for m in ATLC2_DEFAULTS}


__all__ = ["Usermap", "UsermapMetadata"]
