import { useState } from 'react';
import { demoRequest } from './api';
import { Empty, Field, label, text } from './ui';
import type { Mutation, VersionRef } from './types';

export function Models({ projectId, selected, models, busy, mutate, experiment }: {
  projectId: string; selected: VersionRef | undefined; models: VersionRef[];
  busy: boolean; mutate: Mutation; experiment: () => void;
}) {
  const numeric = selected?.version.summary.profile?.filter(column => column.dtype === 'number').map(column => column.name) ?? [];
  const [target, setTarget] = useState(numeric.at(-1) ?? '');
  const [features, setFeatures] = useState(numeric.slice(0, -1));
  const [name, setName] = useState('');
  const [algorithm, setAlgorithm] = useState('linear');
  const [alpha, setAlpha] = useState('1');
  return <div className="demo-two-column"><form className="panel" onSubmit={event => { event.preventDefault(); void mutate(async () => {
    if (!target || !features.length || features.includes(target)) throw new Error('Wybierz cel i co najmniej jedną inną cechę liczbową.');
    await demoRequest(`/projects/${projectId}/models`, { name: name.trim(), task: 'regression', algorithm, target, features, ...(algorithm === 'linear' ? { alpha: Number(alpha) } : {}) });
    setName('');
  }, 'Model zapisany jako kandydat. Uruchom eksperyment, aby otrzymać metryki.'); }}>
    <p className="eyebrow">Definicja · kandydat</p><h2>Zbuduj punkt odniesienia</h2><p className="hint">Model to przepis, nie wynik. Ridge uczy zależności liniowych; baseline przewiduje średnią z treningu.</p><p className="demo-input-label">Kolumny z: <strong>{label(selected)}</strong></p>
    <fieldset disabled={busy || numeric.length < 2}>
      <Field title="Nazwa modelu"><input required maxLength={100} value={name} placeholder="np. Popyt — Ridge" onChange={event => { setName(event.target.value); }} /></Field>
      <Field title="Algorytm"><select value={algorithm} onChange={event => { setAlgorithm(event.target.value); }}><option value="linear">Ridge · regresja liniowa</option><option value="dummy">Baseline · średnia treningowa</option></select></Field>
      <Field title="Zmienna celu"><select required value={target} onChange={event => { setTarget(event.target.value); setFeatures(numeric.filter(item => item !== event.target.value)); }}>{numeric.map(item => <option key={item}>{item}</option>)}</select></Field>
      <fieldset className="demo-checkboxes"><legend>Cechy wejściowe</legend>{numeric.filter(item => item !== target).map(item => <label key={item}><input type="checkbox" checked={features.includes(item)} onChange={event => { setFeatures(event.target.checked ? [...features, item] : features.filter(current => current !== item)); }} />{item}</label>)}</fieldset>
      {algorithm === 'linear' && <Field title="Regularyzacja α" hint="0–100; domyślnie 1. Cechy są standaryzowane wyłącznie na treningu."><input type="number" min="0" max="100" step="any" required value={alpha} onChange={event => { setAlpha(event.target.value); }} /></Field>}
      <div className="actions"><button type="submit">Zapisz model</button></div>
    </fieldset>
    {numeric.length < 2 && <p className="notice warning">Potrzebujesz co najmniej dwóch kolumn liczbowych: celu i cechy wejściowej.</p>}
    <p className="hint demo-form-foot">Stały seed 42 · test 25% · imputacja medianą i skalowanie dopasowane na zbiorze treningowym. To nie wdrożenie produkcyjne.</p>
  </form><section className="demo-stack"><div><p className="eyebrow">Katalog modeli</p><h2>Gotowe do eksperymentu</h2></div>
    {!models.length && <Empty title="Jeszcze bez modeli">Zapisz Ridge oraz baseline, aby porównać, czy model wnosi wartość ponad stałą średnią.</Empty>}
    {models.map(ref => <article className="panel demo-object-card" key={ref.version.id}><div className="demo-section-heading"><span className="demo-chip">model · v{ref.version.number}</span><span className="demo-candidate">KANDYDAT</span></div><h3>{ref.object.name}</h3><dl className="demo-mini-dl"><dt>Algorytm</dt><dd>{ref.version.definition.algorithm === 'linear' ? 'Ridge' : 'Baseline średniej'}</dd><dt>Cel</dt><dd>{text(ref.version.definition.target)}</dd><dt>Cechy</dt><dd>{Array.isArray(ref.version.definition.features) ? ref.version.definition.features.map(item => text(item)).join(', ') : '—'}</dd></dl><details><summary>Definicja i wersja</summary><pre>{JSON.stringify(ref.version.definition, null, 2)}</pre><code>{ref.version.id}</code></details><div className="actions"><button className="secondary" onClick={experiment}>Przejdź do eksperymentów →</button></div></article>)}
  </section></div>;
}
