import { useState } from 'react';
import { demoRequest } from './api';
import { DataTable, Empty, Field, label, number } from './ui';
import type { DemoObject, Mutation, Run, VersionRef } from './types';

const statuses = { queued: 'W kolejce', running: 'W trakcie', succeeded: 'Zakończony', failed: 'Niepowodzenie' };

export function Experiments({ projectId, selected, models, datasets, runs, analyses, activeRun, busy, mutate, selectDataset }: {
  projectId: string; selected: VersionRef | undefined; models: VersionRef[]; datasets: VersionRef[];
  runs: Run[]; analyses: DemoObject[]; activeRun: boolean; busy: boolean; mutate: Mutation; selectDataset: (id: string) => void;
}) {
  const [modelId, setModelId] = useState(models[0]?.version.id ?? '');
  const [selectedRun, setSelectedRun] = useState('');
  const chosenModel = models.find(ref => ref.version.id === modelId) ?? models[0];
  const orderedRuns = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const chosenRun = runs.find(run => run.id === selectedRun) ?? orderedRuns[0];
  const successful = runs.filter(run => run.status === 'succeeded');
  const different = new Set(successful.map(run => `${run.dataset_version_id}:${run.target}`)).size > 1;
  const result = chosenRun?.result;
  const analysis = analyses.find(object => object.versions.some(version => version.definition.run_id === chosenRun?.id));
  const maximum = Math.max(1, ...(result?.importance.map(item => Math.abs(item.value)) ?? []));

  return <div className="demo-stack">
    <form className="panel demo-run-form" onSubmit={event => { event.preventDefault(); void mutate(async () => {
      if (!chosenModel || !selected) throw new Error('Wybierz model i dane.');
      const created = await demoRequest<Run>(`/projects/${projectId}/runs`, { model_version_id: chosenModel.version.id, dataset_version_id: selected.version.id });
      setSelectedRun(created.id);
    }, 'Eksperyment uruchomiony. Wynik pojawi się automatycznie po zakończeniu.'); }}>
      <div><p className="eyebrow">Rzeczywiste wykonanie · MLflow</p><h2>Uruchom eksperyment</h2><p className="hint">Stały podział 75 / 25, seed 42. Dane wybierasz w pasku wersji powyżej.</p></div>
      <Field title="Wersja modelu"><select disabled={busy} value={chosenModel?.version.id ?? ''} onChange={event => { setModelId(event.target.value); }}><option value="" disabled>Najpierw zapisz model</option>{models.map(ref => <option key={ref.version.id} value={ref.version.id}>{label(ref)}</option>)}</select></Field>
      <button type="submit" disabled={busy || activeRun || !chosenModel || !selected || (selected.version.summary.row_count ?? 0) < 20}>Uruchom eksperyment <span aria-hidden="true">↗</span></button>
      <p className="hint demo-run-note">{activeRun ? 'Trwa wykonanie. Demonstrator obsługuje jeden eksperyment naraz; status odświeża się automatycznie.' : (selected?.version.summary.row_count ?? 0) < 20 ? 'Wybierz zbiór zawierający co najmniej 20 wierszy.' : `Dane: ${label(selected)}. Cel i cechy muszą występować w tej wersji.`}</p>
    </form>
    <section><div className="demo-section-heading"><div><p className="eyebrow">Historia i porównanie</p><h2>Eksperymenty <span className="demo-count">{runs.length}</span></h2></div><span className="hint">Niższe MAE / RMSE · wyższe R²</span></div>
      {different && <p className="notice warning">Różne wersje danych lub zmienne celu — tych metryk nie traktuj jako wspólnego rankingu.</p>}
      {!runs.length ? <Empty title="Każdy wynik zaczyna się od eksperymentu">Wybierz model i wersję danych. Metryki pojawią się dopiero po rzeczywistym treningu i zapisie do MLflow.</Empty> : <div className="table-scroll"><table aria-label="Porównanie eksperymentów"><thead><tr><th scope="col">Model / wykonanie</th><th scope="col">Dane i cel</th><th scope="col">Status</th><th scope="col">MAE ↓</th><th scope="col">RMSE ↓</th><th scope="col">R² ↑</th><th scope="col">Podział</th></tr></thead><tbody>{orderedRuns.map(run => <tr className={chosenRun?.id === run.id ? 'demo-selected-row' : ''} key={run.id}><td><button className="text-button" onClick={() => { setSelectedRun(run.id); }} aria-pressed={chosenRun?.id === run.id}>{label(models.find(ref => ref.version.id === run.model_version_id))}</button><small className="demo-id">{run.id.slice(0, 8)} · {run.created_at.slice(0, 16).replace('T', ' ')}</small></td><td><button className="text-button" onClick={() => { selectDataset(run.dataset_version_id); }}>{label(datasets.find(ref => ref.version.id === run.dataset_version_id))}</button><small className="demo-id">cel: {run.target}</small></td><td><span className={`demo-status ${run.status}`}>{statuses[run.status]}</span></td><td>{number(run.result?.metrics.mae)}</td><td>{number(run.result?.metrics.rmse)}</td><td>{number(run.result?.metrics.r2)}</td><td>test {number(run.test_size * 100)}%<small className="demo-id">seed {run.seed}</small></td></tr>)}</tbody></table></div>}
    </section>
    {chosenRun?.status === 'failed' && <div className="notice danger" role="alert"><strong>Eksperyment nie powiódł się.</strong><p>{chosenRun.error ?? 'Nie uzyskano poprawnego wyniku. Sprawdź dane i definicję modelu.'}</p></div>}
    {chosenRun && (chosenRun.status === 'running' || chosenRun.status === 'queued') && <div className="panel demo-pending" role="status"><span className="demo-spinner" aria-hidden="true" /><div><h3>{statuses[chosenRun.status]}</h3><p>Trening, walidacja i zapis artefaktów. Limit wykonania: 120 sekund. Możesz przejść do innego ekranu.</p></div></div>}
    {chosenRun?.status === 'succeeded' && result && <section className="panel demo-stack" aria-label="Analiza wyniku"><div className="demo-section-heading"><div><p className="eyebrow">Analiza · zbiór testowy</p><h2>{label(models.find(ref => ref.version.id === chosenRun.model_version_id))}</h2></div><span className="demo-chip">{result.algorithm === 'linear' ? 'Ridge' : 'Baseline średniej'}</span></div>
      <div className="demo-metrics"><div><span>MAE</span><strong>{number(result.metrics.mae)}</strong><small>średni błąd bezwzględny</small></div><div><span>RMSE</span><strong>{number(result.metrics.rmse)}</strong><small>pierwiastek błędu kwadratowego</small></div><div><span>R²</span><strong>{number(result.metrics.r2)}</strong><small>współczynnik determinacji</small></div></div>
      <div className="demo-lineage"><button className="text-button" onClick={() => { selectDataset(chosenRun.dataset_version_id); }}>{label(datasets.find(ref => ref.version.id === chosenRun.dataset_version_id))}</button><span>→ model → wykonanie → {analysis?.name ?? 'analiza wyniku'}</span></div>
      <div className="demo-two-column"><div><h3>Co wpływa na predykcję?</h3><p className="hint">Współczynniki Ridge po standaryzacji cech. Znak określa kierunek relacji — nie przyczynowość. To nie pełna analiza XAI.</p>{result.importance.length ? <div className="table-scroll demo-coefficients"><table aria-label="Współczynniki Ridge"><thead><tr><th scope="col">Cecha</th><th scope="col">Współczynnik</th></tr></thead><tbody>{result.importance.map(item => <tr key={item.feature}><th scope="row">{item.feature}</th><td><strong>{number(item.value)}</strong><span className={`demo-coefficient ${item.value < 0 ? 'negative' : ''}`} style={{ width: `${String(Math.max(2, Math.abs(item.value) / maximum * 100))}%` }} /></td></tr>)}</tbody></table></div> : <p className="notice">Baseline przewiduje stałą średnią treningową i nie ma współczynników cech.</p>}</div><div><h3>Predykcje a rzeczywistość</h3><p className="hint">Pierwsze {result.predictions.length} obserwacji testowych (maks. 20).</p><DataTable title="Predykcje" columns={['Rzeczywiste', 'Przewidywane']} rows={result.predictions.map(item => ({ Rzeczywiste: item.actual, Przewidywane: item.predicted }))} /></div></div>
      <div className="demo-result-footer"><div><span className="hint">MLflow run ID</span><code>{result.mlflow_run_id}</code><p className="hint">Trening: {result.train_rows} · test: {result.test_rows} · seed {chosenRun.seed}</p></div><div className="actions"><a className="button" href={`/demo-api/runs/${chosenRun.id}/artifacts/model.joblib`} download>Pobierz model</a><a className="button demo-secondary" href={`/demo-api/runs/${chosenRun.id}/artifacts/result.json`} download>Wynik JSON</a><a className="button demo-secondary" href={`/demo-api/runs/${chosenRun.id}/artifacts/environment.json`} download>Środowisko</a></div></div>
      <p className="hint">Model joblib otwieraj wyłącznie wtedy, gdy pochodzi z zaufanego źródła. Eksport projektu do Git pomija dane, predykcje i współczynniki.</p>
      <details><summary>Obiekt analizy i środowisko wykonania</summary>{analysis && <><p>{analysis.name}</p><code>{analysis.versions[0]?.id}</code></>}<pre>{JSON.stringify(result.environment, null, 2)}</pre></details>
    </section>}
  </div>;
}
