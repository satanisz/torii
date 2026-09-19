import { useState } from 'react';
import { demoRequest, fileAsBase64 } from './api';
import { DataTable, Empty, Field, label, number, text } from './ui';
import type { DemoObject, Mutation, VersionRef } from './types';

interface Props { projectId: string; datasets: VersionRef[]; selected: VersionRef | undefined; busy: boolean; mutate: Mutation; select: (id: string) => void; allVersions: VersionRef[] }

export function Data({ projectId, datasets, selected, busy, mutate, select, allVersions }: Props) {
  const [name, setName] = useState('');
  const [append, setAppend] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const objects = [...new Map(datasets.map(ref => [ref.object.id, ref.object])).values()];
  const summary = selected?.version.summary;
  const parent = allVersions.find(ref => ref.version.id === selected?.version.definition.input_version_id);
  const transform = allVersions.find(ref => ref.version.id === selected?.version.definition.transformation_version_id);

  return <div className="demo-stack">
    <section className="demo-import-grid">
      <div className="demo-sample panel"><div className="demo-icon" aria-hidden="true">↗</div><p className="eyebrow">Szybki start</p><h2>Najpierw sprawdź koncept.</h2><p>Gotowe, syntetyczne dane regresji. Bez pobierania plików i bez informacji firmowych.</p><button disabled={busy} onClick={() => mutate(async () => {
        const created = await demoRequest<DemoObject>(`/projects/${projectId}/sample`, {});
        if (created.versions[0]) select(created.versions[0].id);
      }, 'Dodano syntetyczne dane. Możesz przejść do modelu lub transformacji.')}>Dodaj dane przykładowe <span aria-hidden="true">→</span></button></div>
      <form className="panel" onSubmit={event => { event.preventDefault(); void mutate(async () => {
        if (!file) throw new Error('Wybierz plik CSV.');
        const content = await fileAsBase64(file);
        const target = objects.find(object => object.id === append);
        const created = await demoRequest<DemoObject>(`/projects/${projectId}/datasets`, { name: target?.name ?? name.trim(), format: 'csv', content_base64: content, ...(target ? { object_id: target.id } : {}) });
        const newest = [...(created.versions ?? [])].sort((a, b) => b.number - a.number)[0];
        if (newest) select(newest.id);
      }, 'CSV zapisany jako niezmienna wersja danych.'); }}>
        <h2>Twoje dane, lokalnie</h2><fieldset disabled={busy}>
          <Field title="Sposób importu"><select value={append} onChange={event => { setAppend(event.target.value); }}><option value="">Nowy obiekt danych</option>{objects.map(object => <option key={object.id} value={object.id}>Nowa wersja: {object.name}</option>)}</select></Field>
          {!append && <Field title="Nazwa danych"><input maxLength={100} required value={name} placeholder="np. Popyt tygodniowy" onChange={event => { setName(event.target.value); }} /></Field>}
          <Field title="Plik CSV" hint="UTF-8, przecinek, do 5 MiB / 5000 wierszy / 50 kolumn. Puste pola są brakami."><input type="file" accept=".csv,text/csv" onChange={event => { const next = event.target.files?.[0] ?? null; setFile(next); if (!name && next) setName(next.name.replace(/\.csv$/i, '').slice(0, 100)); }} /></Field>
          <button type="submit">Importuj CSV</button>
        </fieldset>
      </form>
    </section>
    {!selected ? <Empty title="Katalog danych jest jeszcze pusty">Dodaj przykładowy zbiór lub zaimportuj CSV. Każdy import zapisuje własną, niezmienną wersję.</Empty> : <section className="panel demo-stack">
      <div className="demo-section-heading"><div><p className="eyebrow">Obiekt danych · wersja {selected.version.number}</p><h2>{selected.object.name}</h2></div><a className="button demo-secondary" href={`/demo-api/datasets/${selected.version.id}/csv`} download>Pobierz CSV</a></div>
      <div className="demo-stat-row"><div><strong>{number(summary?.row_count)}</strong><span>wierszy</span></div><div><strong>{summary?.columns?.length ?? 0}</strong><span>kolumn</span></div><div><strong>{selected.object.versions.length}</strong><span>niezmiennych wersji</span></div><div><strong>{text(selected.version.definition.source) === 'synthetic' ? 'syntetyczne' : text(selected.version.definition.source) === 'transformation' ? 'transformacja' : 'CSV'}</strong><span>źródło</span></div></div>
      {(parent || transform) && <div className="demo-lineage"><span>Pochodzenie</span>{parent && <button className="text-button" onClick={() => { select(parent.version.id); }}>Źródło: {label(parent)}</button>}{transform && <span>→ {label(transform)}</span>}<span>→ {label(selected)}</span></div>}
      <div><h3>Profil kolumn</h3><div className="table-scroll"><table aria-label="Profil kolumn"><thead><tr><th scope="col">Kolumna</th><th scope="col">Typ</th><th scope="col">Braki</th><th scope="col">Unikalne</th><th scope="col">Min</th><th scope="col">Max</th><th scope="col">Średnia</th></tr></thead><tbody>{summary?.profile?.map(column => <tr key={column.name}><th scope="row">{column.name}</th><td><span className="demo-chip">{column.dtype}</span></td><td>{number(column.missing)}</td><td>{number(column.unique)}</td><td>{number(column.min)}</td><td>{number(column.max)}</td><td>{number(column.mean)}</td></tr>)}</tbody></table></div></div>
      <div><div className="demo-section-heading"><h3>Podgląd danych</h3><span className="hint">Pierwsze {summary?.preview?.length ?? 0} wierszy · maks. 20</span></div><DataTable title="Podgląd danych" columns={summary?.columns ?? []} rows={summary?.preview ?? []} /></div>
      <details><summary>Tożsamość i integralność wersji</summary><dl><dt>ID wersji</dt><dd><code>{selected.version.id}</code></dd><dt>SHA-256 zawartości · nie podpis cyfrowy</dt><dd><code>{selected.version.sha256}</code></dd><dt>Utworzono</dt><dd>{selected.version.created_at}</dd></dl></details>
    </section>}
  </div>;
}
