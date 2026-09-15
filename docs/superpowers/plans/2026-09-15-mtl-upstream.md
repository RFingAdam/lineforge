# lineforge: N-conductor Maxwell matrices, Wheeler losses, roughness, causal materials, N-port Touchstone

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give lineforge the upstream capabilities fieldforge's interconnect extraction needs: label-based usermaps, N-conductor capacitance and inductance matrices from the existing Laplace solver, skin-effect resistance by Wheeler's incremental inductance rule with Huray, Hammerstad and Groisse roughness, Djordjevic-Sarkar dielectrics on `MaterialRecord`, and N-port Touchstone export.

**Architecture:** Everything builds on `solvers/laplace.py` (unchanged) and the energy-integral pattern of `solvers/cgp.py`. A new `Usermap.from_labels` constructor and a `conductor_ids` array replace the RGB-role quartet for N conductors while keeping the RGB path intact. `solvers/mtl.py` runs N+1 Laplace solves per material configuration and assembles Maxwell matrices; `solvers/wheeler.py` re-solves the vacuum problem with eroded conductors to get `dL/dn`. Materials gain optional `ds_params` and `roughness` fields; the JSON pack loader learns them.

**Tech Stack:** Python 3.11+, numpy, scipy, pyamg, pydantic 2, scikit-rf (already a dev/gui extra; Touchstone export imports it lazily), pytest, ruff, black, mypy strict.

**Spec:** `/home/swamp/projects/github/fieldforge/docs/superpowers/specs/2026-09-15-fieldforge-design.md`, section "Sub-project 3", paragraph "lineforge upstream additions".

## Global Constraints

