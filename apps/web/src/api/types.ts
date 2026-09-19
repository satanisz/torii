import type { components } from './generated';

export type Session = components['schemas']['Session'];
export type Project = components['schemas']['Project'];
export type ProjectCreate = components['schemas']['ProjectCreate'];
export type AccessPolicy = components['schemas']['AccessPolicy'];
export type AccessPolicyWrite = components['schemas']['AccessPolicyWrite'];
export type Member = AccessPolicy['members'][number];
export type Role = Member['role'];
export type Audit = components['schemas']['Audit'];
export type Page<T> = { items: T[]; next_cursor: string | null };

export const isUuid = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
const isString = (v: unknown, max: number, min = 0): v is string =>
  typeof v === 'string' && v.length >= min && v.length <= max;
const isRevision = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const isDate = (v: unknown) => isString(v, 40, 20) && Number.isFinite(Date.parse(v));
export const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const hasFields = (v: Record<string, unknown>, keys: string[]) =>
  keys.every((key) => Object.hasOwn(v, key)) && Object.keys(v).every((key) => keys.includes(key));
const isRole = (v: unknown): v is Role => v === 'reader' || v === 'editor' || v === 'owner';
const isMember = (v: unknown): v is Member =>
  isRecord(v) && hasFields(v, ['principal_id', 'role']) && isUuid(v.principal_id) && isRole(v.role);

export const isSession = (v: unknown): v is Session =>
  isRecord(v) && hasFields(v, ['principal_id', 'display_name', 'can_create_project', 'csrf_token']) &&
  isUuid(v.principal_id) && isString(v.display_name, 200, 1) && typeof v.can_create_project === 'boolean' &&
  (v.csrf_token === null || isString(v.csrf_token, 256, 32));
export const isProject = (v: unknown): v is Project =>
  isRecord(v) && hasFields(v, ['id', 'name', 'description', 'acl_revision', 'created_by', 'created_at', 'my_role']) &&
  isUuid(v.id) && isString(v.name, 120, 1) && v.name.trim() === v.name &&
  isString(v.description, 4000) && isRevision(v.acl_revision) && isUuid(v.created_by) &&
  isDate(v.created_at) && isRole(v.my_role);
export const isAccessPolicy = (v: unknown): v is AccessPolicy =>
  isRecord(v) && hasFields(v, ['project_id', 'revision', 'members']) &&
  isUuid(v.project_id) && isRevision(v.revision) && Array.isArray(v.members) &&
  v.members.length > 0 && v.members.length <= 100 && v.members.every(isMember) &&
  new Set(v.members.map((member) => member.principal_id)).size === v.members.length;
export const isAudit = (v: unknown): v is Audit =>
  isRecord(v) && hasFields(v, ['id', 'project_id', 'actor_id', 'action', 'target_id', 'version_id', 'outcome', 'occurred_at', 'request_id']) &&
  isUuid(v.id) && isUuid(v.project_id) && isUuid(v.actor_id) && isString(v.action, 64, 1) &&
  isUuid(v.target_id) && (v.version_id === null || isUuid(v.version_id)) &&
  (v.outcome === 'allowed' || v.outcome === 'denied') && isDate(v.occurred_at) && isUuid(v.request_id);
export const isPage = <T>(isItem: (item: unknown) => item is T) => (v: unknown): v is Page<T> =>
  isRecord(v) && hasFields(v, ['items', 'next_cursor']) && Array.isArray(v.items) &&
  v.items.length <= 100 && v.items.every(isItem) &&
  (v.next_cursor === null || isString(v.next_cursor, 2048, 1));
