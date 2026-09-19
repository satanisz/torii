import { useState } from 'react';
import { demoRequest } from './api';
import { Empty, Field, label, text } from './ui';
import type { DemoObject, Mutation, VersionRef } from './types';

const operations = {
  drop_missing: 'Usuń wiersze z brakami', drop_duplicates: 'Usuń powtórzone wiersze',
  select_columns: 'Wybierz kolumny', filter_numeric: 'Filtr liczbowy',
};
type Operation = keyof typeof operations;

export function Transforms({ projectId, selected, transforms, datasets, busy, mutate, select }: {
  projectId: string; selected: VersionRef | undefined; transforms: VersionRef[]; datasets: VersionRef[];
  busy: boolean; mutate: Mutation; select: (id: string) => void;
}) {
  const [name, setName] = useState('');
  const [operation, setOperation] = useState<Operation>('drop_missing');
  const available = selected?.version.summary.columns ?? [];
  const numeric = selected?.version.summary.profile?.filter(column => column.dtype === 'number').map(column => column.name) ?? [];
  const [columns, setColumns] = useState(available);
  const [column, setColumn] = useState(numeric[0] ?? '');
  const [operator, setOperator] = useState('gte');
  const [value, setValue] = useState('0');
  return <div className="demo-two-column">
    <form className="panel" onSubmit={event => { event.preventDefault(); void mutate(async () => {
      if (!selected) throw new Error('Najpierw wybierz wersję danych.');
      if (operation === 'select_columns' && !columns.length) throw new Error('Wybierz co najmniej jedną kolumnę.');
      if (operation === 'filter_numeric' && (!column || !value.trim() || !Number.isFinite(Number(value)))) throw new Error('Wybierz kolumnę liczbową i poprawny próg.');
      await demoRequest(`/projects/${projectId}/transformations`, { name: name.trim(), input_version_id: selected.version.id, operation,
        ...(operation === 'select_columns' ? { columns } : {}),
        ...(operation === 'filter_numeric' ? { column, operator, value: Number(value) } : {}),
      });
      setName('');
    }, 'Definicja zapisana. Wykonaj transformację, aby utworzyć nowy obiekt danych.'); }}>
      <p className="eyebrow">1. Definicja</p><h2>Przygotuj dane</h2><p className="hint">Przepis jest osobnym, wersjonowanym obiektem. Zapis nie uruchamia przetwarzania.</p>
      <p className="demo-input-label">Wejście: <strong>{selected ? label(selected) : 'Brak danych'}</strong></p>
      <fieldset disabled={busy || !selected}>
        <Field title="Nazwa transformacji"><input required maxLength={100} value={name} onChange={event => { setName(event.target.value); }} placeholder="np. Kompletne obserwacje" /></Field>
        <Field title="Operacja"><select value={operation} onChange={event => { setOperation(event.target.value as Operation); }}>{Object.entries(operations).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></Field>
        {operation === 'select_columns' && <fieldset className="demo-checkboxes"><legend>Kolumny wyniku</legend>{available.map(item => <label key={item}><input type="checkbox" checked={columns.includes(item)} onChange={event => { setColumns(event.target.checked ? [...columns, item] : columns.filter(current => current !== item)); }} />{item}</label>)}</fieldset>}
        {operation === 'filter_numeric' && <><Field title="Kolumna filtra"><select required value={column} onChange={event => { setColumn(event.target.value); }}><option value="" disabled>Wybierz kolumnę</option>{numeric.map(item => <option key={item}>{item}</option>)}</select></Field><div className="demo-form-row"><Field title="Warunek"><select value={operator} onChange={event => { setOperator(event.target.value); }}><option value="gte">większe lub równe (≥)</option><option value="lte">mniejsze lub równe (≤)</option></select></Field><Field title="Próg"><input required type="number" step="any" value={value} onChange={event => { setValue(event.target.value); }} /></Field></div></>}
        <div className="actions"><button type="submit">Zapisz transformację</button></div>
      </fieldset>
    </form>
    <section className="demo-stack"><div><p className="eyebrow">2. Wykonanie</p><h2>Zapisane transformacje</h2><p className="hint">Każde wykonanie tworzy nowy zbiór. Źródło pozostaje bez zmian.</p></div>
      {!transforms.length && <Empty title="Jeszcze bez transformacji">Zapisz pierwszy przepis po lewej stronie. Możesz też modelować bezpośrednio na danych źródłowych.</Empty>}
      {transforms.map(ref => <article className="panel demo-object-card" key={ref.version.id}><span className="demo-chip">transformacja · v{ref.version.number}</span><h3>{ref.object.name}</h3><p>{operations[text(ref.version.definition.operation) as Operation] ?? 'Transformacja'}</p><button className="text-button" onClick={() => { select(text(ref.version.definition.input_version_id)); }}>Źródło: {label(datasets.find(dataset => dataset.version.id === ref.version.definition.input_version_id))}</button><details><summary>Definicja</summary><pre>{JSON.stringify(ref.version.definition, null, 2)}</pre></details><div className="actions"><button disabled={busy} aria-label={`Wykonaj ${ref.object.name}`} onClick={() => mutate(async () => {
        const created = await demoRequest<DemoObject>(`/transformations/${ref.version.id}/execute`, {});
        if (created.versions[0]) select(created.versions[0].id);
      }, 'Transformacja wykonana. Wyświetlam nowy zbiór danych z pochodzeniem.')}>Wykonaj <span aria-hidden="true">→</span></button></div></article>)}
    </section>
  </div>;
}