- Work on branch `feature/mtl-nconductor` from `main` in `/home/swamp/projects/github/lineforge`; venv `.venv` (create with `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"`).
- Style gate before every commit: `.venv/bin/ruff check . && .venv/bin/black --check . && .venv/bin/mypy src/lineforge` (mypy strict, `-> None` on every test, `from __future__ import annotations` in every module).
- Coverage floor in `pyproject.toml` is 75; CONTRIBUTING asks for 90 on new code: every new module ships with tests covering its branches.
- No public API removed; the RGB usermap path and all existing tests keep passing.
- Every new solver ships a golden test (analytic value, existing-solver equivalence, or cross-check) per CONTRIBUTING.
- `CHANGELOG.md` gets `### Added` entries under `## [Unreleased]` naming the files.
- Tests that touch `extension.extend` use the `_fast_extension` monkeypatch idiom from `tests/test_solvers/test_diff_modes.py` so they run in seconds.

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/lineforge/geometry/usermap.py` | `Usermap.from_labels`, `conductor_ids`, vectorised `__init__`, `conductor_mask` by int |
| `src/lineforge/solvers/extension.py`, `replicate_edges` | carry `codes` and `conductor_ids` when padding label-based maps |
| `src/lineforge/materials/database.py`, `morecolors.py` | `DSParams`, `RoughnessSpec`, `MaterialRecord.er_complex`, pack I/O |
| `src/lineforge/solvers/roughness.py` | Hammerstad, Huray, Groisse factors and the cannonball parameterisation |
| `src/lineforge/solvers/mtl.py` | `solve_maxwell`, `MaxwellResult`, `rlgc_matrices` |
| `src/lineforge/solvers/wheeler.py` | `solve_wheeler_resistance` |
| `src/lineforge/solvers/faraday.py` | `solve_impedance_matrix` (N right-hand sides, one LU) |
| `src/lineforge/touchstone.py` | `to_touchstone_nport` |
| `tests/test_usermap_labels.py`, `tests/test_materials_ds.py`, `tests/test_solvers/test_roughness.py`, `tests/test_solvers/test_mtl.py`, `tests/test_solvers/test_wheeler.py`, `tests/test_solvers/test_faraday_matrix.py`, `tests/test_touchstone_nport.py` | tests |

---

### Task 1: Label-based usermaps and a vectorised constructor

**Files:**
- Modify: `src/lineforge/geometry/usermap.py` (lines 61-105 constructor loop; `conductor_mask` at 127-143; `replicate_edges` at 198-228)
- Modify: `src/lineforge/solvers/extension.py` (every place a `Usermap` is rebuilt from `rgb`)
- Test: `tests/test_usermap_labels.py`

**Interfaces:**
- Produces: `Usermap.from_labels(material_ids: np.ndarray, materials: list[MaterialRecord], *, pixel_width_m: float, conductor_ids: np.ndarray | None = None, name: str = "labels") -> Usermap`. `material_ids` is int (H, W) indexing `materials`, `-1` for vacuum. `conductor_ids` is int32 (H, W): `-1` non-conductor, `0` reference, `1..N` signal conductors, `-2` floating. When omitted it is derived from roles: `+1 -> 1`, `-1 -> 2` (only if present), `0 -> 0`, `float -> -2`.
- Produces: attribute `Usermap.conductor_ids` on every usermap (derived from roles for RGB maps); `Usermap.n_signal_conductors -> int`; `conductor_mask(use: str | int | None)` accepting an int id.
- `replicate_edges` and `extension.extend` / `extend_to_shape` preserve `codes`, `materials` and `conductor_ids` (edge-replicated) instead of re-deriving from `rgb`.

- [ ] **Step 1: Write the failing test**

`tests/test_usermap_labels.py`:
```python
"""Label-based usermaps carry integer conductor ids and material codes without an RGB round trip."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials.database import MaterialRecord
from lineforge.solvers import extension

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")
FR4 = MaterialRecord(rgb=(223, 247, 136), use="insul", er=3.7, tan_delta=0.018, name="FR4", resistivity_ohm_cm=1e6)
VAC = MaterialRecord(rgb=(255, 255, 255), use="insul", name="vacuum", resistivity_ohm_cm=1e6)


def three_conductor_map() -> Usermap:
    h, w = 20, 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[10:20, :] = 1  # FR4 below
    mat[19, :] = 0  # ground plane row (copper material index 0)
    cid[19, :] = 0
    mat[8:10, 5:12] = 0
    cid[8:10, 5:12] = 1
    mat[8:10, 20:27] = 0
    cid[8:10, 20:27] = 2
    return Usermap.from_labels(mat, [CU, FR4], pixel_width_m=1e-5, conductor_ids=cid)


def test_from_labels_masks_and_fields() -> None:
    u = three_conductor_map()
    assert u.shape == (20, 40)
    assert u.n_signal_conductors == 2
    assert u.conductor_mask(1).sum() == 14
    assert u.conductor_mask(2).sum() == 14
    assert u.conductor_mask(0).sum() == 40
    assert u.conductor_mask(None).sum() == 68
    assert u.er_field()[15, 3] == pytest.approx(3.7)
    assert u.er_field()[2, 2] == pytest.approx(1.0)
    assert u.tan_delta_field()[15, 3] == pytest.approx(0.018)


def test_rgb_map_derives_conductor_ids() -> None:
    rgb = np.full((6, 6, 3), 255, dtype=np.uint8)
    rgb[1, :] = (255, 0, 0)
    rgb[4, :] = (0, 0, 255)
    u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
    assert set(np.unique(u.conductor_ids).tolist()) == {-1, 1, 2}
    assert u.conductor_mask("+1").sum() == u.conductor_mask(1).sum() == 6


def test_vectorised_init_matches_reference_loop() -> None:
    rng = np.random.default_rng(0)
    colours = np.array([(255, 0, 0), (0, 0, 255), (0, 255, 0), (223, 247, 136), (255, 255, 255), (7, 7, 7)], dtype=np.uint8)
    idx = rng.integers(0, len(colours), size=(50, 70))
    rgb = colours[idx]
    u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4), unknown_warning=False)
    # reference: slow per-pixel mapping through the same lookup
    seen: dict[tuple[int, int, int], int] = {}
    ref = np.full((50, 70), -1, dtype=np.int16)
    mats = []
    for y in range(50):
        for x in range(70):
            key = tuple(int(v) for v in rgb[y, x])
            if key in seen:
                ref[y, x] = seen[key]
                continue
            m = u.material_lookup.get(key)  # type: ignore[arg-type]
            if m is None:
                continue
            seen[key] = len(mats)  # type: ignore[assignment]
            mats.append(m)
            ref[y, x] = seen[key]  # type: ignore[assignment]
    # material order may differ; compare by material name per pixel
    names_u = np.array([m.name for m in u.materials] + ["vacuum"])[np.where(u.codes < 0, len(u.materials), u.codes)]
    names_r = np.array([m.name for m in mats] + ["vacuum"])[np.where(ref < 0, len(mats), ref)]
    assert (names_u == names_r).all()


def test_replicate_and_extend_keep_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    u = three_conductor_map()
    padded = u.replicate_edges(3)
    assert padded.shape == (26, 46)
    assert padded.conductor_mask(1).sum() == 14
    assert padded.conductor_mask(0).sum() == 46 * 1 + 0 or padded.conductor_mask(0).any()
    big = extension.extend_to_shape(u, 40, 80)
    assert big.n_signal_conductors == 2
    assert big.conductor_mask(2).sum() == 14
```

Replace the odd `or` assertion in the last test with the plain `assert padded.conductor_mask(0).sum() == 46` (the ground row replicates into the 3 padded rows below it and 3 columns on each side, so the row is 46 wide and the three rows below are copies: total `46 * 4`; write the value the padding actually produces after reading `replicate_edges`, and pin it).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_usermap_labels.py -v`
Expected: FAIL with `AttributeError: type object 'Usermap' has no attribute 'from_labels'`

- [ ] **Step 3: Implement**

In `src/lineforge/geometry/usermap.py` replace the constructor body (lines 61-105) with a vectorised version and add the new members:

```python
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

    def _codes_from_rgb(self, rgb: np.ndarray, unknown_warning: bool) -> tuple[list[MaterialRecord], np.ndarray]:
        packed = (rgb[:, :, 0].astype(np.int32) << 16) | (rgb[:, :, 1].astype(np.int32) << 8) | rgb[:, :, 2].astype(np.int32)
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
        has_minus = any(m.use == "-1" for m in self.materials)
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
        if not has_minus:
            pass
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
        h, w = material_ids.shape
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        for idx, mat in enumerate(materials):
            rgb[material_ids == idx] = mat.rgb
        meta = UsermapMetadata(pixel_width_m=pixel_width_m, name=name, source="labels")
        u = cls(rgb, meta, unknown_warning=False, _codes=material_ids.astype(np.int16), _materials=materials, _conductor_ids=conductor_ids)
        if conductor_ids is not None:
            cid = np.asarray(conductor_ids)
            if cid.shape != material_ids.shape:
                raise ValueError("conductor_ids must match material_ids in shape")
            conductor_material = np.zeros(material_ids.shape, dtype=bool)
            for idx, mat in enumerate(materials):
                if mat.is_conductor:
                    conductor_material |= material_ids == idx
            if ((cid >= 0) | (cid == -2)).any() and not conductor_material[(cid >= 0) | (cid == -2)].all():
                raise ValueError("conductor_ids marks a pixel whose material is not a conductor")
        return u

    @property
    def n_signal_conductors(self) -> int:
        return int(self.conductor_ids.max(initial=0))
```

Update `conductor_mask`:
```python
    def conductor_mask(self, use: str | int | None = None) -> np.ndarray:
        if isinstance(use, int) and not isinstance(use, bool):
            return self.conductor_ids == use
        mask = np.zeros(self.codes.shape, dtype=bool)
        for idx, mat in enumerate(self.materials):
            if mat.is_conductor and (use is None or mat.use == use):
                mask |= self.codes == idx
        if use is None:
            mask |= self.conductor_ids >= 0
            mask |= self.conductor_ids == -2
        return mask
```

Update `replicate_edges` to pad `codes` and `conductor_ids` with `np.pad(..., mode="edge")` and construct the padded map through the private keyword arguments (`_codes`, `_materials`, `_conductor_ids`) so labels survive. Then read `src/lineforge/solvers/extension.py`: every construction of a new `Usermap` from an rgb array must pass the padded `codes`/`conductor_ids` the same way (the coarse-pixel outer ring in `extend` replicates the edge material, so `np.pad(mode="edge")` on both label arrays is the correct counterpart to what it does to `rgb`).

- [ ] **Step 4: Run the new test and the whole existing suite**

Run: `.venv/bin/pytest tests/test_usermap_labels.py tests/test_usermap.py tests/test_solvers -q`
Expected: all passed; the existing usermap and solver tests are unchanged in behaviour (same codes, same results).

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/geometry/usermap.py src/lineforge/solvers/extension.py tests/test_usermap_labels.py
git commit -m "feat(usermap): label-based construction, integer conductor ids, vectorised colour mapping"
```

---

### Task 2: Djordjevic-Sarkar and roughness fields on MaterialRecord

**Files:**
- Modify: `src/lineforge/materials/database.py` (`MaterialRecord`, lines 25-93), `src/lineforge/materials/morecolors.py` (`load_json_pack` at 182, `dump_json_pack` at 222)
- Test: `tests/test_materials_ds.py`

**Interfaces:**
- Produces: `DSParams(eps_inf: float, delta_eps: float, f1_hz: float = 1e3, f2_hz: float = 1e12, sigma_dc_s_per_m: float = 0.0)` (frozen pydantic) with `er_complex(freq_hz) -> complex` and classmethod `fit_point(er, tan_delta, f_ref_hz, f1_hz=1e3, f2_hz=1e12) -> DSParams`; `RoughnessSpec(model: Literal["hammerstad", "huray", "groisse"], rms_um: float | None = None, radius_um: float | None = None, ratio: float | None = None, rz_um: float | None = None)`; `MaterialRecord.ds_params: DSParams | None = None`, `MaterialRecord.roughness: RoughnessSpec | None = None`, `MaterialRecord.er_complex(freq_hz) -> complex` (DS if present, else tables via `material_at_frequency`, else constants; returns `er' - j er''`).
- JSON packs: optional keys `"ds_params": {...}` and `"roughness": {...}` per record, written by `dump_json_pack` only when set.

- [ ] **Step 1: Write the failing test**

`tests/test_materials_ds.py`:
```python
"""Causal dielectric parameters and roughness metadata on MaterialRecord."""

from __future__ import annotations

import json
import math

import pytest

from lineforge.materials.database import DSParams, MaterialRecord, RoughnessSpec
from lineforge.materials.morecolors import dump_json_pack, load_json_pack


def test_ds_fit_point_reproduces_anchor_and_is_lossy() -> None:
    ds = DSParams.fit_point(er=4.3, tan_delta=0.02, f_ref_hz=1e9)
    e = ds.er_complex(1e9)
    assert e.real == pytest.approx(4.3, rel=1e-9)
    assert -e.imag / e.real == pytest.approx(0.02, rel=1e-9)
    assert ds.er_complex(1e6).real > ds.er_complex(1e10).real
    assert ds.er_complex(1e7).imag < 0


def test_material_er_complex_prefers_ds_then_tables_then_constants() -> None:
    ds = DSParams.fit_point(er=3.66, tan_delta=0.0037, f_ref_hz=1e10)
    m_ds = MaterialRecord(rgb=(1, 2, 3), use="insul", er=3.66, tan_delta=0.0037, name="ro4350-ds", ds_params=ds)
    m_tab = MaterialRecord(rgb=(1, 2, 4), use="insul", er=3.66, tan_delta=0.0037, name="ro4350-tab", er_freq={1e8: 3.66, 4e10: 3.65}, tan_freq={1e8: 0.004, 4e10: 0.0048})
    m_const = MaterialRecord(rgb=(1, 2, 5), use="insul", er=3.66, tan_delta=0.0037, name="ro4350")
    assert m_ds.er_complex(1e10).real == pytest.approx(3.66, rel=1e-9)
    assert m_tab.er_complex(1e8).real == pytest.approx(3.66)
    assert m_tab.er_complex(4e10) == pytest.approx(complex(3.65, -3.65 * 0.0048))
    assert m_const.er_complex(1e9) == pytest.approx(complex(3.66, -3.66 * 0.0037))


def test_roughness_spec_and_pack_roundtrip(tmp_path) -> None:
    rough = RoughnessSpec(model="huray", radius_um=0.5, ratio=4.887)
    cu = MaterialRecord(rgb=(255, 0, 0), use="+1", name="rough copper", roughness=rough)
    text = dump_json_pack([cu], name="t", version="1.0.0")
    data = json.loads(text)
    assert data["materials"][0]["roughness"]["model"] == "huray"
    path = tmp_path / "pack.json"
    path.write_text(text)
    back = load_json_pack(path)
    assert back[0].roughness == rough
    assert back[0].ds_params is None


def test_roughness_spec_requires_model_parameters() -> None:
    with pytest.raises(ValueError):
        RoughnessSpec(model="hammerstad")
    with pytest.raises(ValueError):
        RoughnessSpec(model="huray", radius_um=0.5)
    assert RoughnessSpec(model="huray", rz_um=6.0).radius_um == pytest.approx(6.0 / (2 * (1 + math.sqrt(2))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_materials_ds.py -v`
Expected: FAIL with `ImportError: cannot import name 'DSParams'`

- [ ] **Step 3: Implement**

Add to `src/lineforge/materials/database.py` above `MaterialRecord`:
```python
EPS0 = 8.8541878128e-12
_CANNONBALL_HEIGHT = 2.0 * (1.0 + math.sqrt(2.0))  # stack height of 14 close-packed spheres in radii


class DSParams(BaseModel):
    """Djordjevic-Sarkar wideband Debye (IEEE Trans. EMC 43(4), 2001), causal by construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    eps_inf: float = Field(..., gt=0)
    delta_eps: float = Field(..., ge=0)
    f1_hz: float = Field(1e3, gt=0)
    f2_hz: float = Field(1e12, gt=0)
    sigma_dc_s_per_m: float = Field(0.0, ge=0)

    def _units(self, freq_hz: float) -> tuple[float, float]:
        w = 2.0 * math.pi * freq_hz
        w1 = 2.0 * math.pi * self.f1_hz
        w2 = 2.0 * math.pi * self.f2_hz
        span = math.log(self.f2_hz / self.f1_hz)
        real_unit = math.log(math.hypot(w2, w) / math.hypot(w1, w)) / span
        imag_unit = (math.atan2(w, w2) - math.atan2(w, w1)) / span
        return real_unit, imag_unit

    def er_complex(self, freq_hz: float) -> complex:
        if freq_hz <= 0:
            raise ValueError("freq_hz must be positive")
        real_unit, imag_unit = self._units(freq_hz)
        w = 2.0 * math.pi * freq_hz
        cond = self.sigma_dc_s_per_m / (w * EPS0)
        return complex(self.eps_inf + self.delta_eps * real_unit, self.delta_eps * imag_unit - cond)

    @classmethod
    def fit_point(cls, er: float, tan_delta: float, f_ref_hz: float, f1_hz: float = 1e3, f2_hz: float = 1e12) -> DSParams:
        probe = cls(eps_inf=1.0, delta_eps=1.0, f1_hz=f1_hz, f2_hz=f2_hz)
        real_unit, imag_unit = probe._units(f_ref_hz)
        delta_eps = -tan_delta * er / imag_unit if imag_unit != 0 else 0.0
        return cls(eps_inf=er - delta_eps * real_unit, delta_eps=delta_eps, f1_hz=f1_hz, f2_hz=f2_hz)


