"""Policy validation boundaries (Freeze §10) + no-mutation guarantee.

The signed `policy/policy.yaml` is shipped, tracked and never written by the
running application. User commits land in `data/policy.yaml` (app-managed),
which is redirected to tmp_path by the autouse fixture in conftest.py.
"""
from pathlib import Path

import yaml

from app.policy import load_policy, validate_policy

POLICY = load_policy()
SIGNED = Path(__file__).resolve().parent.parent / "policy" / "policy.yaml"


def _weights(**over):
    w = {**POLICY["weights"], **over}
    # keep D-09 intact: category weights sum to exactly 100
    w["position_sizing"] = 100 - sum(v for k, v in w.items() if k != "position_sizing")
    return w


def test_weights_sum_100_valid():
    p = {**POLICY, "weights": _weights(valuation_stretch=50, quality_drift=0,
                                       tax_efficiency=0, opportunity_cost=0,
                                       technical_regime=0)}
    assert sum(p["weights"].values()) == 100
    assert validate_policy(p) == []


def test_weights_must_sum_to_100():
    """D-09: a weight set that does not total 100 is rejected, not silently accepted."""
    p = {**POLICY, "weights": {"position_sizing": 80, "valuation_stretch": 80,
                               "quality_drift": 0, "tax_efficiency": 0,
                               "opportunity_cost": 0, "technical_regime": 0}}
    errors = validate_policy(p)
    assert errors and "must sum to 100" in errors[0]


def test_weights_all_zero_invalid():
    p = {**POLICY, "weights": {k: 0 for k in POLICY["weights"]}}
    assert validate_policy(p)


def test_negative_weight_invalid():
    p = {**POLICY, "weights": {**POLICY["weights"], "position_sizing": -1}}
    assert validate_policy(p)


def test_bands_contiguity_checked():
    p = {**POLICY, "bands": {"hold_max": 60, "watch_max": 40, "trim_max": 90}}
    assert validate_policy(p)


def test_unknown_keys_rejected():
    """A PUT cannot inject arbitrary keys into the signed policy."""
    p = {**POLICY, "EVIL_KEY": "injected"}
    errors = validate_policy(p)
    assert errors and "unknown policy keys" in errors[0]


def test_signed_policy_is_consistent():
    assert validate_policy(POLICY) == []


def test_put_policy_invalid_does_not_mutate_file(tmp_path, monkeypatch):
    import app.config as cfg
    from app.main import app
    from fastapi.testclient import TestClient

    user_policy = tmp_path / "user-policy.yaml"
    user_policy.write_text(yaml.safe_dump(POLICY))
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", user_policy)

    signed_before = SIGNED.read_bytes()
    user_before = user_policy.read_bytes()
    client = TestClient(app)
    r = client.put("/api/v1/policy", json={"weights": {k: 0 for k in POLICY["weights"]}})
    assert r.status_code == 422
    assert user_policy.read_bytes() == user_before
    assert SIGNED.read_bytes() == signed_before


def test_put_policy_valid_commits_new_version(tmp_path, monkeypatch):
    import app.config as cfg
    from app.main import app
    from fastapi.testclient import TestClient

    user_policy = tmp_path / "user-policy.yaml"
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", user_policy)
    assert not user_policy.exists()

    signed_before = SIGNED.read_bytes()
    client = TestClient(app)
    r = client.put("/api/v1/policy",
                   json={"weights": _weights(technical_regime=10)})
    assert r.status_code == 200, r.text
    assert r.json()["policy_version"] == POLICY["policy_version"] + 1
    assert yaml.safe_load(user_policy.read_text())["weights"]["technical_regime"] == 10
    # the shipped signed file is never written by the running application
    assert SIGNED.read_bytes() == signed_before


def test_put_policy_rejects_unknown_key(tmp_path, monkeypatch):
    import app.config as cfg
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "user-policy.yaml")
    r = TestClient(app).put("/api/v1/policy", json={"EVIL_KEY": "injected"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "POLICY_INVALID"
    assert not (tmp_path / "user-policy.yaml").exists()


def test_reset_policy_restores_shipped_defaults(tmp_path, monkeypatch):
    import app.config as cfg
    from app.main import app
    from fastapi.testclient import TestClient

    user_policy = tmp_path / "user-policy.yaml"
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", user_policy)
    client = TestClient(app)
    assert client.put("/api/v1/policy",
                      json={"weights": _weights(technical_regime=10)}).status_code == 200
    assert client.get("/api/v1/policy").json()["weights"]["technical_regime"] == 10

    r = client.post("/api/v1/policy/reset")
    assert r.status_code == 200
    assert not user_policy.exists()
    assert client.get("/api/v1/policy").json()["weights"] == POLICY["weights"]
