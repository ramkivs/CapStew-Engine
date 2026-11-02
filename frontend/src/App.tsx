import { useCallback, useEffect, useState } from 'react';
import type { DecisionPayload, Holding, Policy, RunDiff, RunListItem, TaxYear } from './types';
import { engine } from './api/engine';
import { errMessage, isNotFound } from './api/client';
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

  // A NOT_FOUND on load simply means "nothing has been run yet" — that is a normal
  // empty state, not a fault. Anything else (engine down, 500, bad payload) is
  // surfaced, so the UI never shows a blank shell with no explanation.
  const noteLoadError = useCallback((e: unknown) => {
    if (!isNotFound(e)) setError(errMessage(e));
  }, []);

  const refreshRuns = useCallback(async () => {
    try { setRuns(await history.runs()); } catch (e) { noteLoadError(e); }
  }, [noteLoadError]);

  useEffect(() => {
    engine.health().then((h) => setEngineVersion(h.engine_version)).catch(noteLoadError);
    policy.get().then(setPolicyData).catch(noteLoadError);
    engine.decisions().then((p) => { setPayload(p); setTaxData(p.tax_year ?? null); })
      .catch(noteLoadError);
    refreshRuns();
  }, [refreshRuns, noteLoadError]);

  async function handleRunSample() {
    setRunning(true); setError(null);
    try {
      const p = await engine.runSample();
      setPayload(p); setPreview(null); setTaxData(p.tax_year ?? null);
      setView('decisions'); refreshRuns();
    } catch (e) { setError(errMessage(e)); }
    finally { setRunning(false); }
  }

  async function handleRunFiles(portfolio: File, screener: File, ledger: File, sold: File | null) {
    setRunning(true); setError(null);
    try {
      const form = new FormData();
      form.append('portfolio', portfolio);
      form.append('screener', screener);
      form.append('ledger', ledger);
      if (sold) form.append('sold', sold);
      const p = await engine.run(form);
      setPayload(p); setPreview(null); setTaxData(p.tax_year ?? null);
      setView('decisions'); refreshRuns();
    } catch (e) { setError(errMessage(e)); }
    finally { setRunning(false); }
  }

  async function handleWhatIf(weights: Record<string, number>) {
    try {
      const p = await engine.whatIf({ weights });
      setPreview(p);
    } catch (e) { setError(errMessage(e)); }
  }

  async function handleCommit(weights: Record<string, number>) {
    try {
      const p = await policy.put({ weights });
      setPolicyData(p);
      setError(null);
    } catch (e) { setError(errMessage(e)); }
  }

  async function handleDiff(runId: string) {
    try { setDiff(await history.diff(runId)); } catch (e) { setError(errMessage(e)); }
  }

  async function handleTaxRefresh() {
    try { setTaxData(await tax.tracker()); } catch (e) { if (!isNotFound(e)) setError(errMessage(e)); }
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
      </main>

      <HoldingDetail holding={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