class RoughnessSpec(BaseModel):
    """Conductor surface roughness description consumed by ``solvers.roughness``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["hammerstad", "huray", "groisse"]
    rms_um: float | None = Field(None, gt=0)
    radius_um: float | None = Field(None, gt=0)
    ratio: float | None = Field(None, gt=0)
    rz_um: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _complete(self) -> RoughnessSpec:
        if self.model in ("hammerstad", "groisse") and self.rms_um is None:
            raise ValueError(f"{self.model} roughness needs rms_um")
        if self.model == "huray":
            if self.rz_um is not None and self.radius_um is None:
                radius = self.rz_um / _CANNONBALL_HEIGHT
                object.__setattr__(self, "radius_um", radius)
                if self.ratio is None:
                    object.__setattr__(self, "ratio", 14.0 * 4.0 * math.pi / 36.0)
            if self.radius_um is None or self.ratio is None:
                raise ValueError("huray roughness needs radius_um and ratio, or rz_um for the cannonball parameterisation")
        return self
```
(`import math` and `from pydantic import model_validator`, `Literal` from typing.)

On `MaterialRecord` add the two fields and the method:
```python
    ds_params: DSParams | None = Field(None, description="Djordjevic-Sarkar parameters; overrides er/tan tables when set.")
    roughness: RoughnessSpec | None = Field(None, description="Surface roughness model for conductors.")

    def er_complex(self, freq_hz: float) -> complex:
        """Complex relative permittivity ``er' - j er''`` at ``freq_hz``."""
        if self.ds_params is not None:
            return self.ds_params.er_complex(freq_hz)
        er, tan = self.at_frequency(freq_hz)
        return complex(er, -er * tan)
```
In `morecolors.load_json_pack` construct `ds_params=DSParams(**rec["ds_params"]) if rec.get("ds_params") else None` and `roughness=RoughnessSpec(**rec["roughness"]) if rec.get("roughness") else None`; in `dump_json_pack` emit the keys only when set (`model_dump(exclude_none=True)`).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_materials_ds.py tests/test_materials.py tests/test_dispersion.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/materials tests/test_materials_ds.py
git commit -m "feat(materials): Djordjevic-Sarkar parameters and roughness specs on MaterialRecord"
```

---

### Task 3: Roughness factors

**Files:**
- Create: `src/lineforge/solvers/roughness.py`
- Test: `tests/test_solvers/test_roughness.py`

**Interfaces:**
- Produces: `hammerstad_factor(delta_m: float, rms_m: float) -> float` (`1 + (2/pi) atan(1.4 (rms/delta)^2)`, Hammerstad and Bekkadal 1975); `groisse_factor(delta_m, rms_m) -> float` (`1 + exp(-(delta/(2 rms))^1.6)`, Groisse et al., IEEE Trans. Magnetics 1996); `huray_factor(delta_m, radius_m, ratio) -> float` (`1 + (3/2) ratio / (1 + delta/a + delta^2/(2 a^2))`, Huray, The Foundations of Signal Integrity, ch. 6, with `ratio = N 4 pi a^2 / A_flat`); `cannonball_from_rz(rz_m) -> tuple[float, float]` returning `(a, ratio)` with `a = Rz / (2 (1 + sqrt 2))`, `ratio = 14 * 4 pi / 36` (Simonovich, DesignCon 2015, 9-4-1 stack on a 6a by 6a base); `roughness_factor(spec: RoughnessSpec, delta_m: float) -> float` dispatch.

- [ ] **Step 1: Write the failing test**

`tests/test_solvers/test_roughness.py`:
```python
"""Roughness correction factors: limits and one hand-computed cannonball value."""

from __future__ import annotations

import math

import pytest

from lineforge.materials.database import RoughnessSpec
from lineforge.solvers.roughness import cannonball_from_rz, groisse_factor, hammerstad_factor, huray_factor, roughness_factor
from lineforge.solvers.skin_depth import compute_delta
from lineforge.materials.database import MaterialRecord

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")


def test_hammerstad_limits() -> None:
    assert hammerstad_factor(1e-3, 1e-6) == pytest.approx(1.0, abs=1e-4)
    assert hammerstad_factor(1e-9, 1e-6) == pytest.approx(2.0, abs=1e-4)
    assert hammerstad_factor(1e-6, 1e-6) == pytest.approx(1 + (2 / math.pi) * math.atan(1.4))


def test_groisse_limits() -> None:
    assert groisse_factor(1e-3, 1e-6) == pytest.approx(1.0, abs=1e-6)
    assert groisse_factor(1e-9, 1e-6) == pytest.approx(2.0, abs=1e-3)


def test_huray_cannonball_hand_value() -> None:
    a, ratio = cannonball_from_rz(6e-6)
    assert a == pytest.approx(6e-6 / (2 * (1 + math.sqrt(2))))
    assert ratio == pytest.approx(14 * 4 * math.pi / 36)
    delta = compute_delta(CU, 10e9)
    k = huray_factor(delta, a, ratio)
    expected = 1 + 1.5 * ratio / (1 + delta / a + delta**2 / (2 * a * a))
    assert k == pytest.approx(expected)
    assert huray_factor(1e-3, a, ratio) == pytest.approx(1.0, abs=1e-3)
    assert huray_factor(1e-12, a, ratio) == pytest.approx(1 + 1.5 * ratio, rel=1e-4)


def test_dispatch_by_spec() -> None:
    delta = compute_delta(CU, 5e9)
    assert roughness_factor(RoughnessSpec(model="hammerstad", rms_um=1.0), delta) == pytest.approx(hammerstad_factor(delta, 1e-6))
    assert roughness_factor(RoughnessSpec(model="groisse", rms_um=1.0), delta) == pytest.approx(groisse_factor(delta, 1e-6))
    spec = RoughnessSpec(model="huray", rz_um=6.0)
    assert roughness_factor(spec, delta) == pytest.approx(huray_factor(delta, spec.radius_um * 1e-6, spec.ratio))  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_solvers/test_roughness.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/lineforge/solvers/roughness.py`:
