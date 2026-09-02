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
        return {"decision": s["decision"], "composite_score": s["score"], "as_of": s["as_of"]}

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

    def seed(self, instrument, decision, score, as_of):
        """Initialize state from a PERSISTED previous run (Freeze §6 / audit B)."""
        self.state[instrument] = {"decision": decision, "score": score,
                                  "as_of": as_of, "pending": None}
