// SPEC-0018 D01–D05. Separate local-demo entry; no enterprise session/auth changes.
import { useCallback, useEffect, useRef, useState } from 'react';
import { demoRequest } from './api';
import { Data } from './Data';
import { Experiments } from './Experiments';
import { Models } from './Models';
import { Transforms } from './Transforms';
import { Field, label, refs } from './ui';
import type { DemoState, Mutation, Project } from './types';

type Tab = 'data' | 'transforms' | 'models' | 'experiments';
const tabs: { id: Tab; title: string; step: string }[] = [
  { id: 'data', title: 'Dane', step: '01' }, { id: 'transforms', title: 'Transformacje', step: '02' },
  { id: 'models', title: 'Modele', step: '03' }, { id: 'experiments', title: 'Eksperymenty', step: '04' },
];

export function DemoApp() {
  const [state, setState] = useState<DemoState | null>(null);
  const [projectId, setProjectId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [tab, setTab] = useState<Tab>('data');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const lifetime = useRef<AbortController | null>(null);
  const readSequence = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = ++readSequence.current;
    const signal = lifetime.current?.signal;
    const next = await demoRequest<DemoState>('/state', undefined, signal);
    if (next.mode !== 'local-demo' || !Array.isArray(next.projects) || !Array.isArray(next.objects) || !Array.isArray(next.runs)) throw new Error('Nieprawidłowa odpowiedź lokalnego demonstratora.');
    // A manual refresh may race an existing poll: never regress to an older snapshot.
    if (!signal?.aborted && sequence === readSequence.current) setState(next);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void refresh().catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Nie można wczytać demonstratora.'); });
    return () => { controller.abort(); };
  }, [refresh]);

  const activeRun = state?.runs.some(run => run.status === 'queued' || run.status === 'running') ?? false;
  // Sequential polling only while a real run is active; no overlapping timers or synthetic status.
  useEffect(() => {
    if (!activeRun) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { await refresh(); } catch (reason) {
        if (!stopped) setError(reason instanceof Error ? reason.message : 'Nie można odświeżyć eksperymentu.');
      }
      if (!stopped) timer = setTimeout(() => { void poll(); }, 1000);
    };
    timer = setTimeout(() => { void poll(); }, 1000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [activeRun, refresh]);

  const mutate: Mutation = async (work, message) => {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await work(); await refresh(); setNotice(message); }
    catch (reason) { setError(`${reason instanceof Error ? reason.message : 'Operacja nie powiodła się.'} Jeśli zapis mógł się zakończyć, odśwież stan przed ponowną próbą.`); }
    finally { setBusy(false); }
  };

  const project = state?.projects.find(item => item.id === projectId) ?? state?.projects[0];
  const objects = state?.objects.filter(object => object.project_id === project?.id) ?? [];
  const datasets = refs(objects, 'dataset');
  const transforms = refs(objects, 'transformation');
  const models = refs(objects, 'model');
  const analyses = objects.filter(object => object.kind === 'analysis');
  const runs = state?.runs.filter(run => run.project_id === project?.id) ?? [];
  const selected = datasets.find(ref => ref.version.id === versionId) ?? datasets[0];
  const selectDataset = (id: string) => { setVersionId(id); setTab('data'); };

  return <div className="demo-app">
    <a className="skip-link" href="#demo-main">Przejdź do treści</a>
    <aside className="demo-sidebar">
      <div className="demo-brand"><img src="/torii-logo.jpg" alt="Torii" /><span>WORKSPACE</span></div>
      <p className="demo-sidebar-label">Twoje projekty <span>{state?.projects.length ?? 0}</span></p>
      <nav aria-label="Projekty" className="demo-projects">{state?.projects.map(item => <button key={item.id} disabled={busy} className={project?.id === item.id ? 'active' : ''} aria-current={project?.id === item.id ? 'page' : undefined} onClick={() => { setProjectId(item.id); setVersionId(''); setTab('data'); setError(''); setNotice(''); }}><span aria-hidden="true">▱</span>{item.name}</button>)}</nav>
      <form className="demo-project-form" onSubmit={event => { event.preventDefault(); void mutate(async () => {
        const created = await demoRequest<Project>('/projects', { name: name.trim() });
        setProjectId(created.id); setVersionId(''); setTab('data'); setName('');
      }, 'Projekt utworzony. Zacznij od danych przykładowych lub CSV.'); }}>
        <fieldset disabled={busy || !state}><Field title="Nazwa projektu"><input required maxLength={100} placeholder="Nowy projekt…" value={name} onChange={event => { setName(event.target.value); }} /></Field><button type="submit" className="demo-new-project">Utwórz projekt <span aria-hidden="true">+</span></button></fieldset>
      </form>
      <div className="demo-sidebar-foot"><span className="demo-local-dot" /> Jeden lokalny operator<p>Dane → transformacje → modele → eksperymenty. Jeden spójny kontekst.</p><span className="demo-version-label">CONCEPT DEMO / 0018</span></div>
    </aside>
    <div className="demo-workspace">
      <header className="demo-topbar"><div className="demo-breadcrumb">Torii <span aria-hidden="true">/</span> {project?.name ?? 'Nowy workspace'}</div><div className="demo-top-actions"><span className="demo-environment">DEMO · lokalnie · bez SSO</span><button className="text-button" disabled={busy} onClick={() => { setError(''); void refresh().catch((reason: unknown) => { setError(reason instanceof Error ? reason.message : 'Nie można odświeżyć stanu.'); }); }}>Odśwież</button></div></header>
      <div className="demo-safety">Środowisko demonstracyjne, nie produkcja. Nie używaj danych firmowych i nie udostępniaj przez LAN ani Internet.</div>
      <main id="demo-main" tabIndex={-1}>
        {error && <div className="notice danger" role="alert">{error}</div>}
        {notice && <div className="notice success" role="status">{notice}</div>}
        {busy && <div className="demo-saving" role="status"><span className="demo-spinner" aria-hidden="true" /> Zapisuję i odświeżam…</div>}
        {!state ? <div className="demo-empty"><h1>Twój workspace</h1><p>{error ? 'Połączenie wymaga uwagi. Uruchom lokalny demonstrator i odśwież.' : 'Wczytuję projekty i obiekty…'}</p></div> : !project ? <section className="demo-welcome"><p className="eyebrow">Torii · warsztat danych i modeli</p><h1>Od danych<br />do decyzji.</h1><p>Zobacz cały proces w jednym miejscu: wersje danych, przepisy transformacji, modele i mierzalne wyniki.</p><div className="demo-welcome-flow" aria-label="Kroki demonstratora">{tabs.map(item => <div key={item.id}><span>{item.step}</span><strong>{item.title}</strong></div>)}</div><p className="hint">Utwórz projekt w panelu po lewej. Pierwszy eksperyment możesz wykonać na danych syntetycznych — bez konfiguracji połączeń.</p><div className="demo-scope"><strong>Co pokazuje ten koncept?</strong><p>Niezmienne wersje i ich pochodzenie, deklaratywne transformacje, regresję Ridge, baseline oraz rzeczywiste śledzenie MLflow.</p><p>SSO, współdzielenie, SQL/Parquet, Jupyter, pełne XAI i wdrożenia produkcyjne są poza tą demonstracją.</p></div></section> : <>
          <section className="demo-heading"><div><p className="eyebrow">Projekt / laboratorium</p><h1>{project.name}</h1><p>Buduj, porównuj i wracaj do źródła każdego wyniku.</p></div><a className="button demo-secondary" href={`/demo-api/projects/${project.id}/export`} download>Eksport projektu <span aria-hidden="true">↓</span></a></section>
          <div className="demo-summary"><span><strong>{objects.filter(object => object.kind === 'dataset').length}</strong> zbiory danych</span><span><strong>{transforms.length}</strong> transformacje</span><span><strong>{models.length}</strong> modele</span><span><strong>{runs.length}</strong> eksperymenty</span><span><strong>{analyses.length}</strong> analizy</span></div>
          <nav className="demo-tabs" aria-label="Etapy projektu">{tabs.map(item => <button key={item.id} onClick={() => { setTab(item.id); }} aria-current={tab === item.id ? 'step' : undefined} className={tab === item.id ? 'active' : ''}><span>{item.step}</span>{item.title}{item.id === 'experiments' && activeRun && <i className="demo-local-dot" aria-label="Trwa wykonanie" />}</button>)}</nav>
          <div className="demo-version-bar"><div><span className="demo-chip">SNAPSHOT</span><span className="hint">Pracujesz na konkretnej wersji</span></div><Field title="Wersja danych"><select value={selected?.version.id ?? ''} disabled={busy || !datasets.length} onChange={event => { setVersionId(event.target.value); }}><option value="" disabled>Dodaj zbiór danych</option>{datasets.map(ref => <option key={ref.version.id} value={ref.version.id}>{label(ref)} · {ref.version.summary.row_count ?? 0} wierszy</option>)}</select></Field></div>
          {tab === 'data' && <Data key={project.id} projectId={project.id} datasets={datasets} selected={selected} busy={busy} mutate={mutate} select={selectDataset} allVersions={[...datasets, ...transforms]} />}
          {tab === 'transforms' && <Transforms key={`${project.id}:${selected?.version.id ?? ''}`} projectId={project.id} selected={selected} transforms={transforms} datasets={datasets} busy={busy} mutate={mutate} select={selectDataset} />}
          {tab === 'models' && <Models key={`${project.id}:${selected?.version.id ?? ''}`} projectId={project.id} selected={selected} models={models} busy={busy} mutate={mutate} experiment={() => { setTab('experiments'); }} />}
          {tab === 'experiments' && <Experiments key={project.id} projectId={project.id} selected={selected} models={models} datasets={datasets} runs={runs} analyses={analyses} activeRun={activeRun} busy={busy} mutate={mutate} selectDataset={selectDataset} />}
          <footer className="demo-footer"><span>TORII · lokalny koncept</span><p>Eksport projektu: definicje, hashe, metryki i środowisko — bez danych oraz artefaktów modelu. Nie jest pełnym pakietem odtworzeniowym.</p></footer>
        </>}
      </main>
    </div>
  </div>;
}
