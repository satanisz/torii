// SPEC-0018 D01–D05: component/contract tests, not a substitute for real browser acceptance.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { DemoApp } from '../src/demo/DemoApp';
import { demoRequest } from '../src/demo/api';
import type { DemoObject, DemoState, Run } from '../src/demo/types';

const project = { id: 'project-a', name: 'Prognoza sprzedaży', created_at: '2026-09-19' };
const dataset: DemoObject = {
  id: 'data-a', project_id: project.id, kind: 'dataset', name: 'Sprzedaż', created_at: '2026-09-19',
  versions: [1, 2].map(number => ({
    id: `data-v${String(number)}`, number, definition: { source: 'csv' }, sha256: 'a'.repeat(64), created_at: '2026-09-19',
    summary: {
      columns: ['reklama', 'sprzedaz'], row_count: 40,
      profile: ['reklama', 'sprzedaz'].map(name => ({ name, dtype: 'number', missing: 0, unique: 40, min: 1, max: 40, mean: 20.5 })),
      preview: [{ reklama: number, sprzedaz: 10 }],
    },
  })),
};
const model: DemoObject = {
  id: 'model-a', project_id: project.id, kind: 'model', name: 'Model sprzedaży', created_at: '2026-09-19',
  versions: [{ id: 'model-v1', number: 1, definition: { task: 'regression', algorithm: 'linear', target: 'sprzedaz', features: ['reklama'], alpha: 1, seed: 42, test_size: 0.25 }, sha256: 'b'.repeat(64), created_at: '2026-09-19', summary: {} }],
};
const run: Run = {
  id: 'run-a', project_id: project.id, dataset_version_id: 'data-v2', model_version_id: 'model-v1', status: 'succeeded', error: null,
  target: 'sprzedaz', seed: 42, test_size: 0.25, created_at: '2026-09-19',
  result: { metrics: { mae: 1.25, rmse: 1.5, r2: 0.95 }, importance: [{ feature: 'reklama', value: -2 }], predictions: [{ actual: 10, predicted: 9 }], train_rows: 30, test_rows: 10, algorithm: 'linear', mlflow_run_id: 'mlflow-actual-id', environment: { python: '3.12' } },
};

function state(objects: DemoObject[] = [], runs: Run[] = []): DemoState {
  return { mode: 'local-demo', projects: [project], objects, runs };
}

function server(initial: DemoState, mutate?: (path: string, body: Record<string, unknown>, value: DemoState) => unknown) {
  const value = structuredClone(initial);
  const fetcher = vi.fn((input: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as Record<string, unknown>;
      return Promise.resolve(new Response(JSON.stringify(mutate?.(input, body, value) ?? {}), { status: 201 }));
    }
    return Promise.resolve(new Response(JSON.stringify(value)));
  });
  vi.stubGlobal('fetch', fetcher);
  return { value, fetcher };
}

test('shows honest local demo branding and an empty project onboarding', async () => {
  server({ mode: 'local-demo', projects: [], objects: [], runs: [] });
  render(<DemoApp />);
  expect(await screen.findByRole('heading', { name: /Od danych\s*do decyzji\./ })).toBeInTheDocument();
  expect(screen.getByText(/bez SSO/)).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Torii' })).toHaveAttribute('src', '/torii-logo.jpg');
  expect(screen.getByText(/Nie używaj danych firmowych/)).toBeInTheDocument();
});

test('creates a project with the required demo header and selects it', async () => {
  const { fetcher } = server({ mode: 'local-demo', projects: [], objects: [], runs: [] }, (path, body, value) => {
    expect(path).toBe('/demo-api/projects');
    const created = { ...project, name: String(body.name) };
    value.projects.push(created);
    return created;
  });
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.type(await screen.findByLabelText('Nazwa projektu'), 'Popyt');
  await user.click(screen.getByRole('button', { name: 'Utwórz projekt' }));
  expect(await screen.findByRole('heading', { name: 'Popyt' })).toBeInTheDocument();
  expect(fetcher.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.headers).toMatchObject({ 'X-Torii-Demo': '1' });
});

test('loads immutable versions and their actual preview/profile', async () => {
  server(state([dataset]));
  const user = userEvent.setup();
  render(<DemoApp />);
  const selector = await screen.findByLabelText('Wersja danych');
  expect(selector).toHaveValue('data-v2');
  expect(screen.getByRole('table', { name: 'Profil kolumn' })).toHaveTextContent('20,5');
  await user.selectOptions(selector, 'data-v1');
  expect(screen.getByRole('table', { name: 'Podgląd danych' })).toHaveTextContent('1');
  expect(screen.getByRole('link', { name: 'Pobierz CSV' })).toHaveAttribute('href', '/demo-api/datasets/data-v1/csv');
});

