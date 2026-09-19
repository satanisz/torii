import { useCallback, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from './api/client';
import type { Project, ProjectCreate } from './api/types';
import { ErrorPanel, Field, formatDate, Loading, PageControls } from './components';
import { roles, text } from './i18n/pl';
import { useDirtyGuard, useMutationFailure, useRead, useRetryReady, useSession } from './state';

export function Projects() {
  const { session } = useSession();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Project | null>(null);
  const cursor = cursors[cursors.length - 1] ?? null;
  const load = useCallback((signal: AbortSignal) => api.projects(cursor, filter, signal), [cursor, filter]);
  const { state, reload } = useRead(load);
  function search(event: FormEvent) {
    event.preventDefault(); setCursors([null]); setFilter(query.trim());
  }
  return <>
    <header className="page-heading"><div><p className="eyebrow">{text.workspace}</p><h1>{text.projectsTitle}</h1><p>{text.projectsIntro}</p></div>
      {session.can_create_project && !creating && <button onClick={() => { setCreating(true); setCreated(null); }}>{text.createProject}</button>}
    </header>
    {creating && <CreateProject onCancel={() => setCreating(false)} onCreated={(project) => { setCreating(false); setCreated(project); reload(); }} />}
    {created && <p className="notice success" role="status">{text.saved} <Link to={`/projects/${created.id}`}>{created.name}</Link></p>}
    <form className="filter-bar" onSubmit={search} role="search">
      <label htmlFor="project-filter">{text.search}</label>
      <input id="project-filter" maxLength={100} value={query} onChange={(e) => setQuery(e.target.value)} type="search" />
      <button className="secondary" type="submit">{text.searchAction}</button>
      {filter && <button className="text-button" type="button" onClick={() => { setQuery(''); setFilter(''); setCursors([null]); }}>{text.clearFilter}</button>}
    </form>
    {state.status === 'loading' && <Loading />}
    {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
    {state.status === 'ready' && <>
      {state.value.data.items.length === 0 ? <section className="empty-state"><h2>{filter ? text.noMatches : text.noProjects}</h2><p>{text.noProjectsHint}</p><code>{session.principal_id}</code></section> :
        <div className="table-scroll"><table><caption className="sr-only">{text.projects}</caption><thead><tr><th>{text.name}</th><th>{text.role}</th><th>{text.created}</th></tr></thead><tbody>
          {state.value.data.items.map((project) => <tr key={project.id}><td><Link className="project-link" to={`/projects/${project.id}`}>{project.name}</Link><p className="table-description">{project.description || text.noDescription}</p></td><td><span className="role-badge">{roles[project.my_role]}</span></td><td><time dateTime={project.created_at}>{formatDate(project.created_at)}</time></td></tr>)}
        </tbody></table></div>}
      <PageControls previous={cursors.length > 1 ? () => setCursors(cursors.slice(0, -1)) : undefined} next={state.value.data.next_cursor ? () => setCursors([...cursors, state.value.data.next_cursor]) : undefined} />
    </>}
  </>;
}

function CreateProject({ onCancel, onCreated }: { onCancel: () => void; onCreated: (project: Project) => void }) {
  const { session } = useSession();
  const fail = useMutationFailure();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [nameError, setNameError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [pending, setPending] = useState<{ body: ProjectCreate; key: string } | null>(null);
  const retryReady = useRetryReady(error);
  const requestInFlight = useRef(false);
  const dirty = Boolean(name || description || pending);
  useDirtyGuard(dirty);
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (requestInFlight.current || !retryReady) return;
    if (!name || name.length > 120 || name.trim() !== name) { setNameError(text.invalidName); return; }
    if (!session.csrf_token) { setError(new ApiError(401, 'missing_csrf')); return; }
    const mutation = pending ?? { body: { name, description }, key: crypto.randomUUID() };
    requestInFlight.current = true; setSaving(true); setError(null); setNameError(undefined);
    try { onCreated((await api.createProject(mutation.body, session.csrf_token, mutation.key)).data); }
    catch (cause) {
      const problem = fail(cause); setError(problem);
      if (problem.status === 0 || problem.status >= 500) setPending(mutation);
      else setPending(null);
      if (problem.fields.some((field) => field.pointer === '/name')) setNameError(text.invalidField);
    } finally { requestInFlight.current = false; setSaving(false); }
  }
  return <section className="panel form-panel" aria-labelledby="create-title"><h2 id="create-title">{text.createTitle}</h2>
    <form onSubmit={submit}>
      <fieldset disabled={saving || Boolean(pending)}>
        <Field label={text.name} id="project-name" hint={text.nameHint} error={nameError}>
          <input autoFocus id="project-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required aria-invalid={Boolean(nameError)} aria-describedby={`project-name-hint${nameError ? ' project-name-error' : ''}`} />
        </Field>
        <Field label={text.descriptionOptional} id="project-description" error={error?.fields.some((field) => field.pointer === '/description') ? text.invalidField : undefined}>
          <textarea id="project-description" value={description} maxLength={4000} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </Field>
      </fieldset>
      {error && <ErrorPanel error={error} />}
      {pending && <p className="notice warning">{text.uncertain}</p>}
      <div className="actions"><button type="submit" disabled={saving || !session.csrf_token || !retryReady}>{saving ? text.saving : pending ? text.retryWrite : text.createProject}</button><button type="button" className="secondary" disabled={saving} onClick={() => { if (!dirty || window.confirm(text.dirtyPrompt)) onCancel(); }}>{text.cancel}</button></div>
    </form>
  </section>;
}
