// SPEC-0019 F06: transport, scenario controls, truthful results and project isolation.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { Finance } from '../src/demo/Finance';
import type { FinanceRun } from '../src/demo/finance-types';

const snapshot = {
  as_of: '2026-09-30', currency: 'PLN' as const,
  positions: [{ id: 'loan', name: 'Kredyty zmienne', gl_account: '1100', side: 'asset' as const, balance_pln: 1000000, annual_rate: 0.06, rate_type: 'floating' as const, repricing_month: 1, deposit_beta_applies: false, rate_floor: 0 }],
  ledger: [{ gl_account: '1100', side: 'asset' as const, balance_pln: 1000000 }], history: [],
};
const scenario = { shock_bps: 100, deposit_beta: 0.35, inject_issues: false };
const manifest = { engine_version: 'nii-1', engine_sha256: 'e'.repeat(64), input_sha256: 'a'.repeat(64), scenario_sha256: 'b'.repeat(64) };
const totals = { income_base_pln: 60000, expense_base_pln: 20000, nii_base_pln: 40000, income_scenario_pln: 70000, expense_scenario_pln: 23500, nii_scenario_pln: 46500, delta_nii_pln: 6500 };
const run: FinanceRun = {
  id: 'finance-a', project_id: 'project-a', status: 'succeeded', created_at: '2026-10-09T12:00:00Z', snapshot, scenario, manifest, error: null,
  result: {
    snapshot, scenario, manifest, assumptions: ['Stałe salda; ACT/365F.'], quality_status: 'passed', totals,
    reconciliation: [{ gl_account: '1100', side: 'asset', portfolio_pln: 1000000, ledger_pln: 1000000, difference_pln: 0, status: 'matched' }],
    anomalies: [], monthly: [{ month: '2026-10', ...totals }],
    contributions: [{ position_id: 'loan', name: 'Kredyty zmienne', side: 'asset', balance_pln: 1000000, rate_type: 'floating', repricing_month: 1, base_interest_pln: 60000, scenario_interest_pln: 70000, delta_nii_pln: 10000, monthly: [{ month: '2026-10', base_rate: 0.06, scenario_rate: 0.07, base_interest_pln: 60000, scenario_interest_pln: 70000 }] }],
  },
};

function server(initial: FinanceRun[] = []) {
  const state = { runs: structuredClone(initial), error: '', postError: '' };
  const fetcher = vi.fn((path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (state.postError) return Promise.resolve(new Response(JSON.stringify({ detail: state.postError }), { status: 409 }));
      const created = { ...run, id: 'new-run', status: 'queued' as const, result: null, scenario: JSON.parse(typeof init.body === 'string' ? init.body : '{}') as FinanceRun['scenario'] };
      state.runs.unshift(created);
      return Promise.resolve(new Response(JSON.stringify(created), { status: 202 }));
    }
    if (state.error) return Promise.resolve(new Response(JSON.stringify({ detail: state.error }), { status: 503 }));
    return Promise.resolve(new Response(JSON.stringify(state.runs.filter(item => path.includes(`/projects/${item.project_id}/`)))));
  });
  vi.stubGlobal('fetch', fetcher);
  return { state, fetcher };
}

test('starts with synthetic-data explanation and posts exact scenario through the demo transport', async () => {
  const { fetcher } = server();
  const user = userEvent.setup();
  render(<Finance projectId="project-a" />);
  expect(await screen.findByText('Jeszcze nie wykonano analizy')).toBeInTheDocument();
  expect(screen.getByText(/NII to przychody odsetkowe minus koszty odsetkowe/)).toBeInTheDocument();
  await user.clear(screen.getByLabelText('Zmiana stóp (pb)'));
  await user.type(screen.getByLabelText('Zmiana stóp (pb)'), '-150');
  await user.clear(screen.getByLabelText('Beta depozytów'));
  await user.type(screen.getByLabelText('Beta depozytów'), '0.5');
  await user.click(screen.getByLabelText(/Dodaj rozbieżność księgową i anomalię historyczną/));
  await user.click(screen.getByRole('button', { name: 'Oblicz scenariusz' }));
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
  const posted = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(posted?.[0]).toBe('/demo-api/projects/project-a/finance/runs');
  expect(JSON.parse(typeof posted?.[1]?.body === 'string' ? posted[1].body : '{}')).toEqual({ shock_bps: -150, deposit_beta: 0.5, inject_issues: true });
  expect(posted?.[1]?.headers).toMatchObject({ 'X-Torii-Demo': '1' });
  expect(await screen.findByText('Obliczenia oczekują na wykonanie.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Oblicz scenariusz' })).toBeDisabled();
  expect(screen.queryByRole('region', { name: 'Wynik analizy NII' })).not.toBeInTheDocument();
});