test('imports CSV as a new immutable version, without paths or raw form uploads', async () => {
  const { fetcher } = server(state([dataset]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await screen.findByLabelText('Wersja danych');
  await user.selectOptions(screen.getByLabelText('Sposób importu'), 'data-a');
  await user.upload(screen.getByLabelText('Plik CSV'), new File(['x,y\n1,2'], 'data.csv', { type: 'text/csv' }));
  await user.click(screen.getByRole('button', { name: 'Importuj CSV' }));
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
  const posted = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(JSON.parse(posted?.[1]?.body as string)).toEqual({ name: 'Sprzedaż', format: 'csv', content_base64: 'eCx5CjEsMg==', object_id: 'data-a' });
});

test('separates declaring a transformation from executing it and shows lineage', async () => {
  const transform: DemoObject = { id: 'transform-a', project_id: project.id, kind: 'transformation', name: 'Bez braków', created_at: '2026-09-19', versions: [{ id: 'transform-v1', number: 1, definition: { input_version_id: 'data-v2', operation: 'drop_missing' }, sha256: 'c'.repeat(64), created_at: '2026-09-19', summary: {} }] };
  const { fetcher } = server(state([dataset]), (path, _body, value) => {
    if (path.endsWith('/transformations')) { value.objects.push(transform); return transform; }
    const output = structuredClone(dataset);
    output.id = 'output'; output.name = 'Dane po transformacji';
    output.versions = [{ ...output.versions[0]!, id: 'output-v1', definition: { source: 'transformation', input_version_id: 'data-v2', transformation_version_id: 'transform-v1' } }];
    value.objects.push(output);
    return output;
  });
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Transformacje/ }));
  await user.type(screen.getByLabelText('Nazwa transformacji'), 'Bez braków');
  await user.click(screen.getByRole('button', { name: 'Zapisz transformację' }));
  expect(await screen.findByRole('button', { name: 'Wykonaj Bez braków' })).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  await user.click(screen.getByRole('button', { name: 'Wykonaj Bez braków' }));
  expect(await screen.findByText('Dane po transformacji', { selector: 'h2' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Źródło: Sprzedaż · v2/ })).toBeInTheDocument();
});

