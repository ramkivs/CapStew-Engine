"""Policy validation boundaries (Freeze §10) + no-mutation guarantee."""
from pathlib import Path

import yaml

from app.policy import load_policy, validate_policy

POLICY = load_policy()
SIGNED = Path(__file__).resolve().parent.parent / "policy" / "policy.yaml"


def test_weights_80_80_valid():
    p = {**POLICY, "weights": {"position_sizing": 80, "valuation_stretch": 80,
                               "quality_drift": 0, "tax_efficiency": 0,
                               "opportunity_cost": 0, "technical_regime": 0}}
    assert validate_policy(p) == []


def test_weights_all_zero_invalid():
    p = {**POLICY, "weights": {k: 0 for k in POLICY["weights"]}}
    assert validate_policy(p)


def test_negative_weight_invalid():
    p = {**POLICY, "weights": {**POLICY["weights"], "position_sizing": -1}}
    assert validate_policy(p)


def test_bands_contiguity_checked():
    p = {**POLICY, "bands": {"hold_max": 60, "watch_max": 40, "trim_max": 90}}
    assert validate_policy(p)


def test_signed_policy_is_consistent():
    assert validate_policy(POLICY) == []


def test_put_policy_invalid_does_not_mutate_file(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.policy as pol

    tmp_policy = tmp_path / "policy.yaml"
    tmp_policy.write_text(yaml.safe_dump(POLICY))
    monkeypatch.setattr(pol, "POLICY_PATH", tmp_policy)

    before = tmp_policy.read_bytes()
    client = TestClient(app)
    r = client.put("/api/v1/policy", json={"weights": {k: 0 for k in POLICY["weights"]}})
    assert r.status_code == 422
    assert tmp_policy.read_bytes() == before


def test_put_policy_valid_commits_new_version(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.policy as pol

    tmp_policy = tmp_path / "policy.yaml"
    tmp_policy.write_text(yaml.safe_dump(POLICY))
    monkeypatch.setattr(pol, "POLICY_PATH", tmp_policy)

    client = TestClient(app)
    r = client.put("/api/v1/policy", json={"weights": {**POLICY["weights"], "technical_regime": 10}})
    assert r.status_code == 200
    assert r.json()["policy_version"] == POLICY["policy_version"] + 1
    assert yaml.safe_load(tmp_policy.read_text())["weights"]["technical_regime"] == 10