test('renders persisted NII, reconciliation, history, assumptions and immutable export', async () => {
  server([run]);
  render(<Finance projectId="project-a" />);
  const result = await screen.findByRole('region', { name: 'Wynik analizy NII' });
  expect(within(result).getByText('40 000,00 PLN', { selector: 'strong' })).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Uzgodnienie portfela z księgą główną' })).toHaveTextContent('1100');
  expect(screen.getByRole('table', { name: 'Wkład portfeli w zmianę NII' })).toHaveTextContent('Kredyty zmienne');
  expect(screen.getByRole('link', { name: 'Eksport analizy JSON' })).toHaveAttribute('href', '/demo-api/projects/project-a/finance/runs/finance-a/export');
  expect(screen.getByText('Stałe salda; ACT/365F.')).toBeInTheDocument();
  expect(screen.getByText(manifest.input_sha256)).toBeInTheDocument();
});

test('keeps blocked quality visible beside amounts and labels the anomaly as a rule', async () => {
  const blocked = structuredClone(run);
  if (!blocked.result) throw new Error('Fixture needs a result');
  blocked.result.quality_status = 'blocked';
  blocked.result.reconciliation[0] = { gl_account: '1100', side: 'asset', portfolio_pln: 1000000, ledger_pln: 900000, difference_pln: 100000, status: 'mismatch' };
  blocked.result.anomalies = [{ month: '2026-09', nii_pln: -100000, baseline_pln: 40000, threshold_pln: 100000, deviation_pln: -140000 }];
  server([blocked]);
  render(<Finance projectId="project-a" />);
  const result = await screen.findByRole('region', { name: 'Wynik analizy NII' });
  expect(within(result).getByText('Wynik roboczy — dane nieuzgodnione')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Uzgodnienie portfela z księgą główną' })).toHaveTextContent('Rozbieżność');
  expect(screen.getByRole('table', { name: 'Sygnały anomalii historycznych' })).toHaveTextContent('2026-09');
  expect(screen.getByText(/Sygnał regułowy, nie model ML/)).toBeInTheDocument();
});

test('polls an active run to a real completed report', async () => {
  const { state } = server([{ ...run, status: 'running', result: null }]);
  render(<Finance projectId="project-a" />);
  expect(await screen.findByText('Trwają obliczenia scenariusza.')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Eksport analizy JSON' })).not.toBeInTheDocument();
  state.runs = [run];
  expect(await screen.findByRole('region', { name: 'Wynik analizy NII' }, { timeout: 3500 })).toBeInTheDocument();
});

test('shows load and shared-run errors and lets the user retry reading', async () => {
  const { state } = server();
  state.error = 'Magazyn niedostępny.';
  const user = userEvent.setup();
  render(<Finance projectId="project-a" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Magazyn niedostępny.');
  expect(screen.getByRole('button', { name: 'Oblicz scenariusz' })).toBeDisabled();
  state.error = '';
  state.postError = 'Inne wykonanie demo nadal trwa.';
  await user.click(screen.getByRole('button', { name: 'Odśwież analizy' }));
  await screen.findByText('Jeszcze nie wykonano analizy');
  await user.click(screen.getByRole('button', { name: 'Oblicz scenariusz' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Inne wykonanie demo nadal trwa.');
});

test('selects historical runs and retains provenance for failed execution', async () => {
  server([{ ...run, id: 'failed-run', status: 'failed', result: null, error: 'Limit czasu obliczeń.', scenario: { ...scenario, shock_bps: -100 } }, run]);
  const user = userEvent.setup();
  render(<Finance projectId="project-a" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Limit czasu obliczeń.');
  expect(screen.getByText(manifest.engine_sha256)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Pokaż analizę finance-a/ }));
  expect(await screen.findByRole('region', { name: 'Wynik analizy NII' })).toBeInTheDocument();
});

test('project changes discard old results and ignore late requests', async () => {
  let release: ((value: Response) => void) | undefined;
  vi.stubGlobal('fetch', vi.fn((path: string) => path.includes('project-a')
    ? new Promise<Response>(resolve => { release = resolve; })
    : Promise.resolve(new Response('[]'))));
  const { rerender } = render(<Finance projectId="project-a" />);
  rerender(<Finance projectId="project-b" />);
  await screen.findByText('Jeszcze nie wykonano analizy');
  await act(async () => { release?.(new Response(JSON.stringify([run]))); await Promise.resolve(); });
  expect(screen.queryByRole('region', { name: 'Wynik analizy NII' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Pokaż analizę finance-a/ })).not.toBeInTheDocument();
});

test('invalid scenario values do not issue a write', async () => {
  const { fetcher } = server();
  render(<Finance projectId="project-a" />);
  await screen.findByText('Jeszcze nie wykonano analizy');
  fireEvent.change(screen.getByLabelText('Zmiana stóp (pb)'), { target: { value: '301' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Parametry scenariusza' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/całkowitą od -300 do 300/);
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
});