```python
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


__all__ = ["cannonball_from_rz", "groisse_factor", "hammerstad_factor", "huray_factor", "roughness_factor"]
```

- [ ] **Step 4: Run test**

Run: `.venv/bin/pytest tests/test_solvers/test_roughness.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/solvers/roughness.py tests/test_solvers/test_roughness.py
git commit -m "feat(solvers): Hammerstad, Groisse and Huray roughness factors"
```

---

### Task 4: N-conductor Maxwell matrices from the Laplace solver

**Files:**
- Create: `src/lineforge/solvers/mtl.py`
- Modify: `src/lineforge/solvers/__init__.py` (export `MaxwellResult`, `solve_maxwell`, `rlgc_matrices`)
- Test: `tests/test_solvers/test_mtl.py`

**Interfaces:**
- Produces: `MaxwellResult(conductor_ids: list[int], C0: np.ndarray, W: dict[int, np.ndarray], W0: np.ndarray, materials: list[MaterialRecord], phi: np.ndarray | None, phi0: np.ndarray | None, iterations: list[int], warnings: list[SolverWarning], pixel_width_m: float)` where `W[m]` is the (N, N) energy matrix restricted to pixels of material index `m` (`-1` is vacuum), computed from the potentials solved with the materials' `er` at `f_ref_hz`; `W0` the all-space energy matrix of the vacuum solves; `C0 = eps0 W0`.
- Produces: `solve_maxwell(usermap: Usermap, *, f_ref_hz: float | None = None, method: str = "auto", tol: float = 1e-7, max_iter: int | None = None, extend_grid: bool = True, target_extent: int = 3200, keep_fields: bool = False) -> MaxwellResult`.
- Produces: `rlgc_matrices(res: MaxwellResult, freq_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]` returning `(C, G, L_ext)` in F/m, S/m, H/m using each material's `er_complex(freq_hz)`: `C = eps0 sum_m Re(er_m) W[m]`, `G = omega eps0 sum_m (-Im(er_m)) W[m]`, `L_ext = mu0 eps0 inv(C0)`.
- Drive convention: for signal conductor k, `phi_k` has conductor k at 1 V, every other conductor (reference and signals) at 0 V, floating groups (`conductor_ids == -2`) handled through `float_groups`. The outer grid boundary is 0 V as in `solve_cgp`.
- Energy matrix entries: `W[j, k] = sum_pixels (Ex_j Ex_k + Ey_j Ey_k)` with the same central-difference gradient as `cgp._energy_integral` (pixel units cancel in 2-D), so `C = eps0 * W` is directly F/m, matching `solve_cgp` for N = 1.

- [ ] **Step 1: Write the failing test**

`tests/test_solvers/test_mtl.py`:
```python
"""Maxwell capacitance matrices reduce to the existing single-line and differential solvers."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord
from lineforge.solvers import cgp, diff_modes, extension
from lineforge.solvers.mtl import rlgc_matrices, solve_maxwell

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
CU2 = MaterialRecord(rgb=(0, 0, 255), use="-1", name="copper2")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")
FR4 = MaterialRecord(rgb=(223, 247, 136), use="insul", er=3.7, tan_delta=0.018, name="FR4", resistivity_ohm_cm=1e6)


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    def _small(usermap: Usermap, **_kw: object) -> Usermap:
        return usermap.replicate_edges(4)

    monkeypatch.setattr(cgp.extension, "extend", _small)
    monkeypatch.setattr(diff_modes.extension, "extend", _small)
    monkeypatch.setattr(extension, "extend", _small)


def stripline_pair(with_second: bool) -> tuple[Usermap, Usermap]:
    """Two label maps of the same geometry: one with fieldforge ids, one RGB-role encoded."""
    h, w = 30, 60
    mat = np.full((h, w), 1, dtype=np.int32)  # FR4 everywhere
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[0, :] = 0
    cid[0, :] = 0
    mat[h - 1, :] = 0
    cid[h - 1, :] = 0
    mat[14:16, 15:25] = 0
    cid[14:16, 15:25] = 1
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:] = FR4.rgb
    rgb[0, :] = GND.rgb
    rgb[h - 1, :] = GND.rgb
    rgb[14:16, 15:25] = CU.rgb
    if with_second:
        mat[14:16, 35:45] = 0
        cid[14:16, 35:45] = 2
        rgb[14:16, 35:45] = CU2.rgb
    labels = Usermap.from_labels(mat, [CU, FR4], pixel_width_m=2e-5, conductor_ids=cid)
    roles = Usermap(rgb, labels.meta, unknown_warning=False)
    return labels, roles


def test_single_conductor_matches_solve_cgp() -> None:
    labels, roles = stripline_pair(with_second=False)
    res = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True)
    C, G, L = rlgc_matrices(res, 1e9)
    ref = cgp.solve_cgp(roles, frequency_hz=1e9, method="sor", tol=1e-6, extend_grid=True)
    assert C.shape == (1, 1)
    assert C[0, 0] == pytest.approx(ref.C_per_m, rel=2e-3)
    assert L[0, 0] == pytest.approx(ref.L_per_m, rel=2e-3)
    assert G[0, 0] == pytest.approx(ref.Gp_per_m, rel=2e-3)


def test_pair_reduces_to_odd_and_even_modes() -> None:
    labels, roles = stripline_pair(with_second=True)
    res = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True)
    C, _, L = rlgc_matrices(res, 1e9)
    assert C.shape == (2, 2)
    assert C[0, 1] == pytest.approx(C[1, 0], rel=1e-6)
    assert C[0, 1] < 0 < C[0, 0]
    modes = diff_modes.solve_modes(roles)
    c_odd = C[0, 0] - C[0, 1]
    c_even = C[0, 0] + C[0, 1]
    z_odd = np.sqrt((L[0, 0] - L[0, 1]) / c_odd)
    z_even = np.sqrt((L[0, 0] + L[0, 1]) / c_even)
    assert z_odd == pytest.approx(modes.z_odd, rel=3e-3)
    assert z_even == pytest.approx(modes.z_even, rel=3e-3)
    eig = np.linalg.eigvalsh(C)
    assert (eig > 0).all()


def test_keep_fields_and_warnings_shape() -> None:
    labels, _ = stripline_pair(with_second=True)
    res = solve_maxwell(labels, method="sor", tol=1e-5, extend_grid=False, keep_fields=True)
    assert res.phi is not None and res.phi.shape[0] == 2
    assert res.conductor_ids == [1, 2]
    assert set(res.W) >= {0, 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_solvers/test_mtl.py -v`
Expected: FAIL with `ModuleNotFoundError: lineforge.solvers.mtl`

- [ ] **Step 3: Implement**

