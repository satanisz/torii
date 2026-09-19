import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { text } from '../src/i18n/pl';
import { audit, json, otherId, policy, principalId, problem, project, projectId, requestId, session } from './fixtures';

type Handler = (path: string, init: RequestInit) => Response | Promise<Response> | undefined;
function renderApp(path = '/projects', handler: Handler = () => undefined) {
  const fetcher = vi.fn(async (input: string, init: RequestInit) => {
    const result = handler(input, init);
    if (result !== undefined) return await result;
    if (input === '/api/v1/session') return json(session);
    if (input.startsWith('/api/v1/projects?')) return json({ items: [project], next_cursor: null });
    if (input === `/api/v1/projects/${projectId}`) return json(project);
    if (input === `/api/v1/projects/${projectId}/access-policy`) return json(policy, 200, { ETag: `"acl:${projectId}:1"` });
    if (input.startsWith(`/api/v1/projects/${projectId}/audit?`)) return json({ items: [audit], next_cursor: null });
    throw new Error(`Unexpected fixture path ${input}`);
  });
  vi.stubGlobal('fetch', fetcher);
  const router = createMemoryRouter([{ path: '*', element: <App /> }], { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return { fetcher, router, user: userEvent.setup() };
}

describe('SPEC-0017 AC-01/02/04/07/08 SP-01 component behavior (mock API)', () => {
  it('renders only the OIDC entry for an anonymous user, without local password inputs', async () => {
    renderApp('/login?error=do-not-echo-secret', (path) => path === '/api/v1/session' ? problem(401) : undefined);
    expect(await screen.findByRole('link', { name: /Zaloguj przez OIDC/ })).toHaveAttribute('href', '/auth/login');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(text.loginError);
    expect(document.body).not.toHaveTextContent('do-not-echo-secret');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('shows accessible projects and never offers undelivered module actions', async () => {
    renderApp();
    expect(await screen.findByRole('link', { name: project.name })).toHaveAttribute('href', `/projects/${projectId}`);
    expect(screen.getByText(text.environment)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run|Flow|Model|Eksperyment/i })).not.toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: text.navigation })).toBeInTheDocument();
  });

  it('hides create without its grant and owner navigation for a reader', async () => {
    const { fetcher } = renderApp(`/projects/${projectId}/access`, (path) => {
      if (path === '/api/v1/session') return json({ ...session, can_create_project: false });
      if (path === `/api/v1/projects/${projectId}`) return json({ ...project, my_role: 'reader' });
      return undefined;
    });
    expect(await screen.findByRole('heading', { name: text.forbiddenTitle })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: text.access })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: text.audit })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([path]) => path.endsWith('/access-policy'))).toBe(false);
  });

  it('creates a project only after successful server confirmation', async () => {
    const { user, fetcher } = renderApp('/projects', (path, init) => path === '/api/v1/projects' && init.method === 'POST' ? json({ ...project, name: 'Nowy projekt' }, 201) : undefined);
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Nowy projekt');
    await user.click(screen.getAllByRole('button', { name: text.createProject })[0]!);
    expect(await screen.findByRole('link', { name: 'Nowy projekt' })).toBeInTheDocument();
    const call = fetcher.mock.calls.find(([path, init]) => path === '/api/v1/projects' && init.method === 'POST');
    expect(JSON.parse(call![1].body as string)).toEqual({ name: 'Nowy projekt', description: '' });
    expect(new Headers(call![1].headers).get('Idempotency-Key')).toMatch(/^[\da-f-]{36}$/);
  });

  it('maps 422 pointer to the field, with safe request ID and no arbitrary server title', async () => {
    const { user } = renderApp('/projects', (path, init) => path === '/api/v1/projects' && init.method === 'POST' ? problem(422, 'validation_failed', {}, [{ pointer: '/name', code: 'invalid' }]) : undefined);
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Projekt');
    await user.click(screen.getByRole('button', { name: text.createProject }));
    expect(await screen.findByText(text.invalidField)).toBeInTheDocument();
    expect(screen.getByLabelText(text.name)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent(requestId);
    expect(document.body).not.toHaveTextContent('secret-do-not-render');
  });

  it('retries an uncertain create with the exact same body/key and locks editing meanwhile', async () => {
    let writes = 0;
    const { user, fetcher } = renderApp('/projects', (path, init) => {
      if (path !== '/api/v1/projects' || init.method !== 'POST') return undefined;
      writes++;
      return writes === 1 ? Promise.reject(new TypeError('connection lost')) : json({ ...project, name: 'Niepewny zapis' }, 201);
    });
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Niepewny zapis');
    await user.click(screen.getByRole('button', { name: text.createProject }));
    expect(await screen.findByText(text.uncertain)).toBeInTheDocument();
    expect(screen.getByLabelText(text.name)).toBeDisabled();
    await user.click(screen.getByRole('button', { name: text.retryWrite }));
    expect(await screen.findByRole('link', { name: 'Niepewny zapis' })).toBeInTheDocument();
    const calls = fetcher.mock.calls.filter(([path, init]) => path === '/api/v1/projects' && init.method === 'POST');
    expect(calls).toHaveLength(2);
    expect(calls[0]![1].body).toBe(calls[1]![1].body);
    expect(new Headers(calls[0]![1].headers).get('Idempotency-Key')).toBe(new Headers(calls[1]![1].headers).get('Idempotency-Key'));
  });

  it('warns before navigating away from an unsaved form', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user, router } = renderApp();
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Niezapisany projekt');
    await user.click(screen.getByRole('link', { name: project.name }));
    expect(confirm).toHaveBeenCalledWith(text.dirtyPrompt);
    expect(router.state.location.pathname).toBe('/projects');
    expect(screen.getByLabelText(text.name)).toHaveValue('Niezapisany projekt');
  });

  it('also warns before logout discards an unsaved form', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user, fetcher } = renderApp();
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Niezapisany projekt');
    await user.click(screen.getByRole('button', { name: text.logout }));
    expect(confirm).toHaveBeenCalledWith(text.dirtyPrompt);
    expect(screen.getByLabelText(text.name)).toHaveValue('Niezapisany projekt');
    expect(fetcher.mock.calls.some(([path]) => path.endsWith('/logout'))).toBe(false);
  });

  it('reactivates an uncertain-write retry when Retry-After expires, without unrelated form edits', async () => {
    const { user } = renderApp('/projects', (path, init) => path === '/api/v1/projects' && init.method === 'POST' ? problem(503, 'unavailable', { 'Retry-After': '10' }) : undefined);
    await user.click(await screen.findByRole('button', { name: text.createProject }));
    await user.type(screen.getByLabelText(text.name), 'Projekt');
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    try {
      await user.click(screen.getByRole('button', { name: text.createProject }));
      await act(async () => { await Promise.resolve(); });
      const retry = screen.getByRole('button', { name: text.retryWrite });
      expect(retry).toBeDisabled();
      expect(screen.getByLabelText(text.name)).toBeDisabled();
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(retry).toBeEnabled();
    } finally { vi.useRealTimers(); }
  });

  it('clears project/session content on a 401 without replaying writes', async () => {
    const { fetcher } = renderApp(`/projects/${projectId}`, (path) => path === `/api/v1/projects/${projectId}` ? problem(401, 'unauthenticated') : undefined);
    expect(await screen.findByText(text.sessionExpired)).toBeInTheDocument();
    expect(screen.queryByText(session.display_name)).not.toBeInTheDocument();
    expect(screen.queryByText(project.name)).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([, init]) => init.method !== 'GET')).toHaveLength(0);
    expect(localStorage.length).toBe(0);
  });

  it('removes sensitive views even when logout cannot be confirmed; explicit retry stays available', async () => {
    let writes = 0;
    const { user } = renderApp('/projects', (path) => {
      if (path !== '/api/v1/session/logout') return undefined;
      return ++writes === 1 ? Promise.reject(new TypeError('network')) : json(undefined, 204);
    });
    await screen.findByRole('link', { name: project.name });
    await user.click(screen.getByRole('button', { name: text.logout }));
    expect(await screen.findByText(text.logoutFailed)).toBeInTheDocument();
    expect(screen.queryByText(project.name)).not.toBeInTheDocument();
    expect(screen.queryByText(session.display_name)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: text.retry }));
    expect(await screen.findByRole('link', { name: /Zaloguj przez OIDC/ })).toBeInTheDocument();
  });

  it('shows a minimal paginated audit history', async () => {
    renderApp(`/projects/${projectId}/audit`);
    expect(await screen.findByText('Utworzenie projektu')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: text.audit })).toHaveTextContent(principalId);
    expect(screen.queryByText('Syntetyczny payload definicji')).not.toBeInTheDocument();
  });
});

