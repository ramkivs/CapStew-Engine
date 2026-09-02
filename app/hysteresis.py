"""Decision hysteresis (Freeze §6).

Asymmetric band transitions + N=2 persistence over distinct as_of dates.
Stage-1 gates bypass hysteresis (the caller uses bypass() for gate decisions).
"""


class Hysteresis:
    def __init__(self):
        self.state = {}

    @staticmethod
    def transition(prev_decision, score):
        if prev_decision == "HOLD":
            return "WATCH" if score >= 31 else "HOLD"
        if prev_decision == "WATCH":
            if score >= 56:
                return "TRIM"
            if score < 28:
                return "HOLD"
            return "WATCH"
        if prev_decision == "TRIM":
            if score >= 76:
                return "HARVEST"
            if score < 52:
                return "WATCH"
            return "TRIM"
        if prev_decision == "HARVEST":
            if score < 72:
                return "TRIM"
            return "HARVEST"
        return "HOLD"

    def get_prev(self, instrument):
        s = self.state.get(instrument)
        if not s:
            return None
        prev = {"decision": s["decision"], "composite_score": s["score"], "as_of": s["as_of"]}
        # Freeze §6 N=2: carry the confirmation counter when one is open. Omitted
        # when null so the no-history/golden deterministic output is unchanged.
        pending = s.get("pending")
        if pending:
            prev["pending"] = {"band": pending["band"], "count": pending["count"]}
        return prev

    def apply(self, instrument, raw_band, score, as_of):
        cur = self.state.get(instrument)
        if cur is None or cur["decision"] == "EXIT":
            self.state[instrument] = {"decision": raw_band, "score": score,
                                      "as_of": as_of.isoformat(), "pending": None}
            return raw_band

        target = self.transition(cur["decision"], score)
        if target == cur["decision"]:
            cur["pending"] = None
            cur["score"], cur["as_of"] = score, as_of.isoformat()
            return target

        new_asof = as_of.isoformat() != cur["as_of"]
        pending = cur.get("pending")
        if pending and pending["band"] == target and new_asof:
            pending["count"] += 1
        else:
            pending = {"band": target, "count": 1}
        cur["pending"] = pending
        cur["as_of"], cur["score"] = as_of.isoformat(), score

        if pending["count"] >= 2:
            cur["decision"] = target
            cur["pending"] = None
            return target
        return cur["decision"]  # persist current decision (N=2 not yet met)

    def bypass(self, instrument, decision, score, as_of):
        """Gate decisions override hysteresis immediately."""
        self.state[instrument] = {"decision": decision, "score": score,
                                  "as_of": as_of.isoformat(), "pending": None}
        return decision

    def seed(self, instrument, decision, score, as_of, pending=None):
        """Initialize state from a PERSISTED previous run (Freeze §6 / audit B).

        `pending` is the optional N=2 confirmation counter carried by the
        persisted `previous_run`. Restoring it is what lets the two consecutive
        distinct-`as_of` observations required by Freeze §6 accumulate across
        separate runs / process restarts instead of restarting at 1 every time.
        Legacy records carrying only decision/composite_score/as_of restore as
        `pending=None`, which is exactly the pre-existing behaviour.
        """
        restored = None
        if isinstance(pending, dict):
            band = pending.get("band")
            count = pending.get("count")
            if (band in ("HOLD", "WATCH", "TRIM", "HARVEST")
                    and isinstance(count, int) and not isinstance(count, bool)
                    and count >= 1):
                restored = {"band": band, "count": count}
        self.state[instrument] = {"decision": decision, "score": score,
                                  "as_of": as_of, "pending": restored}