`src/lineforge/solvers/mtl.py`:
```python
"""N-conductor Maxwell capacitance and external inductance matrices from Laplace solves.

For signal conductor k the potential phi_k has conductor k at 1 V and every other conductor at 0 V.
The energy matrix W[j, k] = sum over pixels of grad(phi_j) . grad(phi_k) is dimensionless in 2-D, so
C = eps0 * sum_m er_m * W_m is the Maxwell capacitance matrix in F/m (region-partitioned by material),
G = omega * eps0 * sum_m er_m tan_m W_m, and L_ext = mu0 eps0 inv(C0) with C0 from vacuum solves.
Paul, Analysis of Multiconductor Transmission Lines, 2nd ed., ch. 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord
from lineforge.results import SolverWarning
from lineforge.solvers import extension, laplace

EPS0 = 8.8541878128e-12
MU0 = 4e-7 * np.pi


@dataclass
class MaxwellResult:
    conductor_ids: list[int]
    C0: np.ndarray
    W: dict[int, np.ndarray]
    W0: np.ndarray
    materials: list[MaterialRecord]
    pixel_width_m: float
    phi: np.ndarray | None = None
    phi0: np.ndarray | None = None
    iterations: list[int] = field(default_factory=list)
    warnings: list[SolverWarning] = field(default_factory=list)


def _gradients(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ex = np.zeros_like(v)
    ex[:, 1:-1] = -(v[:, 2:] - v[:, :-2]) / 2.0
    ey = np.zeros_like(v)
    ey[1:-1, :] = -(v[2:, :] - v[:-2, :]) / 2.0
    return ex, ey


def _solve_set(
    usermap: Usermap, er_field: np.ndarray, ids: list[int], *, method: str, tol: float, max_iter: int | None
) -> tuple[np.ndarray, list[int]]:
    all_conductors = usermap.conductor_mask(None)
    floats = [usermap.conductor_ids == -2]
    float_groups = [g for g in floats if g.any()]
    fixed = all_conductors & ~(usermap.conductor_ids == -2)
    phi = np.zeros((len(ids), *usermap.shape), dtype=np.float64)
    iters: list[int] = []
    for n, k in enumerate(ids):
        v_value = np.zeros(usermap.shape, dtype=np.float64)
        v_value[usermap.conductor_ids == k] = 1.0
        res = laplace.solve_laplace(er_field, fixed, v_value, method=method, tol=tol, max_iter=max_iter, float_groups=float_groups)
        phi[n] = res.v_field
        iters.append(res.iterations)
    return phi, iters


def _energy_matrices(phi: np.ndarray, codes: np.ndarray) -> tuple[dict[int, np.ndarray], np.ndarray]:
    n = phi.shape[0]
    grads = [_gradients(phi[i]) for i in range(n)]
    total = np.zeros((n, n))
    per_material: dict[int, np.ndarray] = {}
    material_codes = [int(c) for c in np.unique(codes)]
    for m in material_codes:
        sel = codes == m
        w = np.zeros((n, n))
        for j in range(n):
            exj, eyj = grads[j]
            for k in range(j, n):
                exk, eyk = grads[k]
                val = float(((exj * exk + eyj * eyk)[sel]).sum())
                w[j, k] = val
                w[k, j] = val
        per_material[m] = w
        total += w
    return per_material, total


def solve_maxwell(
    usermap: Usermap,
    *,
    f_ref_hz: float | None = None,
    method: str = "auto",
    tol: float = 1e-7,
    max_iter: int | None = None,
    extend_grid: bool = True,
    target_extent: int = 3200,
    keep_fields: bool = False,
) -> MaxwellResult:
    ids = sorted(int(i) for i in np.unique(usermap.conductor_ids) if i >= 1)
    if not ids:
        raise ValueError("usermap has no signal conductors (conductor_ids >= 1)")
    extended = extension.extend(usermap, target_size=target_extent) if extend_grid else usermap
    if f_ref_hz is None:
        er_field = extended.er_field()
    else:
        er_field = np.ones(extended.shape, dtype=np.float64)
        for idx, mat in enumerate(extended.materials):
            if mat.is_insulator:
                er_field[extended.codes == idx] = mat.er_complex(f_ref_hz).real
    phi, it1 = _solve_set(extended, er_field, ids, method=method, tol=tol, max_iter=max_iter)
    w_per_material, _ = _energy_matrices(phi, extended.codes)
    phi0, it0 = _solve_set(extended, np.ones_like(er_field), ids, method=method, tol=tol, max_iter=max_iter)
    _, w0 = _energy_matrices(phi0, extended.codes)
    c0 = EPS0 * w0
    warnings: list[SolverWarning] = []
    if np.linalg.eigvalsh(c0).min() <= 0:
        warnings.append(SolverWarning(code="c0_not_positive_definite", message="vacuum capacitance matrix is not positive definite; check conductor labels", severity="error"))
    return MaxwellResult(
        conductor_ids=ids, C0=c0, W=w_per_material, W0=w0, materials=list(extended.materials), pixel_width_m=extended.pixel_width_m,
        phi=phi if keep_fields else None, phi0=phi0 if keep_fields else None, iterations=it1 + it0, warnings=warnings,
    )


def rlgc_matrices(res: MaxwellResult, freq_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(res.conductor_ids)
    c = np.zeros((n, n))
    g = np.zeros((n, n))
    omega = 2.0 * np.pi * freq_hz
    for m, w in res.W.items():
        if m < 0:
            er = complex(1.0, 0.0)
        else:
            mat = res.materials[m]
            er = mat.er_complex(freq_hz) if mat.is_insulator else complex(1.0, 0.0)
        c += er.real * w
        g += (-er.imag) * w
    c *= EPS0
    g *= omega * EPS0
    l_ext = MU0 * EPS0 * np.linalg.inv(res.C0)
    return c, g, l_ext


__all__ = ["MaxwellResult", "rlgc_matrices", "solve_maxwell"]
```

Add `from lineforge.solvers.mtl import MaxwellResult, rlgc_matrices, solve_maxwell` and the three names to `__all__` in `src/lineforge/solvers/__init__.py`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_solvers/test_mtl.py -v`
Expected: 3 passed. If the N = 1 comparison is off by exactly a factor of 4, `solve_cgp` drove +1/-1 (V_drive = 2) because the RGB map had a `-1` conductor; the fixture uses ground rows so V_drive is 1; check `has_minus` in `solve_cgp`. If the odd/even impedances disagree by more than 0.3 percent, both solvers must share the same extension monkeypatch (the fixture patches all three modules).

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/solvers/mtl.py src/lineforge/solvers/__init__.py tests/test_solvers/test_mtl.py
git commit -m "feat(solvers): N-conductor Maxwell capacitance and inductance matrices"
```

---

### Task 5: Skin-effect resistance by Wheeler's incremental inductance rule

**Files:**
- Create: `src/lineforge/solvers/wheeler.py`
- Test: `tests/test_solvers/test_wheeler.py`

**Interfaces:**
- Produces: `WheelerResult(R_per_m: np.ndarray (N,N), L_int_per_m: np.ndarray (N,N), per_conductor: dict[int, np.ndarray], frequency_hz: float, roughness_factors: dict[int, float], warnings: list[SolverWarning])`; `solve_wheeler_resistance(usermap, *, frequency_hz: float, base: MaxwellResult | None = None, method="auto", tol=1e-7, extend_grid=True, roughness: dict[int, RoughnessSpec] | None = None, erode_pixels: int = 1) -> WheelerResult`.
- Method (Wheeler, Proc. IRE 30, 1942; Pozar, Microwave Engineering, section 2.7): with skin depth `delta << conductor dimensions`, `R = (Rs / mu0) * dL_ext / dn`, where `dL_ext/dn` is the change of the external inductance matrix when conductor `c`'s surface recedes by `dn`. For each conductor id `c` in `{0} ∪ signals ∪ floats`, erode that conductor's pixel set by `erode_pixels` (binary erosion, `scipy.ndimage.binary_erosion`), re-run the vacuum Maxwell solve, and take `dL_c = (L_ext_eroded - L_ext) / (erode_pixels * px)`. `R = sum_c K_c(f) (Rs(f)/mu0) dL_c` with `K_c` the roughness factor of conductor `c` (1 when no spec). `L_int = R / omega`. Conductors thinner than `2 * erode_pixels + 1` pixels raise `SolverWarning("conductor_too_thin_for_wheeler")` and are skipped. Skin-depth resolution is not needed (that is the point of the rule); validity requires `delta < t/3` and is reported when violated (`skin_depth_not_small`).

- [ ] **Step 1: Write the failing test**

