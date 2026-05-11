"""End-to-end tests for the atlc3-gui FastAPI backend (C1 scaffolding)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state import reset_state


@pytest.fixture(autouse=True)
async def _reset_each_test() -> None:
    await reset_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_health_returns_versions(self, client: TestClient) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "atlc3_version" in body
        assert "atlc3_gui_version" in body


class TestGeometryRoutes:
    def test_list_geometries(self, client: TestClient) -> None:
        r = client.get("/api/geometries")
        assert r.status_code == 200
        body = r.json()
        names = [g["type"] for g in body["geometries"]]
        # Spot-check a few we know exist
        assert "microstrip" in names
        assert "stripline_asymmetric" in names
        assert "three_wire" in names

    def test_describe_known_geometry(self, client: TestClient) -> None:
        r = client.get("/api/geometries/microstrip")
        assert r.status_code == 200
        schema = r.json()
        # Pydantic model_json_schema includes 'properties' with W, H, T, er
        props = schema["properties"]
        for required in ("W", "H", "T", "er"):
            assert required in props

    def test_describe_unknown_geometry_404(self, client: TestClient) -> None:
        r = client.get("/api/geometries/nonexistent")
        assert r.status_code == 404
        assert "valid_types" in r.json()["detail"]

    def test_schema_export(self, client: TestClient) -> None:
        r = client.get("/api/geometries/schema")
        assert r.status_code == 200
        schema = r.json()
        assert "oneOf" in schema  # discriminated union


class TestSolveRoutes:
    def test_calculate_microstrip(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["_kind"] == "TLineResult"
        assert 40 < body["z0"] < 60  # 6mil/4mil FR4 microstrip is ~50Ω

    def test_calculate_invalid_geometry_400(self, client: TestClient) -> None:
        r = client.post("/api/solve/calculate", json={"geometry": {"type": "fictional_geometry"}})
        assert r.status_code == 400

    def test_calculate_drops_extraneous_empty_fields(self, client: TestClient) -> None:
        """DB1: form sends all common fields including empties → backend filters
        them before atlc3.from_dict (which is extra='forbid'). The visible
        L3 SIG1 case (asymmetric stripline with H='' from the form's H input).
        """
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "stripline_asymmetric",
                    "W": "3.4mil",
                    "T": "0.689mil",
                    "H1": "3.5mil",
                    "H2": "5.3mil",
                    "er": 4.0,
                    "H": "",  # extra field that would normally trigger extra=forbid
                    "S": "",  # also extraneous
                    "B": "",
                },
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["_kind"] == "TLineResult"
        assert 40 < body["z0"] < 55

    def test_calculate_drops_unknown_keys_for_known_type(self, client: TestClient) -> None:
        """An unrecognized field on a known geometry should be silently dropped."""
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                    "made_up_field": "0.5mil",
                },
            },
        )
        assert r.status_code == 200

    def test_error_message_strips_pydantic_url(self, client: TestClient) -> None:
        """A genuinely-bad geometry should return a 400 whose detail does NOT
        contain the Pydantic documentation URL."""
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "0",  # gt=0 → ValidationError
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                }
            },
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "https://" not in detail, f"detail still has Pydantic URL: {detail}"

    def test_calculate_frequency_as_string_with_unit(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                    "tan_delta": 0.02,
                },
                "frequency": "1GHz",
            },
        )
        assert r.status_code == 200
        body = r.json()
        # parse_frequency('1GHz') == 1e9 → frequency_hz used by solver
        assert body.get("frequency_hz") == pytest.approx(1e9)

    def test_calculate_frequency_as_float(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                    "tan_delta": 0.02,
                },
                "frequency": 1e9,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("frequency_hz") == pytest.approx(1e9)

    def test_calculate_missing_required_field_friendly_error(self, client: TestClient) -> None:
        """DB2: empty/missing required Length triggers a clean 'Field W is
        required' instead of a Pydantic-internal ValueError."""
        r = client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "",  # empty → cleaned out → Pydantic reports as required
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
            },
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        # User-friendly: mentions which field, no Pydantic URL
        assert "W" in detail
        assert "https://" not in detail


class TestTargetZ0BoundsValidation:
    """DB2: bounds must parse + low<high."""

    def test_reversed_bounds_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/target-z0",
            json={
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["30mil", "0.5mil"],  # reversed
            },
        )
        assert r.status_code == 422  # pydantic body-validation error
        assert "lower bound must be less than upper" in r.text

    def test_unparseable_bounds_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/target-z0",
            json={
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["wide", "narrow"],  # garbage
            },
        )
        assert r.status_code == 422
        assert "must be a positive length" in r.text

    def test_negative_bound_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/target-z0",
            json={
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["-1mil", "30mil"],
            },
        )
        assert r.status_code == 422


