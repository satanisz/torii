import { useCallback, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { api } from './api/client';
import type { ApiError } from './api/client';
import type { Project } from './api/types';
import { ErrorPanel, formatDate, Identifier, Loading, PageControls } from './components';
import { auditActions, roles, text } from './i18n/pl';
import { useRead } from './state';
import { AccessEditor } from './AccessEditor';

export function ProjectPage({ id, section }: { id: string; section: 'details' | 'access' | 'audit' }) {
  const [denied, setDenied] = useState<ApiError | null>(null);
  const load = useCallback((signal: AbortSignal) => api.project(id, signal), [id]);
  const { state, reload, invalidate } = useRead(load);
  const deny = useCallback((error: ApiError) => { invalidate(); setDenied(error); }, [invalidate]);
  if (denied) return <ErrorPanel error={denied} onRetry={() => { setDenied(null); reload(); }} />;
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} />;
  const project = state.value.data;
  return <>
    <nav className="breadcrumbs" aria-label="Ścieżka"><Link to="/projects">{text.projects}</Link><span aria-hidden="true">/</span><span>{project.name}</span></nav>
    <header className="page-heading"><div><p className="eyebrow">{text.project}</p><h1>{project.name}</h1><p>{project.description || text.noDescription}</p></div><span className="role-badge">{roles[project.my_role]}</span></header>
    <nav className="tabs" aria-label="Widoki projektu"><NavLink to={`/projects/${id}`} end>{text.details}</NavLink>{project.my_role === 'owner' && <><NavLink to={`/projects/${id}/access`}>{text.access}</NavLink><NavLink to={`/projects/${id}/audit`}>{text.audit}</NavLink></>}</nav>
    {section === 'details' ? <ProjectDetails project={project} /> : project.my_role !== 'owner' ? <section className="notice warning" role="alert"><h2>{text.forbiddenTitle}</h2><p>{text.forbidden}</p></section> :
      section === 'access' ? <AccessEditor project={project} onDenied={deny} /> : <AuditHistory project={project} onDenied={deny} />}
  </>;
}

function ProjectDetails({ project }: { project: Project }) {
  return <div className="details-grid"><section className="panel"><h2>{text.details}</h2><dl>
    <dt>{text.projectId}</dt><dd><Identifier value={project.id} /></dd>
    <dt>{text.creator}</dt><dd><Identifier value={project.created_by} /></dd>
    <dt>{text.created}</dt><dd><time dateTime={project.created_at}>{formatDate(project.created_at)}</time></dd>
    <dt>{text.role}</dt><dd>{roles[project.my_role]}</dd>
  </dl><p className="hint">{text.ownershipNote}</p></section><section className="panel scope-note"><p className="eyebrow">SP-01</p><h2>{text.scopeTitle}</h2><p>{text.scope}</p></section></div>;
}

function AuditHistory({ project, onDenied }: { project: Project; onDenied: (error: ApiError) => void }) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1] ?? null;
  const load = useCallback((signal: AbortSignal) => api.audit(project.id, cursor, signal), [project.id, cursor]);
  const { state, reload } = useRead(load, onDenied);
  return <section><h2>{text.audit}</h2><p className="section-intro">{text.auditIntro}</p>
    {state.status === 'loading' && <Loading />}
    {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
    {state.status === 'ready' && <>
      {state.value.data.items.length === 0 ? <p className="empty-state">{text.noAudit}</p> : <div className="table-scroll"><table><caption className="sr-only">{text.audit}</caption><thead><tr><th>{text.when}</th><th>{text.action}</th><th>{text.actor}</th><th>{text.outcome}</th></tr></thead><tbody>
        {state.value.data.items.map((event) => <tr key={event.id}><td><time dateTime={event.occurred_at}>{formatDate(event.occurred_at)}</time></td><td>{auditActions[event.action] ?? event.action}<details><summary>{text.details}</summary><dl><dt>{text.target}</dt><dd><code>{event.target_id}</code></dd><dt>{text.requestId}</dt><dd><code>{event.request_id}</code></dd></dl></details></td><td><code>{event.actor_id}</code></td><td>{event.outcome === 'allowed' ? text.allowed : text.denied}</td></tr>)}
      </tbody></table></div>}
      <PageControls previous={cursors.length > 1 ? () => setCursors(cursors.slice(0, -1)) : undefined} next={state.value.data.next_cursor ? () => setCursors([...cursors, state.value.data.next_cursor]) : undefined} />
    </>}
  </section>;
}