`tests/test_solvers/test_wheeler.py`:
```python
"""Wheeler incremental-inductance resistance: sqrt(f) scaling, symmetry, and the wide-strip closed form."""

from __future__ import annotations

import math

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord, RoughnessSpec
from lineforge.solvers import extension
from lineforge.solvers.mtl import solve_maxwell
from lineforge.solvers.wheeler import solve_wheeler_resistance

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
VAC = MaterialRecord(rgb=(255, 255, 255), use="insul", name="vacuum", resistivity_ohm_cm=1e6)
MU0 = 4e-7 * math.pi
RHO = 1.7241e-8


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extension, "extend", lambda u, **_k: u.replicate_edges(6))


def parallel_plate(width_px: int = 80, gap_px: int = 8, t_px: int = 5, px: float = 1e-5) -> Usermap:
    h = gap_px + 2 * t_px + 20
    w = width_px + 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    top = slice(10, 10 + t_px)
    bot = slice(10 + t_px + gap_px, 10 + 2 * t_px + gap_px)
    cols = slice(20, 20 + width_px)
    mat[top, cols] = 0
    cid[top, cols] = 1
    mat[bot, cols] = 0
    cid[bot, cols] = 0
    return Usermap.from_labels(mat, [CU], pixel_width_m=px, conductor_ids=cid)


def test_sqrt_f_scaling_and_symmetry() -> None:
    u = parallel_plate()
    base = solve_maxwell(u, method="sor", tol=1e-6, extend_grid=True)
    r1 = solve_wheeler_resistance(u, frequency_hz=1e9, base=base, method="sor", tol=1e-6)
    r4 = solve_wheeler_resistance(u, frequency_hz=4e9, base=base, method="sor", tol=1e-6)
    assert r4.R_per_m[0, 0] == pytest.approx(2.0 * r1.R_per_m[0, 0], rel=1e-9)
    assert r1.L_int_per_m[0, 0] == pytest.approx(r1.R_per_m[0, 0] / (2 * math.pi * 1e9))


def test_wide_parallel_plate_matches_closed_form() -> None:
    """Wide parallel plates: R = 2 Rs / W per metre (both conductors), within the pixel discretisation."""
    px = 1e-5
    width_px = 80
    u = parallel_plate(width_px=width_px, gap_px=8, t_px=5, px=px)
    f = 5e9
    res = solve_wheeler_resistance(u, frequency_hz=f, method="sor", tol=1e-6)
    rs = math.sqrt(math.pi * f * MU0 * RHO)
    expected = 2.0 * rs / (width_px * px)
    assert res.R_per_m[0, 0] == pytest.approx(expected, rel=0.25)


def test_roughness_scales_only_the_rough_conductor() -> None:
    u = parallel_plate()
    smooth = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    rough = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6, roughness={1: RoughnessSpec(model="hammerstad", rms_um=2.0)})
    k = rough.roughness_factors[1]
    assert k > 1.5
    contribution_signal = smooth.per_conductor[1][0, 0]
    contribution_ref = smooth.per_conductor[0][0, 0]
    assert rough.R_per_m[0, 0] == pytest.approx(k * contribution_signal + contribution_ref, rel=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_solvers/test_wheeler.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/lineforge/solvers/wheeler.py`:
```python
"""Conductor loss by Wheeler's incremental inductance rule on the Maxwell inductance matrix.

R = (Rs / mu0) dL_ext/dn, evaluated per conductor by eroding its cross-section one pixel and
re-solving the vacuum Laplace problem (Wheeler, Proc. IRE 30, 1942; Pozar, Microwave Engineering,
section 2.7). Roughness multiplies each conductor's own contribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import RoughnessSpec
from lineforge.results import SolverWarning
from lineforge.solvers.mtl import EPS0, MU0, MaxwellResult, solve_maxwell
from lineforge.solvers.roughness import roughness_factor
from lineforge.solvers.skin_depth import compute_delta


@dataclass
class WheelerResult:
    R_per_m: np.ndarray
    L_int_per_m: np.ndarray
    per_conductor: dict[int, np.ndarray]
    frequency_hz: float
    roughness_factors: dict[int, float]
    warnings: list[SolverWarning] = field(default_factory=list)


def _eroded_copy(usermap: Usermap, conductor_id: int, pixels: int) -> tuple[Usermap, bool]:
    mask = usermap.conductor_ids == conductor_id
    eroded = ndimage.binary_erosion(mask, iterations=pixels)
    if not eroded.any():
        return usermap, False
    vacuum_index = -1
    codes = usermap.codes.copy()
    cid = usermap.conductor_ids.copy()
    removed = mask & ~eroded
    codes[removed] = vacuum_index
    cid[removed] = -1
    return Usermap.from_labels(codes, list(usermap.materials), pixel_width_m=usermap.pixel_width_m, conductor_ids=cid), True


def solve_wheeler_resistance(
    usermap: Usermap,
    *,
    frequency_hz: float,
    base: MaxwellResult | None = None,
    method: str = "auto",
    tol: float = 1e-7,
    extend_grid: bool = True,
    roughness: dict[int, RoughnessSpec] | None = None,
    erode_pixels: int = 1,
) -> WheelerResult:
    if base is None:
        base = solve_maxwell(usermap, method=method, tol=tol, extend_grid=extend_grid)
    n = len(base.conductor_ids)
    l_base = MU0 * EPS0 * np.linalg.inv(base.C0)
    px = usermap.pixel_width_m
    conductor_material = next((m for m in usermap.materials if m.is_conductor), None)
    if conductor_material is None:
        raise ValueError("usermap has no conductor material")
    rho = conductor_material.resistivity_ohm_cm * 1e-2
    rs = np.sqrt(np.pi * frequency_hz * MU0 * rho)
    delta = compute_delta(conductor_material, frequency_hz)
    warnings: list[SolverWarning] = []
    ids = sorted({int(i) for i in np.unique(usermap.conductor_ids) if i >= 0} | {int(i) for i in np.unique(usermap.conductor_ids) if i == -2})
    per_conductor: dict[int, np.ndarray] = {}
    factors: dict[int, float] = {}
    total = np.zeros((n, n))
    for c in ids:
        eroded, ok = _eroded_copy(usermap, c, erode_pixels)
        if not ok:
            warnings.append(SolverWarning(code="conductor_too_thin_for_wheeler", message=f"conductor {c} is too thin to erode by {erode_pixels} px; its loss is omitted", severity="warning"))
            continue
        thickness_px = int((usermap.conductor_ids == c).sum(axis=0).max())
        if delta > thickness_px * px / 3.0:
            warnings.append(SolverWarning(code="skin_depth_not_small", message=f"conductor {c}: skin depth {delta:.3g} m exceeds a third of its thickness; Wheeler rule is a high-frequency asymptote", severity="warning"))
        res_c = solve_maxwell(eroded, method=method, tol=tol, extend_grid=extend_grid)
        l_eroded = MU0 * EPS0 * np.linalg.inv(res_c.C0)
        dl_dn = (l_eroded - l_base) / (erode_pixels * px)
        contribution = (rs / MU0) * dl_dn
        spec = (roughness or {}).get(c)
        k = roughness_factor(spec, delta) if spec is not None else 1.0
        factors[c] = k
        per_conductor[c] = contribution
        total += k * contribution
    omega = 2.0 * np.pi * frequency_hz
    return WheelerResult(R_per_m=total, L_int_per_m=total / omega, per_conductor=per_conductor, frequency_hz=frequency_hz, roughness_factors=factors, warnings=warnings)


__all__ = ["WheelerResult", "solve_wheeler_resistance"]
```