describe('SPEC-0001 access policy and SPEC-0017 conflict/revocation UI', () => {
  it('sends owner access update with the received ETag, and refuses removal of the last owner locally', async () => {
    const { user, fetcher } = renderApp(`/projects/${projectId}/access`, (path, init) => {
      if (path.endsWith('/access-policy') && init.method === 'PUT') return json({ ...policy, revision: 2, members: [...policy.members, { principal_id: otherId, role: 'reader' }] }, 200, { ETag: `"acl:${projectId}:2"` });
      return undefined;
    });
    const memberInput = await screen.findByLabelText(text.principalId);
    await user.type(memberInput, otherId);
    await user.click(screen.getByRole('button', { name: text.addMember }));
    await user.click(screen.getByRole('button', { name: text.save }));
    expect(await screen.findByText(text.saved)).toBeInTheDocument();
    const writes = fetcher.mock.calls.filter(([, init]) => init.method === 'PUT');
    expect(writes).toHaveLength(1);
    expect(new Headers(writes[0]![1].headers).get('If-Match')).toBe(`"acl:${projectId}:1"`);
    await user.click(screen.getByRole('button', { name: `${text.remove}: ${principalId}` }));
    await user.click(screen.getByRole('button', { name: text.save }));
    expect(await screen.findByText(text.needOwner)).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([, init]) => init.method === 'PUT')).toHaveLength(1);
  });

  it('preserves edits on 412, reauthorizes before comparison, and never automatically force-saves', async () => {
    let reads = 0;
    const serverId = '00000000-0000-4000-8000-000000000003';
    const { user, fetcher } = renderApp(`/projects/${projectId}/access`, (path, init) => {
      if (!path.endsWith('/access-policy')) return undefined;
      if (init.method === 'PUT') return problem(412, 'revision_conflict');
      if (++reads > 1) return json({ ...policy, revision: 2, members: [...policy.members, { principal_id: serverId, role: 'editor' }] }, 200, { ETag: `"acl:${projectId}:2"` });
      return undefined;
    });
    await user.type(await screen.findByLabelText(text.principalId), otherId);
    await user.click(screen.getByRole('button', { name: text.addMember }));
    await user.click(screen.getByRole('button', { name: text.save }));
    expect(await screen.findByText(text.conflictTitle)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: text.members })).toHaveTextContent(otherId);
    await user.click(screen.getByRole('button', { name: text.compare }));
    expect(await screen.findByText(`${text.serverChanges} · ${text.revision} 2`)).toBeInTheDocument();
    expect(screen.getByText(serverId)).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([path]) => path === `/api/v1/projects/${projectId}`)).toHaveLength(2);
    expect(fetcher.mock.calls.filter(([, init]) => init.method === 'PUT')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: text.merge }));
    expect(screen.getByRole('button', { name: text.save })).toBeEnabled();
    expect(fetcher.mock.calls.filter(([, init]) => init.method === 'PUT')).toHaveLength(1);
  });

  it('discards the project and comparison after a grant is revoked', async () => {
    let projectsRead = 0;
    const { user } = renderApp(`/projects/${projectId}/access`, (path, init) => {
      if (path === `/api/v1/projects/${projectId}` && ++projectsRead > 1) return problem(404, 'not_found');
      if (path.endsWith('/access-policy') && init.method === 'PUT') return problem(412, 'revision_conflict');
      return undefined;
    });
    await user.type(await screen.findByLabelText(text.principalId), otherId);
    await user.click(screen.getByRole('button', { name: text.addMember }));
    await user.click(screen.getByRole('button', { name: text.save }));
    await user.click(await screen.findByRole('button', { name: text.compare }));
    expect(await screen.findByText(text.notFound)).toBeInTheDocument();
    expect(screen.queryByText(project.name)).not.toBeInTheDocument();
    expect(screen.queryByText(otherId)).not.toBeInTheDocument();
    expect(screen.queryByText(principalId)).not.toBeInTheDocument();
  });

  it('disables policy writes if the server omits its strong ETag', async () => {
    const { user } = renderApp(`/projects/${projectId}/access`, (path) => path.endsWith('/access-policy') ? json(policy) : undefined);
    await user.type(await screen.findByLabelText(text.principalId), otherId);
    await user.click(screen.getByRole('button', { name: text.addMember }));
    expect(screen.getByRole('button', { name: text.save })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent(text.unexpected);
  });

  it('does not redisplay a denied project while a fresh authorization retry is pending', async () => {
    let reads = 0;
    let finishRetry: ((response: Response) => void) | undefined;
    const { user, fetcher } = renderApp(`/projects/${projectId}/access`, (path, init) => {
      if (path === `/api/v1/projects/${projectId}`) {
        reads++;
        if (reads === 2) return problem(404, 'not_found');
        if (reads === 3) return new Promise<Response>((resolve) => { finishRetry = resolve; });
      }
      if (path.endsWith('/access-policy') && init.method === 'PUT') return problem(412, 'revision_conflict');
      return undefined;
    });
    await user.type(await screen.findByLabelText(text.principalId), otherId);
    await user.click(screen.getByRole('button', { name: text.addMember }));
    await user.click(screen.getByRole('button', { name: text.save }));
    await user.click(await screen.findByRole('button', { name: text.compare }));
    await screen.findByText(text.notFound);
    const accessReads = fetcher.mock.calls.filter(([path]) => path.endsWith('/access-policy')).length;
    await user.click(screen.getByRole('button', { name: text.retry }));
    expect(screen.getByRole('status')).toHaveTextContent(text.loading);
    expect(screen.queryByText(project.name)).not.toBeInTheDocument();
    expect(screen.queryByText(otherId)).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([path]) => path.endsWith('/access-policy'))).toHaveLength(accessReads);
    await act(async () => { finishRetry?.(problem(404, 'not_found')); await Promise.resolve(); });
    expect(await screen.findByText(text.notFound)).toBeInTheDocument();
  });

  it('supports project pagination and resets the cursor when filtering', async () => {
    const { user, fetcher } = renderApp('/projects', (path) => path.startsWith('/api/v1/projects?') ? json({ items: [project], next_cursor: path.includes('cursor') ? null : 'cursor-second' }) : undefined);
    await user.click(await screen.findByRole('button', { name: text.next }));
    await waitFor(() => expect(fetcher.mock.calls.some(([path]) => path.includes('cursor=cursor-second'))).toBe(true));
    await user.type(screen.getByRole('searchbox', { name: text.search }), 'ryzyko');
    await user.click(screen.getByRole('button', { name: text.searchAction }));
    await waitFor(() => expect(fetcher.mock.calls.some(([path]) => path === '/api/v1/projects?limit=25&q=ryzyko')).toBe(true));
    const filter = screen.getByRole('search');
    expect(within(filter).getByRole('button', { name: text.clearFilter })).toBeInTheDocument();
  });
});
