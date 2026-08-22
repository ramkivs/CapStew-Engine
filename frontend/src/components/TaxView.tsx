import type { DecisionPayload, TaxYear } from '../types';
import { Bar, Banner, inr, num } from './ui';

export function TaxView({ payload, tax }: { payload: DecisionPayload | null; tax: TaxYear | null }) {
  const t = tax ?? payload?.tax_year ?? null;

  if (!t) {
    return (
      <div>
        <Banner kind="warn">
          No realised-gains data. Run with a <b>sold-transactions ledger</b> (or the bundled demo)
          to compute the tax year. Until then the ₹1.25L headroom is provisional.
        </Banner>
      </div>
    );
  }

  const s = t.summary;
  // Display scale derived ENTIRELY from backend-supplied numbers — the browser
  // never carries a tax constant (UAT-06: presentation formatting only).
  const scale = Math.max(
    s.exemption.used + s.exemption.headroom,
    s.gross.ltcg, s.gross.stcg, s.gross.ltcl, s.gross.stcl, 1,
  );

  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Tax-year gain budget <span className="tag">FY {s.fy ?? '2026-27'}</span></h3>
        <Budget label="LTCG realised" value={s.gross.ltcg} color="var(--green)" max={scale} />
        <Budget label="STCG realised" value={s.gross.stcg} color="var(--orange)" max={scale} />
        <Budget label="LTCG headroom" value={s.exemption.headroom} color="var(--green)" max={scale} />
        <Budget label="STCL harvestable" value={s.gross.stcl} color="var(--blue)" max={scale} />
        <div className="note" style={{ marginTop: 8 }}>
          Total tax: <b style={{ color: 'var(--red)' }}>{inr(s.tax.total)}</b> ·
          LTCG {inr(s.tax.ltcg)} (12.5% above ₹1.25L) + STCG {inr(s.tax.stcg)} (20%)
        </div>
      </div>

      <div className="card">
        <h3>Set-off & carry-forward <span className="tag">S.74</span></h3>
        <div className="drivers">
          <li><b>Order:</b> LTCL → LTCG · STCL → STCG then LTCG · carried losses (oldest first, 8y lapse).</li>
          <li>LTCL used: <b>{inr(s.set_off.ltcl_used)}</b></li>
          <li>STCL vs STCG: <b>{inr(s.set_off.stcl_used_against_stcg)}</b></li>
          <li>STCL vs LTCG: <b>{inr(s.set_off.stcl_used_against_ltcg)}</b></li>
          <li className="warn">
            Carry-forward out — LTCL: {fmtCF(s.carry_forward_out.ltcl)} · STCL: {fmtCF(s.carry_forward_out.stcl)}
          </li>
          <li>No wash-sale rule in India → sell &amp; rebuy to reset cost basis is legal (GAAR caveat).</li>
          <li className="warn">Never defer a <i>stretched</i> position just for LTCG — 7.5pp tax vs drawdown risk.</li>
        </div>
      </div>

      <div className="card">
        <h3>Realised transactions <span className="tag">FIFO-matched</span></h3>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr><th>Instrument</th><th>Lot</th><th>Sell date</th><th className="num">Qty</th>
                <th className="num">Gain</th><th className="num">Held</th><th>Class</th></tr>
            </thead>
            <tbody>
              {t.realized.map((r, i) => (
                <tr key={i}>
                  <td className="tick">{r.instrument}</td>
                  <td>#{r.lot_id}</td>
                  <td>{r.sell_date}</td>
                  <td className="num">{r.qty}</td>
                  <td className={`num ${r.gain >= 0 ? 'up' : 'down'}`}>{r.gain >= 0 ? '+' : ''}{num(r.gain)}</td>
                  <td className="num">{r.holding_days}d</td>
                  <td><Tag type={r.type} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Open positions — unrealised split</h3>
        {Object.entries(t.open_positions).map(([inst, split]) => (
          <div key={inst} className="cfg">
            <div className="lbl"><b style={{ fontFamily: 'var(--mono)', color: 'var(--blue)' }}>{inst}</b></div>
            <div></div>
            <div className="val" style={{ fontSize: 11 }}>
              LTCG {num(split.ltcg)} · STCG {num(split.stcg)} · LTCL {num(split.ltcl)} · STCL {num(split.stcl)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Budget({ label, value, color, max }: { label: string; value: number; color: string; max: number }) {
  return (
    <div className="cfg">
      <div className="lbl"><b>{label}</b><small>FY 2026-27</small></div>
      <Bar value={(value / max) * 100} color={color} />
      <div className="val">{inr(value)}</div>
    </div>
  );
}

function fmtCF(cf: [number, number][]): string {
  if (!cf.length) return 'none';
  return cf.map(([amt, age]) => `${inr(amt)} (age ${age})`).join(', ');
}

function Tag({ type }: { type: string }) {
  const color = type === 'LTCG' ? 'var(--green)' : type === 'STCG' ? 'var(--orange)' : 'var(--red)';
  return <span className="tagchip" style={{ color, border: `1px solid ${color}44` }}>{type}</span>;
}
