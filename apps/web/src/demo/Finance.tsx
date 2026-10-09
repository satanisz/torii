// SPEC-0019 F06: local, immutable financial analyses; no production approval semantics.
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { demoRequest } from './api';
import { Empty, Field } from './ui';
import type { FinanceMonth, FinanceReport, FinanceRun, FinanceSide } from './finance-types';
import './finance.css';

const amount = new Intl.NumberFormat('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat('pl-PL', { style: 'percent', maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Europe/Warsaw' });
const money = (value: number) => `${amount.format(value === 0 ? 0 : value)} PLN`;
const signed = (value: number) => `${value > 0 ? '+' : ''}${money(value)}`;
const shock = (value: number) => `${value > 0 ? '+' : ''}${String(value)} pb`;
const side = (value: FinanceSide) => value === 'asset' ? 'Aktywa' : 'Pasywa';
const statuses = { queued: 'W kolejce', running: 'W trakcie', succeeded: 'Obliczono', failed: 'Niepowodzenie' };
const isActive = (run: FinanceRun) => run.status === 'queued' || run.status === 'running';
const message = (error: unknown) => error instanceof Error ? error.message : 'Nie udało się pobrać analizy.';

/** The keyed boundary also cancels pending requests on a project change. */
export function Finance({ projectId }: { projectId: string }) {
  return <FinanceProject key={projectId} projectId={projectId} />;
}

