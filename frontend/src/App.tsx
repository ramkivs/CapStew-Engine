import { useCallback, useEffect, useState } from 'react';
import type { DecisionPayload, Holding, Policy, RunDiff, RunListItem, TaxYear } from './types';
import { engine } from './api/engine';
import { tax } from './api/tax';
import { history } from './api/history';
import { policy } from './api/policy';
import { Header, type ViewId } from './components/Header';
import { InputsView } from './components/InputsView';
import { DecisionsView } from './components/DecisionsView';
import { HoldingDetail } from './components/HoldingDetail';
import { TaxView } from './components/TaxView';
import { WeightsView } from './components/WeightsView';
import { HistoryView } from './components/HistoryView';
import { ActivityLogPanel } from './components/ActivityLogPanel';
import { log } from './activityLog';

export default function App() {
  const [view, setView] = useState<ViewId>('inputs');
  const [payload, setPayload] = useState<DecisionPayload | null>(null);
  const [preview, setPreview] = useState<DecisionPayload | null>(null);
  const [taxData, setTaxData] = useState<TaxYear | null>(null);
  const [policyData, setPolicyData] = useState<Policy | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [selected, setSelected] = useState<Holding | null>(null);
  const [engineVersion, setEngineVersion] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    try { setRuns(await history.runs()); } catch { /* no runs yet */ }
  }, []);

  useEffect(() => {
    engine.health().then((h) => setEngineVersion(h.engine_version)).catch(() => {});
    policy.get().then(setPolicyData).catch(() => {});
    engine.decisions().then((p) => { setPayload(p); setTaxData(p.tax_year ?? null); })
      .catch(() => { /* no run yet — expected */ });
    refreshRuns();
  }, [refreshRuns]);

  async function handleRunSample() {
    setRunning(true); setError(null);
    log('info', 'run requested — bundled demo fixtures');
    try {
      const p = await engine.runSample();
      setPayload(p); setPreview(null); setTaxData(p.tax_year ?? null);
      setView('decisions'); refreshRuns();
      log('ok', `run complete — run_id ${p.run_id} · ${p.holdings.length} holdings · as_of ${p.as_of}`);
    } catch (e) {
      setError((e as Error).message);
      log('fail', `run failed — ${(e as Error).message}`);
    }
    finally { setRunning(false); }
  }

  async function handleRunFiles(portfolio: File, screener: File, ledger: File, sold: File | null) {
    setRunning(true); setError(null);
    log('info', `run requested — ${portfolio.name} + ${screener.name} + ${ledger.name}${sold ? ` + ${sold.name}` : ''} → POST /api/v1/run`);
    try {
      const form = new FormData();
      form.append('portfolio', portfolio);
      form.append('screener', screener);
      form.append('ledger', ledger);
      if (sold) form.append('sold', sold);
      const p = await engine.run(form);
      setPayload(p); setPreview(null); setTaxData(p.tax_year ?? null);
      setView('decisions'); refreshRuns();
      log('ok', `run complete — run_id ${p.run_id} · ${p.holdings.length} holdings · as_of ${p.as_of} · content_hash ${p.content_hash.slice(0, 12)}…`);
    } catch (e) {
      setError((e as Error).message);
      log('fail', `run failed — ${(e as Error).message}`);
    }
    finally { setRunning(false); }
  }

  async function handleWhatIf(weights: Record<string, number>) {
    try {
      const p = await engine.whatIf({ weights });
      setPreview(p);
    } catch (e) { setError((e as Error).message); }
  }

  async function handleCommit(weights: Record<string, number>) {
    const p = await policy.put({ weights });
    setPolicyData(p);
  }

  async function handleDiff(runId: string) {
    setDiff(await history.diff(runId));
  }

  async function handleTaxRefresh() {
    try { setTaxData(await tax.tracker()); } catch { /* no realised data */ }
  }

  return (
    <div>
      <Header view={view} onView={setView} engine={engineVersion}
        asOf={payload?.as_of ?? null} running={running} />
      <main>
        {error ? (
          <div style={{ marginBottom: 14 }}>
            <div className="banner err">⚠ {error}</div>
          </div>
        ) : null}

        {view === 'inputs' ? (
          <InputsView running={running} onRunSample={handleRunSample} onRunFiles={handleRunFiles} />
        ) : null}

        {view === 'decisions' && payload ? (
          <DecisionsView payload={payload} preview={preview}
            onSelect={setSelected} onClearPreview={() => setPreview(null)} />
        ) : view === 'decisions' ? (
          <div className="banner warn">No run yet — go to <b>Inputs &amp; Policy</b> and run the engine.</div>
        ) : null}

        {view === 'weights' ? (
          <WeightsView policy={policyData} previewActive={preview !== null}
            onWhatIf={handleWhatIf} onCommit={handleCommit} />
        ) : null}

        {view === 'tax' ? <TaxView payload={payload} tax={taxData} /> : null}

        {view === 'history' ? (
          <HistoryView runs={runs} diff={diff} onDiff={handleDiff} onRefresh={refreshRuns} />
        ) : null}

        <ActivityLogPanel />
      </main>

      <HoldingDetail holding={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