class TestSweepParameterValidation:
    """DB2: sweep parameter must be 'frequency' or a real field on the geom."""

    def test_typo_parameter_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/sweep",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "parameter": "frequnecy",  # typo
                "values": [1e8, 1e9],
            },
        )
        assert r.status_code == 400
        assert "frequnecy" in r.json()["detail"]
        assert "frequency" in r.json()["detail"]  # listed as valid choice

    def test_wrong_field_for_geometry_rejected(self, client: TestClient) -> None:
        """stripline_asymmetric has H1/H2, NOT H. Sweeping over 'H' should
        list H1 / H2 as valid choices instead."""
        r = client.post(
            "/api/solve/sweep",
            json={
                "geometry": {
                    "type": "stripline_asymmetric",
                    "W": "5mil",
                    "T": "1.4mil",
                    "H1": "6mil",
                    "H2": "8mil",
                    "er": 4.4,
                },
                "parameter": "H",
                "values": [4e-5, 5e-5],
            },
        )
        assert r.status_code == 400
        assert "H1" in r.json()["detail"]
        assert "H2" in r.json()["detail"]

    def test_target_z0(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/target-z0",
            json={
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["0.5mil", "30mil"],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert abs(body["z0_achieved"] - 50.0) < 0.1

    def test_sweep_frequency(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/sweep",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "parameter": "frequency",
                "values": [1e8, 1e9, 1e10],
                "solver": "analytical",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["points"]) == 3
        for p in body["points"]:
            assert p["params"]["frequency"] in (1e8, 1e9, 1e10)
            assert p["result"] is not None


class TestSweepTouchstone:
    """E4: sweep with touchstone_out returns the .s2p content inline."""

    def test_touchstone_content_inlined(self, client: TestClient) -> None:
        r = client.post(
            "/api/solve/sweep",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                    "tan_delta": 0.02,
                },
                "parameter": "frequency",
                "values": [1e8, 1e9, 1e10],
                "solver": "analytical",
                "touchstone_out": "trace.s2p",
                "line_length": "1in",
                "z_ref": 50.0,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        ts = body["touchstone"]
        assert ts["filename"] == "trace.s2p"
        assert ts["n_ports"] == 2
        # The content should be a Touchstone v1 RI file with three frequency rows
        assert ts["content"].lstrip().startswith("!")  # comment header
        assert "S 50" in ts["content"] or "Hz S RI" in ts["content"]


class TestStateRoutes:
    def test_initial_state(self, client: TestClient) -> None:
        r = client.get("/api/state")
        assert r.status_code == 200
        s = r.json()
        assert s["geometry"] is None
        assert s["last_result"] is None
        assert s["chat_history"] == []

    def test_state_updated_after_calculate(self, client: TestClient) -> None:
        client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
            },
        )
        s = client.get("/api/state").json()
        assert s["geometry"] is not None
        assert s["geometry"]["type"] == "microstrip"
        assert s["last_result"]["_kind"] == "TLineResult"

    def test_reset_clears_state(self, client: TestClient) -> None:
        client.post(
            "/api/solve/calculate",
            json={
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
            },
        )
        r = client.post("/api/state/reset")
        assert r.status_code == 200
        s = client.get("/api/state").json()
        assert s["geometry"] is None
        assert s["last_result"] is None


class TestChatWebSocket:
    def test_chat_stub_echoes_message(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "Hello"}))
            reply = ws.receive_json()
            assert reply["role"] == "assistant"
            assert "Hello" in reply["content"]  # stub echoes content
            assert "(stub)" in reply["content"]
            assert reply["stream"] is False

    def test_chat_records_history(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "First message"}))
            ws.receive_json()
        s = client.get("/api/state").json()
        history = s["chat_history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "First message"
        assert history[1]["role"] == "assistant"

    def test_chat_reset_clears_state(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "Hi"}))
            ws.receive_json()
            ws.send_text(json.dumps({"role": "system", "type": "reset"}))
            reset_msg = ws.receive_json()
            assert reset_msg["role"] == "state_delta"
            assert reset_msg["patch"]["reset"] is True
        s = client.get("/api/state").json()
        assert s["chat_history"] == []

    def test_chat_rejects_unknown_role(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "robot", "content": "..."}))
            reply = ws.receive_json()
            assert reply["role"] == "error"
            assert "unsupported role" in reply["content"]

    def test_chat_rejects_bad_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text("not json {")
            reply = ws.receive_json()
            assert reply["role"] == "error"


class TestProgressWebSocket:
    def test_progress_subscribe_and_finalize(self, client: TestClient) -> None:
        """Open /ws/progress/<task>, push a progress and a result message
        from the backend; the WebSocket forwards both then closes."""
        import asyncio

        from app.ws_progress import send_progress

        with client.websocket_connect("/ws/progress/tsk-123") as ws:
            # Push from another thread/loop
            asyncio.get_event_loop().run_until_complete(
                send_progress("tsk-123", {"type": "progress", "stage": "laplace", "frac": 0.5})
            )
            asyncio.get_event_loop().run_until_complete(
                send_progress("tsk-123", {"type": "result", "result": {"z0": 50.0}})
            )
            m1 = ws.receive_json()
            assert m1["type"] == "progress"
            assert m1["frac"] == 0.5
            m2 = ws.receive_json()
            assert m2["type"] == "result"
            assert m2["result"]["z0"] == 50.0