function FinanceProject({ projectId }: { projectId: string }) {
  const [runs, setRuns] = useState<FinanceRun[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [readError, setReadError] = useState('');
  const [writeError, setWriteError] = useState('');
  const [shockValue, setShockValue] = useState('100');
  const [betaValue, setBetaValue] = useState('0.35');
  const [injectIssues, setInjectIssues] = useState(false);
  const readController = useRef<AbortController | null>(null);
  const writeController = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  const path = `/projects/${encodeURIComponent(projectId)}/finance/runs`;
  const selected = runs.find(run => run.id === selectedId) ?? runs[0];
  const active = runs.some(isActive);

  const refresh = useCallback(async () => {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    setLoading(true);
    try {
      const next = await demoRequest<FinanceRun[]>(path, undefined, controller.signal);
      if (!controller.signal.aborted) {
        setRuns(next.filter(run => run.project_id === projectId));
        setLoaded(true);
        setReadError('');
      }
    } catch (error) {
      if (!controller.signal.aborted) setReadError(message(error));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [path, projectId]);

  useEffect(() => {
    void refresh();
    return () => { readController.current?.abort(); writeController.current?.abort(); };
  }, [refresh]);

  useEffect(() => {
    if (!active || saving) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await refresh();
      if (!cancelled) timer = setTimeout(() => { void poll(); }, 1500);
    }
    timer = setTimeout(() => { void poll(); }, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active, saving, refresh]);

  async function submit() {
    if (submitting.current || active || !loaded || readError) return;
    setWriteError('');
    const shockBps = Number(shockValue);
    const depositBeta = Number(betaValue);
    if (!shockValue.trim() || !Number.isInteger(shockBps) || shockBps < -300 || shockBps > 300) {
      setWriteError('Zmiana stóp musi być liczbą całkowitą od -300 do 300 pb.');
      return;
    }
    if (!betaValue.trim() || !Number.isFinite(depositBeta) || depositBeta < 0 || depositBeta > 1) {
      setWriteError('Beta depozytów musi być liczbą od 0 do 1.');
      return;
    }
    submitting.current = true;
    readController.current?.abort();
    setLoading(false);
    setSaving(true);
    const controller = new AbortController();
    writeController.current = controller;
    try {
      const created = await demoRequest<FinanceRun>(path, { shock_bps: shockBps, deposit_beta: depositBeta, inject_issues: injectIssues }, controller.signal);
      if (controller.signal.aborted) return;
      setRuns(previous => [created, ...previous.filter(run => run.id !== created.id)]);
      setSelectedId(created.id);
      void refresh();
    } catch (error) {
      if (!controller.signal.aborted) setWriteError(message(error));
    } finally {
      submitting.current = false;
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  return <div className="finance-workbench">
    <header className="finance-intro">
      <div><p className="eyebrow">Finanse banku · lokalne laboratorium</p><h2>Od księgi i portfela do scenariusza NII</h2><p>NII to przychody odsetkowe minus koszty odsetkowe — nie zysk netto banku.</p></div>
      <span className="finance-tag">Dane syntetyczne · PLN</span>
    </header>

    <form className="panel finance-form" aria-label="Parametry scenariusza" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <div className="finance-form-context"><p className="eyebrow">01 / Scenariusz</p><h3>Jak zmiana stóp wpływa na wynik?</h3><p className="hint">Porównaj bazę ze zmianą stóp na 12 miesięcy: październik 2026 – wrzesień 2027. Sześć syntetycznych pozycji portfela i odpowiadający im wycinek księgi.</p></div>
      <Field title="Zmiana stóp (pb)" hint="100 pb = 1 punkt procentowy. Zakres: -300 do +300 pb."><input type="number" min="-300" max="300" step="1" value={shockValue} disabled={saving} onChange={event => { setShockValue(event.target.value); }} /></Field>
      <Field title="Beta depozytów" hint="Część zmiany stóp przenoszona na depozyty oszczędnościowe: 0–1."><input type="number" min="0" max="1" step="any" value={betaValue} disabled={saving} onChange={event => { setBetaValue(event.target.value); }} /></Field>
      <div className="finance-form-footer"><label className="finance-checkbox"><input type="checkbox" checked={injectIssues} disabled={saving} onChange={event => { setInjectIssues(event.target.checked); }} /><span>Dodaj rozbieżność księgową i anomalię historyczną<small>Celowe błędy do sprawdzenia uzgodnienia i sygnałów kontrolnych.</small></span></label><button type="submit" disabled={!loaded || Boolean(readError) || saving || active}>{saving ? 'Zapisywanie analizy…' : 'Oblicz scenariusz'}</button></div>
      {active && <p className="hint finance-form-note">Trwa wykonanie. Status aktualizuje się automatycznie. Wspólny limit demo: jedno zadanie ML lub finansowe naraz.</p>}
    </form>

    {(readError || writeError) && <div className="notice danger" role="alert">{readError && <p>{readError}</p>}{writeError && <p>{writeError}</p>}{readError && loaded && <p>Widoczne wyniki pochodzą z ostatniego odczytu. Odśwież stan przed uruchomieniem nowej analizy.</p>}</div>}

    <section aria-label="Historia analiz" className="finance-history">
      <div className="finance-section-heading"><div><p className="eyebrow">02 / Historia scenariuszy</p><h3>Każde wykonanie zachowuje swoje dane</h3></div><button className="demo-secondary" type="button" disabled={saving || loading} onClick={() => { void refresh(); }}>Odśwież analizy</button></div>
      {!loaded && loading && <p role="status">Wczytywanie historii analiz…</p>}
      {loaded && !runs.length && <Empty title="Jeszcze nie wykonano analizy">Ustaw scenariusz i uruchom obliczenia. Wynik, uzgodnienie z księgą oraz historia pojawią się po rzeczywistym wykonaniu.</Empty>}
      {runs.length > 0 && <div className="finance-history-list">{runs.map(run => <button key={run.id} type="button" className={`finance-history-item ${selected?.id === run.id ? 'finance-chosen' : ''}`} aria-label={`Pokaż analizę ${run.id}`} aria-pressed={selected?.id === run.id} onClick={() => { setSelectedId(run.id); }}><span><strong>{shock(run.scenario.shock_bps)}</strong><span>beta {percent.format(run.scenario.deposit_beta)}</span></span><small>{dateTime.format(new Date(run.created_at))} · Warszawa</small><span className={`demo-status ${run.status}`}>{statuses[run.status]}</span><small>{run.scenario.inject_issues ? 'Zestaw z celowymi błędami' : 'Zestaw bez celowych błędów'}</small></button>)}</div>}
    </section>

    {selected && isActive(selected) && <div className="panel demo-pending" role="status"><span className="demo-spinner" aria-hidden="true" /><div><h3>{selected.status === 'queued' ? 'Obliczenia oczekują na wykonanie.' : 'Trwają obliczenia scenariusza.'}</h3><p>Uzgodnienie danych, bazowy NII i scenariusz stóp. Limit obliczeń: 30 sekund.</p></div></div>}
    {selected?.status === 'failed' && <div className="notice danger" role="alert"><strong>Analiza nie powiodła się.</strong><p>{selected.error ?? 'Nie uzyskano poprawnego wyniku.'}</p></div>}
    {selected?.status === 'succeeded' && selected.result && <FinancialResult report={selected.result} exportPath={`/demo-api${path}/${encodeURIComponent(selected.id)}/export`} />}
    {selected && <Provenance run={selected} />}
  </div>;
}

function MonthlyChart({ months }: { months: FinanceMonth[] }) {
  const titleId = useId();
  const values = months.flatMap(month => [month.nii_base_pln, month.nii_scenario_pln]);
  const low = Math.min(0, ...values);
  const high = Math.max(1, ...values);
  const x = (index: number) => 70 + index * 640 / Math.max(1, months.length - 1);
  const y = (value: number) => 188 - (value - low) / (high - low) * 156;
  const points = (key: 'nii_base_pln' | 'nii_scenario_pln') => months.map((month, index) => `${String(x(index))},${String(y(month[key]))}`).join(' ');
  return <figure className="finance-chart"><figcaption id={titleId}><strong>Miesięczny wynik odsetkowy</strong><span><i className="finance-legend-base" />Baza <i className="finance-legend-scenario" />Scenariusz</span></figcaption><svg viewBox="0 0 750 235" role="img" aria-labelledby={titleId}><desc>Porównanie bazowego NII i scenariusza w PLN. Dokładne wartości są w tabeli Kwoty miesięczne poniżej.</desc>{[0, 0.5, 1].map(fraction => { const value = low + fraction * (high - low); return <g key={fraction}><line x1="70" y1={y(value)} x2="710" y2={y(value)} className="finance-chart-grid" /><text x="61" y={y(value) + 4} textAnchor="end">{new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 }).format(value / 1000000)} mln</text></g>; })}<polyline points={points('nii_base_pln')} className="finance-line-base" /><polyline points={points('nii_scenario_pln')} className="finance-line-scenario" />{months.map((month, index) => <g key={month.month}><circle cx={x(index)} cy={y(month.nii_scenario_pln)} r="3.5" className="finance-point" /><text x={x(index)} y="214" textAnchor="middle">{month.month.slice(5)}/{month.month.slice(2, 4)}</text></g>)}</svg></figure>;
}

function FinancialResult({ report, exportPath }: { report: FinanceReport; exportPath: string }) {
  const totals = report.totals;
  const blocked = report.quality_status === 'blocked';
  return <section className="finance-results" aria-label="Wynik analizy NII">
    <div className="finance-section-heading"><div><p className="eyebrow">03 / Wynik · 12 miesięcy</p><h2>Baza i scenariusz {shock(report.scenario.shock_bps)}</h2><p className="hint">Dane na {report.snapshot.as_of} · beta depozytów {percent.format(report.scenario.deposit_beta)} · syntetyczny wycinek bilansu</p></div><a className="button demo-secondary" href={exportPath} download>Eksport analizy JSON</a></div>
    <div className={`finance-quality ${blocked ? 'finance-quality-blocked' : ''}`} role="status"><strong>{blocked ? 'Wynik roboczy — dane nieuzgodnione' : 'Salda portfela i księgi są uzgodnione'}</strong><span>{blocked ? 'Scenariusz pokazuje wpływ założeń, ale nie jest podstawą zatwierdzonego raportu.' : 'Kontrola dotyczy syntetycznych sald. Nie oznacza zatwierdzenia metodyki ani wydania produkcyjnego.'}</span></div>
    <div className="finance-kpis"><div><span>NII bazowy</span><strong>{money(totals.nii_base_pln)}</strong><small>Przychody {money(totals.income_base_pln)}<br />Koszty {money(totals.expense_base_pln)}</small></div><div><span>NII w scenariuszu</span><strong>{money(totals.nii_scenario_pln)}</strong><small>Przychody {money(totals.income_scenario_pln)}<br />Koszty {money(totals.expense_scenario_pln)}</small></div><div className="finance-delta"><span>Zmiana NII</span><strong className={totals.delta_nii_pln < 0 ? 'finance-negative' : ''}>{signed(totals.delta_nii_pln)}</strong><small>Scenariusz minus baza<br />Projekcja przy stałych saldach</small></div></div>

    <div className="panel finance-monthly"><MonthlyChart months={report.monthly} /><details><summary>Kwoty miesięczne · PLN</summary><div className="table-scroll"><table aria-label="Miesięczna projekcja NII"><thead><tr><th scope="col">Miesiąc</th><th scope="col">NII bazowy</th><th scope="col">Przychody scenariusza</th><th scope="col">Koszty scenariusza</th><th scope="col">NII scenariusza</th><th scope="col">Zmiana NII</th></tr></thead><tbody>{report.monthly.map(month => <tr key={month.month}><th scope="row">{month.month}</th><td>{money(month.nii_base_pln)}</td><td>{money(month.income_scenario_pln)}</td><td>{money(month.expense_scenario_pln)}</td><td>{money(month.nii_scenario_pln)}</td><td>{signed(month.delta_nii_pln)}</td></tr>)}</tbody></table></div></details></div>

    <section className="panel finance-detail"><div className="finance-section-heading"><div><p className="eyebrow">Wyjaśnienie zmiany</p><h3>Wkład portfeli w NII</h3></div><span className="hint">Wkład pasywów uwzględnia znak kosztu.</span></div><div className="table-scroll"><table aria-label="Wkład portfeli w zmianę NII"><thead><tr><th scope="col">Portfel</th><th scope="col">Saldo</th><th scope="col">Stopa / przeszacowanie</th><th scope="col">Odsetki bazowe</th><th scope="col">Odsetki scenariusza</th><th scope="col">Wkład w zmianę NII</th></tr></thead><tbody>{report.contributions.map(item => <tr key={item.position_id}><th scope="row">{item.name}<small>{side(item.side)}</small></th><td>{money(item.balance_pln)}</td><td>{item.rate_type === 'fixed' ? 'Stała' : `Zmienna · miesiąc ${String(item.repricing_month)}`}</td><td>{money(item.base_interest_pln)}</td><td>{money(item.scenario_interest_pln)}</td><td className={item.delta_nii_pln < 0 ? 'finance-negative' : ''}>{signed(item.delta_nii_pln)}</td></tr>)}</tbody></table></div><details><summary>Stopy i odsetki pozycji w każdym miesiącu</summary>{report.contributions.map(item => <div className="finance-rate-table" key={item.position_id}><h4>{item.name}</h4><div className="table-scroll"><table aria-label={`Stopy i odsetki: ${item.name}`}><thead><tr><th scope="col">Miesiąc</th><th scope="col">Stopa bazowa</th><th scope="col">Stopa scenariusza</th><th scope="col">Odsetki bazowe</th><th scope="col">Odsetki scenariusza</th></tr></thead><tbody>{item.monthly.map(month => <tr key={month.month}><th scope="row">{month.month}</th><td>{percent.format(month.base_rate)}</td><td>{percent.format(month.scenario_rate)}</td><td>{money(month.base_interest_pln)}</td><td>{money(month.scenario_interest_pln)}</td></tr>)}</tbody></table></div></div>)}</details></section>

    <section className="panel finance-detail"><div className="finance-section-heading"><div><p className="eyebrow">Jakość danych</p><h3>Uzgodnienie portfela z księgą główną</h3></div><span className={`finance-tag ${blocked ? 'finance-tag-warning' : ''}`}>{report.reconciliation.filter(row => row.status === 'mismatch').length} rozbieżności</span></div><p className="hint">Różnica = portfel minus GL, według konta i strony. Tolerancja: 0,01 PLN. To wycinek sald, nie pełna księga podwójnego zapisu.</p><div className="table-scroll"><table aria-label="Uzgodnienie portfela z księgą główną"><thead><tr><th scope="col">Konto GL</th><th scope="col">Strona</th><th scope="col">Portfel</th><th scope="col">Księga główna</th><th scope="col">Różnica</th><th scope="col">Kontrola</th></tr></thead><tbody>{report.reconciliation.map(row => <tr key={`${row.gl_account}:${row.side}`} className={row.status === 'mismatch' ? 'finance-mismatch' : ''}><th scope="row">{row.gl_account}</th><td>{side(row.side)}</td><td>{money(row.portfolio_pln)}</td><td>{money(row.ledger_pln)}</td><td>{signed(row.difference_pln)}</td><td>{row.status === 'matched' ? 'Uzgodnione' : 'Rozbieżność'}</td></tr>)}</tbody></table></div></section>

    <section className="panel finance-detail"><p className="eyebrow">Kontrola historii · 2025-10 — 2026-09</p><h3>Nietypowy miesięczny wynik odsetkowy</h3><p className="hint">Sygnał regułowy, nie model ML ani dowód błędu. NII porównujemy z medianą poprzednich 6 miesięcy; próg to większa z wartości: 100 000 PLN lub 3 × 1,4826 × MAD. Pierwszych 6 miesięcy nie oceniamy.</p>{report.anomalies.length ? <div className="table-scroll"><table aria-label="Sygnały anomalii historycznych"><thead><tr><th scope="col">Miesiąc</th><th scope="col">NII</th><th scope="col">Mediana okna</th><th scope="col">Odchylenie</th><th scope="col">Próg sygnału</th></tr></thead><tbody>{report.anomalies.map(item => <tr key={item.month}><th scope="row">{item.month}</th><td>{money(item.nii_pln)}</td><td>{money(item.baseline_pln)}</td><td>{signed(item.deviation_pln)}</td><td>{money(item.threshold_pln)}</td></tr>)}</tbody></table></div> : <p className="finance-no-anomalies">Brak sygnałów przekraczających próg w ocenianych miesiącach.</p>}<details><summary>Źródłowa historia wyniku odsetkowego</summary><div className="table-scroll"><table aria-label="Historyczny wynik odsetkowy"><thead><tr><th scope="col">Miesiąc</th><th scope="col">Przychody odsetkowe</th><th scope="col">Koszty odsetkowe</th><th scope="col">NII</th></tr></thead><tbody>{report.snapshot.history.map(item => <tr key={item.month}><th scope="row">{item.month}</th><td>{money(item.interest_income_pln)}</td><td>{money(item.interest_expense_pln)}</td><td>{money(item.interest_income_pln - item.interest_expense_pln)}</td></tr>)}</tbody></table></div></details></section>

    <details className="panel finance-assumptions"><summary>Metoda i założenia analizy</summary><p>Projekcja warunkowa NII przy stałych saldach, nie prognoza przyszłych stóp ani regulacyjny pomiar IRRBB. NII nie obejmuje całego rachunku zysków i strat.</p><ul>{report.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul></details>
  </section>;
}

function Provenance({ run }: { run: FinanceRun }) {
  return <details className="panel finance-provenance"><summary>Dane i wersja tego wykonania</summary><dl><dt>Wykonanie</dt><dd><code>{run.id}</code></dd><dt>Utworzono</dt><dd>{run.created_at}</dd><dt>Dane na dzień</dt><dd>{run.snapshot.as_of} · {run.snapshot.currency} · dane syntetyczne</dd><dt>Scenariusz</dt><dd>{shock(run.scenario.shock_bps)}, beta {percent.format(run.scenario.deposit_beta)}, {run.scenario.inject_issues ? 'celowe błędy w danych' : 'bez celowych błędów'}</dd><dt>Wersja silnika</dt><dd>{run.manifest.engine_version}</dd><dt>SHA-256 kodu silnika</dt><dd><code>{run.manifest.engine_sha256}</code></dd><dt>SHA-256 danych</dt><dd><code>{run.manifest.input_sha256}</code></dd><dt>SHA-256 scenariusza</dt><dd><code>{run.manifest.scenario_sha256}</code></dd></dl><p className="hint">Ponowne obliczenie tworzy nowe wykonanie. Ta koperta wejść pozostaje zachowana również po błędzie.</p></details>;
}
