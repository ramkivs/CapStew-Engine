"""Policy keys must not be misleading.

F-1: `policy/policy.yaml` is presented to the user as the live configuration
surface, but several of its keys are read by nothing in `app/`. Editing one of
those changes no behaviour, which is exactly the kind of misleading
configuration the personal-use brief says not to retain.

The chosen remedy is documentation rather than deletion: the keys mirror signed
decisions D-05…D-14 of the Methodology Freeze, so removing them would make this
file a worse serialization of that policy. Instead every unread key is tagged
`[NOT CONSUMED]` inline, and these tests fail if the tags ever drift from what
the code actually reads — so the note cannot quietly become a lie.
"""
import re
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = ROOT / "policy" / "policy.yaml"


def _leaf_keys(node, prefix=""):
    for k, v in node.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _leaf_keys(v, key + ".")
        else:
            yield key


def _tagged_not_consumed():
    """Leaf keys carrying an inline `# [NOT CONSUMED]` comment."""
    tagged, stack = set(), []          # stack of parent keys, by indent depth
    for line in POLICY.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        m = re.match(r"([A-Za-z_][\w]*):", line.strip())
        if not m:
            continue
        key = m.group(1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        leaf = ".".join([s[1] for s in stack] + [key])
        if "[NOT CONSUMED]" in line:
            tagged.add(leaf)
        if isinstance(yaml.safe_load(line.strip()), dict):
            stack.append((indent, key))
    return tagged


def _app_source_excluding_allowlist():
    """app/*.py with the POLICY_KEYS allowlist blanked out.

    The allowlist mentions every key by name; counting it would make every key
    look live and hide exactly the drift this module exists to catch.
    """
    out = {}
    for path in sorted((ROOT / "app").glob("*.py")):
        text = path.read_text()
        if path.name == "policy.py":
            text = re.sub(r"POLICY_KEYS = frozenset\(\{.*?\}\)", "", text, flags=re.S)
        out[path.name] = text
    return out


def _actually_unread():
    src = _app_source_excluding_allowlist()
    unread = set()
    for leaf in _leaf_keys(yaml.safe_load(POLICY.read_text())):
        pat = re.compile(r"['\"]" + re.escape(leaf.split(".")[-1]) + r"['\"]")
        if not any(pat.search(text) for text in src.values()):
            unread.add(leaf)
    return unread


def test_policy_file_is_valid_and_versioned():
    data = yaml.safe_load(POLICY.read_text())
    assert data["policy_version"] == 1
    assert "effective_from" in data


def test_not_consumed_tags_match_reality():
    """The documented set of inert keys is exactly the set the code never reads."""
    tagged = _tagged_not_consumed()
    unread = _actually_unread()

    assert tagged <= set(_leaf_keys(yaml.safe_load(POLICY.read_text()))), \
        f"tagged keys that are not in policy.yaml: {sorted(tagged - set(_leaf_keys(yaml.safe_load(POLICY.read_text()))))}"
    assert unread == tagged, (
        "policy.yaml documentation drifted from the code. "
        f"Newly dead (add a [NOT CONSUMED] tag): {sorted(unread - tagged)}. "
        f"Tagged but now live (remove the tag): {sorted(tagged - unread)}."
    )


@pytest.mark.parametrize("key", sorted(_actually_unread()))
def test_every_inert_key_is_tagged_in_the_file(key):
    """No silently inert key: an unread key must say so where a user will see it."""
    text = POLICY.read_text()
    leaf = key.split(".")[-1]
    lines = [ln for ln in text.splitlines() if re.match(rf"\s*{re.escape(leaf)}:", ln)]
    assert lines, f"{key}: declared in a block but not found as a top-level line"
    assert any("[NOT CONSUMED]" in ln for ln in lines), (
        f"{key} is read by nothing in app/ but policy.yaml does not say so"
    )


def test_weights_still_sum_to_100():
    data = yaml.safe_load(POLICY.read_text())
    assert sum(data["weights"].values()) == 100


def test_bands_and_review_cadence_are_actually_consumed():
    """Regression: these were dead config until wired into the engine."""
    unread = _actually_unread()
    for key in ("hold_max", "watch_max", "trim_max",
                "hold_high_conf_days", "hold_low_conf_days",
                "action_verify_days", "gate_fired_days"):
        assert key not in unread, f"{key} has gone unread again"
