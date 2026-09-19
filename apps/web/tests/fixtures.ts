import type { AccessPolicy, Audit, Project, Session } from '../src/api/types';

export const principalId = '00000000-0000-4000-8000-000000000001';
export const otherId = '00000000-0000-4000-8000-000000000002';
export const projectId = '10000000-0000-4000-8000-000000000001';
export const requestId = '20000000-0000-4000-8000-000000000001';
export const session: Session = { principal_id: principalId, display_name: 'Anna Testowa', can_create_project: true, csrf_token: 'a'.repeat(32) };
export const project: Project = { id: projectId, name: 'Kontrola ryzyka', description: 'Syntetyczny projekt testowy', acl_revision: 1, created_by: principalId, created_at: '2026-09-19T10:00:00Z', my_role: 'owner' };
export const policy: AccessPolicy = { project_id: projectId, revision: 1, members: [{ principal_id: principalId, role: 'owner' }] };
export const audit: Audit = { id: '30000000-0000-4000-8000-000000000001', project_id: projectId, actor_id: principalId, action: 'project.created', target_id: projectId, version_id: null, outcome: 'allowed', occurred_at: '2026-09-19T10:00:00Z', request_id: requestId };
export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => new Response(
  status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId, ...headers } },
);
export const problem = (status: number, code = 'unavailable', headers: Record<string, string> = {}, fields: { pointer: string; code: string }[] = []) =>
  json({ type: `urn:torii:problem:${code}`, title: 'Untrusted server title: secret-do-not-render', status, code, request_id: requestId, errors: fields }, status, headers);