test('model form excludes target from features and posts a real Ridge definition', async () => {
  const { fetcher } = server(state([dataset]), (_path, _body, value) => { value.objects.push(model); return model; });
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Modele/ }));
  await user.type(screen.getByLabelText('Nazwa modelu'), 'Model sprzedaży');
  await user.selectOptions(screen.getByLabelText('Zmienna celu'), 'sprzedaz');
  expect(screen.queryByRole('checkbox', { name: 'sprzedaz' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Zapisz model' }));
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
  expect(JSON.parse(fetcher.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body as string)).toEqual({ name: 'Model sprzedaży', task: 'regression', algorithm: 'linear', target: 'sprzedaz', features: ['reklama'], alpha: 1 });
});

test('presents persisted metrics, signed coefficients, MLflow ID and safe artifact links', async () => {
  server(state([dataset, model], [run]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  expect(screen.getByRole('table', { name: 'Porównanie eksperymentów' })).toHaveTextContent('0,95');
  expect(screen.getByText('mlflow-actual-id')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Współczynniki Ridge' })).toHaveTextContent('-2');
  expect(screen.getByText(/nie przyczynowość/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Pobierz model' })).toHaveAttribute('href', '/demo-api/runs/run-a/artifacts/model.joblib');
});

test('warns when comparison uses different dataset versions', async () => {
  server(state([dataset, model], [run, { ...run, id: 'run-b', dataset_version_id: 'data-v1' }]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  expect(screen.getByText(/Różne wersje danych lub zmienne celu/)).toBeInTheDocument();
});

test('polls queued runs to completion without fabricated metrics', async () => {
  const { value } = server(state([dataset, model], [{ ...run, status: 'running', result: null }]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  expect(screen.getByRole('button', { name: 'Uruchom eksperyment' })).toBeDisabled();
  expect(screen.queryByText('mlflow-actual-id')).not.toBeInTheDocument();
  value.runs = [run];
  expect(await screen.findByText('mlflow-actual-id', {}, { timeout: 3500 })).toBeInTheDocument();
});

test('shows recoverable state errors and never silently invents projects', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Magazyn niedostępny.' }), { status: 503 }))));
  render(<DemoApp />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Magazyn niedostępny.');
  expect(screen.getByRole('button', { name: 'Odśwież' })).toBeInTheDocument();
});

test('rejects invalid/oversized CSV selection before a request', async () => {
  const { fetcher } = server(state([dataset]));
  render(<DemoApp />);
  await screen.findByLabelText('Plik CSV');
  const file = new File(['x'], 'huge.csv', { type: 'text/csv' });
  Object.defineProperty(file, 'size', { value: 6 * 1024 * 1024 });
  fireEvent.change(screen.getByLabelText('Plik CSV'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Importuj CSV' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/5 MiB/);
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
});

test('navigation stays scoped to the selected project', async () => {
  const initial = state([dataset, model], [run]);
  initial.projects.push({ ...project, id: 'project-b', name: 'Drugi projekt' });
  server(initial);
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: 'Drugi projekt' }));
  await user.click(screen.getByRole('button', { name: /Eksperymenty/ }));
  expect(screen.queryByText('mlflow-actual-id')).not.toBeInTheDocument();
  expect(within(screen.getByRole('main')).queryByText('Sprzedaż')).not.toBeInTheDocument();
});

test('API errors with non-JSON bodies use a safe fixed message', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>private traceback</html>', { status: 500 }))));
  await expect(demoRequest('/state')).rejects.toThrow('Usługa demonstracyjna jest niedostępna.');
});

test('an older refresh cannot overwrite a newly completed experiment', async () => {
  const pending = state([dataset, model], [{ ...run, status: 'running', result: null }]);
  let release: ((response: Response) => void) | undefined;
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn(() => {
    calls += 1;
    if (calls === 2) return new Promise<Response>(resolve => { release = resolve; });
    return Promise.resolve(new Response(JSON.stringify(calls === 1 ? pending : state([dataset, model], [run]))));
  }));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  await user.click(screen.getByRole('button', { name: 'Odśwież' }));
  await user.click(screen.getByRole('button', { name: 'Odśwież' }));
  expect(await screen.findByText('mlflow-actual-id')).toBeInTheDocument();
  await act(async () => { release?.(new Response(JSON.stringify(pending))); await Promise.resolve(); });
  expect(screen.getByText('mlflow-actual-id')).toBeInTheDocument();
});

test('starts a run using concrete model and dataset versions', async () => {
  const { fetcher } = server(state([dataset, model]), (_path, _body, value) => {
    const queued = { ...run, status: 'queued' as const, result: null };
    value.runs.push(queued);
    return queued;
  });
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  await user.click(screen.getByRole('button', { name: 'Uruchom eksperyment' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Uruchom eksperyment' })).toBeDisabled());
  const posted = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(posted?.[0]).toBe('/demo-api/projects/project-a/runs');
  expect(JSON.parse(posted?.[1]?.body as string)).toEqual({ model_version_id: 'model-v1', dataset_version_id: 'data-v2' });
  expect(screen.queryByRole('link', { name: 'Pobierz model' })).not.toBeInTheDocument();
});

test('a failed run has no fabricated metrics or model download', async () => {
  server(state([dataset, model], [{ ...run, status: 'failed', result: null, error: 'Braki w kolumnie celu.' }]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  expect(screen.getByRole('alert')).toHaveTextContent('Braki w kolumnie celu.');
  expect(screen.queryByText('mlflow-actual-id')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Pobierz model' })).not.toBeInTheDocument();
});

test('changing a data version resets the model form to its real columns', async () => {
  const other = structuredClone(dataset);
  other.id = 'data-b'; other.name = 'Inne dane';
  other.versions = [{ ...other.versions[0]!, id: 'different-v1', summary: { columns: ['wiek', 'koszt'], row_count: 50, preview: [], profile: ['wiek', 'koszt'].map(name => ({ name, dtype: 'number', missing: 0, unique: 50, min: 1, max: 50, mean: 25 })) } }];
  server(state([dataset, other]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Modele/ }));
  await user.selectOptions(screen.getByLabelText('Wersja danych'), 'different-v1');
  expect(screen.getByLabelText('Zmienna celu')).toHaveValue('koszt');
  expect(screen.getByRole('checkbox', { name: 'wiek' })).toBeChecked();
  expect(screen.queryByRole('checkbox', { name: 'reklama' })).not.toBeInTheDocument();
});

test('baseline analysis explicitly has no feature coefficients', async () => {
  server(state([dataset, model], [{ ...run, result: { ...run.result!, importance: [], algorithm: 'dummy' } }]));
  const user = userEvent.setup();
  render(<DemoApp />);
  await user.click(await screen.findByRole('button', { name: /Eksperymenty/ }));
  expect(screen.getByText(/nie ma współczynników cech/)).toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Współczynniki Ridge' })).not.toBeInTheDocument();
});
