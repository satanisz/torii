import { useCallback, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from './api/client';
import type { ApiResult } from './api/client';
import { isUuid } from './api/types';
import type { AccessPolicy, AccessPolicyWrite, Member, Project, Role } from './api/types';
import { ErrorPanel, Field, Loading } from './components';
import { roles, text } from './i18n/pl';
import { useDirtyGuard, useMutationFailure, useRead, useRetryReady, useSession } from './state';

type Props = { project: Project; onDenied: (error: ApiError) => void };
export function AccessEditor({ project, onDenied }: Props) {
  const load = useCallback((signal: AbortSignal) => api.access(project.id, signal), [project.id]);
  const { state, reload } = useRead(load, onDenied);
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} />;
  return <PolicyForm project={project} onDenied={onDenied} initial={state.value} />;
}

const fingerprint = (members: Member[]) => JSON.stringify([...members].sort((a, b) => a.principal_id.localeCompare(b.principal_id)));
const aclEtag = (result: ApiResult<AccessPolicy>): string | null =>
  result.etag === `"acl:${result.data.project_id}:${result.data.revision}"` ? result.etag : null;

function PolicyForm({ project, onDenied, initial }: Props & { initial: ApiResult<AccessPolicy> }) {
  const { session } = useSession();
  const fail = useMutationFailure(onDenied);
  const [base, setBase] = useState(initial);
  const [members, setMembers] = useState<Member[]>(initial.data.members);
  const [newId, setNewId] = useState('');
  const [newRole, setNewRole] = useState<Role>('reader');
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [error, setError] = useState<ApiError | null>(aclEtag(initial) ? null : new ApiError(0, 'unexpected_response', initial.requestId));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<ApiResult<AccessPolicy> | null>(null);
  const [pending, setPending] = useState<{ body: AccessPolicyWrite; key: string; etag: string } | null>(null);
  const retryReady = useRetryReady(error);
  const inFlight = useRef(false);
  const dirty = fingerprint(members) !== fingerprint(base.data.members) || Boolean(newId);
  useDirtyGuard(dirty || Boolean(pending));

  function addMember() {
    if (!isUuid(newId) || members.some((member) => member.principal_id.toLowerCase() === newId.toLowerCase()) || members.length >= 100) { setFieldError(text.invalidMember); return; }
    setMembers([...members, { principal_id: newId.toLowerCase(), role: newRole }]); setNewId(''); setFieldError(undefined); setSaved(false);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || conflict || !retryReady) return;
    if (!members.some((member) => member.role === 'owner')) { setFieldError(text.needOwner); return; }
    if (!session.csrf_token) { setError(new ApiError(401, 'missing_csrf')); return; }
    const etag = aclEtag(base);
    if (!etag) { setError(new ApiError(0, 'unexpected_response')); return; }
    const mutation = pending ?? { body: { members }, key: crypto.randomUUID(), etag };
    inFlight.current = true; setSaving(true); setSaved(false); setError(null); setFieldError(undefined);
    try {
      const result = await api.saveAccess(project.id, mutation.body, session.csrf_token, mutation.etag, mutation.key);
      const freshProject = await api.project(project.id);
      if (freshProject.data.my_role !== 'owner') { onDenied(new ApiError(403, 'forbidden')); return; }
      if (!aclEtag(result)) throw new ApiError(0, 'unexpected_response', result.requestId);
      setBase(result); setMembers(result.data.members); setPending(null); setSaved(true);
    } catch (cause) {
      const problem = fail(cause); setError(problem);
      if (problem.status === 412) { setConflict(true); setLatest(null); }
      if (problem.status === 0 || problem.status >= 500) setPending(mutation);
      else setPending(null);
      if (problem.status === 422) setFieldError(text.invalidPolicy);
    } finally { inFlight.current = false; setSaving(false); }
  }
  async function compare() {
    if (inFlight.current) return;
    inFlight.current = true; setSaving(true); setError(null);
    try {
      const freshProject = await api.project(project.id);
      if (freshProject.data.my_role !== 'owner') { onDenied(new ApiError(403, 'forbidden')); return; }
      const result = await api.access(project.id);
      if (!aclEtag(result)) throw new ApiError(0, 'unexpected_response', result.requestId);
      setLatest(result);
    } catch (cause) { setError(fail(cause)); }
    finally { inFlight.current = false; setSaving(false); }
  }
  const locked = saving || Boolean(pending) || conflict;
  return <section aria-labelledby="access-title"><h2 id="access-title">{text.access}</h2><p className="section-intro">{text.accessIntro}</p>
    <form className="panel" onSubmit={save}>
      <div className="section-heading"><h3>{text.members}</h3><span className="small">{text.revision} {base.data.revision}{dirty ? ` · ${text.dirty}` : ''}</span></div>
      <fieldset disabled={locked}><div className="table-scroll"><table><caption className="sr-only">{text.members}</caption><thead><tr><th>{text.principalId}</th><th>{text.memberRole}</th><th><span className="sr-only">{text.remove}</span></th></tr></thead><tbody>
        {members.map((member, index) => <tr key={member.principal_id}><td><code>{member.principal_id}</code></td><td><select aria-label={`${text.memberRole}: ${member.principal_id}`} value={member.role} onChange={(event) => { setMembers(members.map((row, i) => i === index ? { ...row, role: event.target.value as Role } : row)); setSaved(false); }}>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td><td><button className="text-button danger-text" type="button" aria-label={`${text.remove}: ${member.principal_id}`} onClick={() => { setMembers(members.filter((_, i) => i !== index)); setSaved(false); }}>{text.remove}</button></td></tr>)}
      </tbody></table></div>
      <div className="add-member"><Field id="new-principal" label={text.principalId} error={fieldError}><input id="new-principal" value={newId} onChange={(event) => setNewId(event.target.value)} maxLength={36} spellCheck={false} autoComplete="off" aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? 'new-principal-error' : undefined} /></Field><Field id="new-role" label={text.memberRole}><select id="new-role" value={newRole} onChange={(event) => setNewRole(event.target.value as Role)}>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><button className="secondary" type="button" onClick={addMember} disabled={members.length >= 100}>{text.addMember}</button></div>
      <p className="hint">{text.memberLimit}</p></fieldset>
      {error && <ErrorPanel error={error} />}
      {pending && <p className="notice warning">{text.uncertain}</p>}
      {saved && <p className="notice success" role="status">{text.saved}</p>}
      {!conflict && <div className="actions"><button type="submit" disabled={saving || (!dirty && !pending) || !session.csrf_token || !aclEtag(base) || !retryReady}>{saving ? text.saving : pending ? text.retryWrite : text.save}</button></div>}
    </form>
    {conflict && <section className="notice warning" aria-labelledby="conflict-title"><h3 id="conflict-title">{text.conflictTitle}</h3><p>{text.conflictIntro}</p>
      {!latest && <button className="secondary" onClick={compare} disabled={saving}>{saving ? text.loading : text.compare}</button>}
      {latest && <><div className="comparison"><PolicySnapshot title={text.localChanges} members={members} /><PolicySnapshot title={`${text.serverChanges} · ${text.revision} ${latest.data.revision}`} members={latest.data.members} /></div><p>{text.mergeHint}</p><div className="actions"><button className="secondary" onClick={() => { setBase(latest); setConflict(false); setLatest(null); setError(null); }}>{text.merge}</button><button className="secondary" onClick={() => { setBase(latest); setMembers(latest.data.members); setNewId(''); setConflict(false); setLatest(null); setError(null); }}>{text.discard}</button></div></>}
    </section>}
  </section>;
}

function PolicySnapshot({ title, members }: { title: string; members: Member[] }) {
  return <section><h4>{title}</h4><ul>{members.map((member) => <li key={member.principal_id}><code>{member.principal_id}</code><span>{roles[member.role]}</span></li>)}</ul></section>;
}
