"""Capital Steward Determinism Guarantee (Freeze §8).

content_hash is the sha256 of the canonical JSON of the payload minus the
run_id — same inputs + same policy + same engine version ⇒ identical hash.
"""
import hashlib
import json


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(payload_dict) -> str:
    return hashlib.sha256(canonical_json(payload_dict).encode("utf-8")).hexdigest()