Note `_eroded_copy` passes `codes` as `material_ids`: `from_labels` requires the material list to be the usermap's own list so the indices line up, which `list(usermap.materials)` guarantees.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_solvers/test_wheeler.py -v`
Expected: 3 passed. The wide-plate closed form is a 25 percent check because edge crowding on 80-pixel plates with an 8-pixel gap is real; if the error is above that, widen the plates to 160 px and re-check before loosening the tolerance.

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/solvers/wheeler.py tests/test_solvers/test_wheeler.py
git commit -m "feat(solvers): skin-effect resistance matrix by Wheeler incremental inductance with roughness"
```

---

### Task 6: N-conductor PEEC impedance matrix with one LU

**Files:**
- Modify: `src/lineforge/solvers/faraday.py` (add `solve_impedance_matrix`, `SolverBudgetExceeded`; leave `solve_lrs` untouched)
- Test: `tests/test_solvers/test_faraday_matrix.py`

**Interfaces:**
- Produces: `class SolverBudgetExceeded(ValueError)`; `solve_impedance_matrix(usermap, *, frequency_hz: float, restrict_to_skin_depth: bool = True, skin_factor: float = 3.0, max_pixels: int = 6000, tol: float = 1e-8) -> tuple[np.ndarray, np.ndarray]` returning `(R, L)` each (N, N) in ohm/m and H/m. Drive j: `+1 A` on signal conductor j, `-1 A` on the reference (id 0), `0` on other conductors; column j of the impedance matrix is `Z[k, j] = V_k - V_ref` for the per-conductor voltages the constraint rows return. Builds the dense system once with the existing `_build_system` (extended to take `cid` from `conductor_ids` and a `drive` per column), factors it once with `scipy.linalg.lu_factor`, solves N right-hand sides. Raises `SolverBudgetExceeded` when the conductor pixel count after skin masking exceeds `max_pixels`.

- [ ] **Step 1: Write the failing test**

`tests/test_solvers/test_faraday_matrix.py`:
```python
"""The N-conductor PEEC impedance matrix reduces to solve_lrs for one conductor and is symmetric for pairs."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials.database import MaterialRecord
from lineforge.solvers import faraday
from lineforge.solvers.faraday import SolverBudgetExceeded, solve_impedance_matrix

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")


def small_pair(second: bool) -> tuple[Usermap, Usermap]:
    h, w = 16, 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[14:16, :] = 0
    cid[14:16, :] = 0
    mat[4:6, 8:14] = 0
    cid[4:6, 8:14] = 1
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    rgb[14:16, :] = GND.rgb
    rgb[4:6, 8:14] = CU.rgb
    if second:
        mat[4:6, 26:32] = 0
        cid[4:6, 26:32] = 2
    labels = Usermap.from_labels(mat, [CU], pixel_width_m=2e-5, conductor_ids=cid)
    roles = Usermap(rgb, UsermapMetadata(pixel_width_m=2e-5), unknown_warning=False)
    return labels, roles


def test_single_conductor_equals_solve_lrs() -> None:
    labels, roles = small_pair(second=False)
    r, l = solve_impedance_matrix(labels, frequency_hz=1e8, restrict_to_skin_depth=False)
    ref = faraday.solve_lrs(roles, frequency_hz=1e8)
    assert r.shape == (1, 1)
    assert r[0, 0] == pytest.approx(ref.R_per_m, rel=1e-9)
    assert l[0, 0] == pytest.approx(ref.L_per_m, rel=1e-9)


def test_pair_symmetric_with_positive_mutual() -> None:
    labels, _ = small_pair(second=True)
    r, l = solve_impedance_matrix(labels, frequency_hz=1e8, restrict_to_skin_depth=False)
    assert l.shape == (2, 2)
    assert l[0, 1] == pytest.approx(l[1, 0], rel=1e-6)
    assert 0 < l[0, 1] < l[0, 0]
    assert r[0, 0] == pytest.approx(r[1, 1], rel=1e-6)


def test_budget_refusal() -> None:
    labels, _ = small_pair(second=True)
    with pytest.raises(SolverBudgetExceeded):
        solve_impedance_matrix(labels, frequency_hz=1e8, restrict_to_skin_depth=False, max_pixels=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_solvers/test_faraday_matrix.py -v`
Expected: FAIL with `ImportError: cannot import name 'SolverBudgetExceeded'`

- [ ] **Step 3: Implement**

Append to `src/lineforge/solvers/faraday.py`:
```python
class SolverBudgetExceeded(ValueError):
    """The dense PEEC system would exceed the configured pixel budget."""


def _build_system_multi(
    ys: np.ndarray, xs: np.ndarray, pixel_cid: np.ndarray, rho_field: np.ndarray, px: float, omega: float, conductor_index: dict[int, int]
) -> np.ndarray:
    """Dense Z for N conductors without a right-hand side; rows N..N+n_c are the current constraints."""
    N = len(ys)
    n_c = len(conductor_index)
    Z = np.zeros((N + n_c, N + n_c), dtype=np.complex128)
    rho_pixel = rho_field[ys, xs]
    R_diag = rho_pixel / (px * px)
    h, w = rho_field.shape
    d_ref = float(max(h, w)) * px
    yy = ys[:, None].astype(np.float64) * px
    xx = xs[:, None].astype(np.float64) * px
    r2 = (yy - yy.T) ** 2 + (xx - xx.T) ** 2
    np.fill_diagonal(r2, (px * 0.5) ** 2)
    L_partial = (MU0 / (2.0 * np.pi)) * np.log(d_ref / np.sqrt(r2))
    np.fill_diagonal(L_partial, _self_inductance_per_m(px))
    Z[:N, :N] = 1j * omega * L_partial
    np.fill_diagonal(Z[:N, :N], np.diag(Z[:N, :N]) + R_diag)
    for n_idx in range(N):
        Z[n_idx, N + conductor_index[int(pixel_cid[n_idx])]] = -1.0
    for c, col in conductor_index.items():
        rows = np.where(pixel_cid == c)[0]
        Z[N + col, rows] = 1.0
    return Z


def solve_impedance_matrix(
    usermap: Usermap,
    *,
    frequency_hz: float,
    restrict_to_skin_depth: bool = True,
    skin_factor: float = 3.0,
    max_pixels: int = 6000,
    tol: float = 1e-8,
) -> tuple[np.ndarray, np.ndarray]:
    from scipy.linalg import lu_factor, lu_solve

    from lineforge.solvers.skin_depth import mask_skin_depth

    working = mask_skin_depth(usermap, frequency_hz, factor=skin_factor) if restrict_to_skin_depth else usermap
    cid_field = working.conductor_ids
    ys, xs = np.where(cid_field >= 0)
    if len(ys) > max_pixels:
        raise SolverBudgetExceeded(f"{len(ys)} conductor pixels exceed the budget of {max_pixels}")
    if len(ys) == 0:
        raise ValueError("no conductor pixels in usermap")
    pixel_cid = cid_field[ys, xs]
    ids = sorted({int(c) for c in np.unique(pixel_cid)})
    if 0 not in ids:
        raise ValueError("solve_impedance_matrix needs a reference conductor with id 0")
    signals = [c for c in ids if c >= 1]
    conductor_index = {c: i for i, c in enumerate(ids)}
    omega = 2.0 * np.pi * frequency_hz
    Z = _build_system_multi(ys, xs, pixel_cid, working.resistivity_field_ohm_m(), working.pixel_width_m, omega, conductor_index)
    N = len(ys)
    lu = lu_factor(Z)
    n = len(signals)
    zmat = np.zeros((n, n), dtype=np.complex128)
    for j, drive in enumerate(signals):
        b = np.zeros(Z.shape[0], dtype=np.complex128)
        b[N + conductor_index[drive]] = 1.0
        b[N + conductor_index[0]] = -1.0
        x = lu_solve(lu, b)
        v = x[N:]
        for k, cond in enumerate(signals):
            zmat[k, j] = v[conductor_index[cond]] - v[conductor_index[0]]
    return np.real(zmat), np.imag(zmat) / omega
```
`mask_skin_depth` must preserve `conductor_ids` (it builds a new usermap from an rgb copy with blackened interiors; update it to pass `_codes`/`_conductor_ids` with the blackened pixels set to `-1`, mirroring Task 1's `replicate_edges` change).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_solvers/test_faraday_matrix.py tests/test_solvers/test_faraday.py tests/test_solvers/test_skin_depth.py -v`
Expected: all passed. The single-conductor equality holds to 1e-9 because both paths assemble the identical dense system for the same pixels and drive.

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/solvers/faraday.py src/lineforge/solvers/skin_depth.py tests/test_solvers/test_faraday_matrix.py
git commit -m "feat(solvers): N-conductor PEEC impedance matrix with a single LU factorisation"
```

---

### Task 7: N-port Touchstone export

**Files:**
- Modify: `src/lineforge/touchstone.py`
- Test: `tests/test_touchstone_nport.py`

**Interfaces:**
- Produces: `to_touchstone_nport(freqs_hz: np.ndarray, s: np.ndarray, path: str | Path, *, z_ref: float | Sequence[float] = 50.0, port_names: Sequence[str] | None = None, mixed_mode_order: Sequence[str] | None = None, version: Literal[1, 2] = 1, comment: str = "") -> Path`. `s` has shape (F, P, P). Version 1 writes through scikit-rf (`Network(frequency=Frequency.from_f(freqs, unit="Hz"), s=s, z0=z_ref).write_touchstone(..., form="ri")`), forcing the suffix `.s{P}p`. Version 2 writes the file directly: `[Version] 2.0`, `# Hz S RI R <z>`, `[Number of Ports] P`, `[Two-Port Data Order] 12_21` (P == 2 only), `[Reference] z1 ... zP`, optional `[Mixed-Mode Order] ...`, `[Number of Frequencies] F`, `[Network Data]`, rows of `f re im ...` in row-major port order, `[End]`.

- [ ] **Step 1: Write the failing test**

`tests/test_touchstone_nport.py`:
```python
"""N-port Touchstone export round-trips through scikit-rf and writes version 2 headers."""

from __future__ import annotations

import numpy as np
import pytest

skrf = pytest.importorskip("skrf")

from lineforge.touchstone import to_touchstone_nport


def _sample(ports: int = 4, n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    f = np.linspace(1e9, 5e9, n)
    rng = np.random.default_rng(1)
    s = (rng.normal(size=(n, ports, ports)) + 1j * rng.normal(size=(n, ports, ports))) * 0.1
    return f, s


def test_v1_roundtrip(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan", z_ref=50.0)
    assert path.suffix == ".s4p"
    net = skrf.Network(str(path))
    np.testing.assert_allclose(net.s, s, atol=1e-9)
    np.testing.assert_allclose(net.f, f)


def test_v2_header_and_mixed_mode(tmp_path) -> None:
    f, s = _sample()
    path = to_touchstone_nport(f, s, tmp_path / "chan.s4p", z_ref=[50, 50, 50, 50], mixed_mode_order=["D1,2", "C1,2", "D3,4", "C3,4"], version=2)
    text = path.read_text()
    assert "[Version] 2.0" in text
    assert "[Number of Ports] 4" in text
    assert "[Reference] 50 50 50 50" in text
    assert "[Mixed-Mode Order] D1,2 C1,2 D3,4 C3,4" in text
    assert "[Number of Frequencies] 5" in text
    assert text.strip().endswith("[End]")


def test_shape_validation(tmp_path) -> None:
    f, s = _sample()
    with pytest.raises(ValueError):
        to_touchstone_nport(f[:-1], s, tmp_path / "bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_touchstone_nport.py -v`
Expected: FAIL with `ImportError: cannot import name 'to_touchstone_nport'`

- [ ] **Step 3: Implement**

Append to `src/lineforge/touchstone.py`:
```python
def to_touchstone_nport(
    freqs_hz: np.ndarray,
    s: np.ndarray,
    path: str | Path,
    *,
    z_ref: float | Sequence[float] = 50.0,
    port_names: Sequence[str] | None = None,
    mixed_mode_order: Sequence[str] | None = None,
    version: Literal[1, 2] = 1,
    comment: str = "",
) -> Path:
    """Write an N-port S-parameter set as Touchstone 1.x (via scikit-rf) or 2.0 (native writer)."""
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    s = np.asarray(s, dtype=np.complex128)
    if s.ndim != 3 or s.shape[1] != s.shape[2] or s.shape[0] != len(freqs):
        raise ValueError(f"s must have shape (F, P, P) matching {len(freqs)} frequencies, got {s.shape}")
    ports = s.shape[1]
    zs = [float(z_ref)] * ports if isinstance(z_ref, (int, float)) else [float(z) for z in z_ref]
    if len(zs) != ports:
        raise ValueError("z_ref must be a scalar or one value per port")
    out = Path(path)
    if out.suffix.lower() != f".s{ports}p":
        out = out.with_suffix(f".s{ports}p")
    if version == 1:
        import skrf

        net = skrf.Network(frequency=skrf.Frequency.from_f(freqs, unit="Hz"), s=s, z0=np.array(zs), name=out.stem)
        if port_names:
            net.port_names = list(port_names)
        net.write_touchstone(str(out.with_suffix("")), form="ri", write_z0=False)
        return out
    lines = ["[Version] 2.0", f"# Hz S RI R {zs[0]:g}", f"[Number of Ports] {ports}"]
    if ports == 2:
        lines.append("[Two-Port Data Order] 12_21")
    lines.append("[Reference] " + " ".join(f"{z:g}" for z in zs))
    if mixed_mode_order:
        lines.append("[Mixed-Mode Order] " + " ".join(mixed_mode_order))
    if comment:
        lines.append(f"! {comment}")
    if port_names:
        lines.extend(f"! port {i + 1}: {name}" for i, name in enumerate(port_names))
    lines.append(f"[Number of Frequencies] {len(freqs)}")
    lines.append("[Network Data]")
    for fi, f in enumerate(freqs):
        row = [f"{f:.9e}"]
        for i in range(ports):
            for j in range(ports):
                row.append(f"{s[fi, i, j].real:.9e} {s[fi, i, j].imag:.9e}")
        lines.append(" ".join(row))
    lines.append("[End]")
    out.write_text("\n".join(lines) + "\n")
    return out
```
Add `from collections.abc import Sequence`, `from typing import Literal`, `import numpy as np` at the top and `"to_touchstone_nport"` to `__all__`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_touchstone_nport.py tests/test_touchstone.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/lineforge/touchstone.py tests/test_touchstone_nport.py
git commit -m "feat(touchstone): N-port export in Touchstone 1 and 2 with mixed-mode order"
```

---

### Task 8: Changelog, docs, full gate, pull request

- [ ] **Step 1: CHANGELOG and docs**

Under `## [Unreleased]` in `CHANGELOG.md`, `### Added`:
- `Usermap.from_labels`, `conductor_ids`, vectorised colour mapping (`geometry/usermap.py`).
- `DSParams`, `RoughnessSpec`, `MaterialRecord.er_complex` and pack I/O (`materials/database.py`, `materials/morecolors.py`).
- `solvers/roughness.py` (Hammerstad, Groisse, Huray, cannonball parameterisation).
- `solvers/mtl.py` (`solve_maxwell`, `rlgc_matrices`) and `solvers/wheeler.py` (`solve_wheeler_resistance`).
- `solvers/faraday.solve_impedance_matrix` with `SolverBudgetExceeded`.
- `touchstone.to_touchstone_nport`.
Add a short section to `docs/` (whichever page documents solvers) describing the N-conductor workflow: labels, `solve_maxwell`, `rlgc_matrices`, `solve_wheeler_resistance`, roughness.

- [ ] **Step 2: Full gate**

```bash
.venv/bin/ruff check . && .venv/bin/black --check . && .venv/bin/mypy src/lineforge
.venv/bin/pytest -q --cov=lineforge --cov-report=term-missing
```
Expected: clean, all passed, coverage above the configured floor and above 90 percent for the new modules.

- [ ] **Step 3: Commit and open the pull request**

```bash
git add CHANGELOG.md docs
git commit -m "docs: describe the N-conductor extraction workflow"
git push -u origin feature/mtl-nconductor
gh pr create --title "N-conductor Maxwell matrices, Wheeler losses, roughness and causal materials" --body "Adds label-based usermaps, solve_maxwell and rlgc_matrices, Wheeler incremental-inductance resistance with Hammerstad/Groisse/Huray roughness, Djordjevic-Sarkar material parameters, an N-conductor PEEC impedance matrix and N-port Touchstone export. Consumed by fieldforge's interconnect extraction. All existing tests unchanged."
```

## Self-review notes
- Spec coverage: every item of the "lineforge upstream additions" paragraph has a task (labels, materials, Maxwell, surface-current loss replaced by the equivalent Wheeler rule which needs no surface-current extraction, N-RHS impedance matrix with budget, roughness, N-port Touchstone).
- Type consistency: `conductor_ids` semantics (-1, 0, 1..N, -2) are identical in Tasks 1, 4, 5, 6; `MaxwellResult.C0` feeds both `rlgc_matrices` and `solve_wheeler_resistance`; `RoughnessSpec` from Task 2 is what Task 3 dispatches on and Task 5 accepts.
- The Wheeler rule replaces the spec's "surface current from potential" perturbation: it is the same physics (Pozar 2.7 shows the equivalence) with fewer moving parts, and it gives the mutual resistance terms the SI slice needs.
