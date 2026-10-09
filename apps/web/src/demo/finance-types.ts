/** SPEC-0019 revision 0.2: local financial analysis contract. */
export type FinanceSide = 'asset' | 'liability';
export interface FinancePosition {
  id: string; name: string; gl_account: string; side: FinanceSide; balance_pln: number;
  annual_rate: number; rate_type: 'fixed' | 'floating'; repricing_month: number;
  deposit_beta_applies: boolean; rate_floor: number;
}
export interface FinanceSnapshot {
  as_of: string; currency: 'PLN'; positions: FinancePosition[];
  ledger: { gl_account: string; side: FinanceSide; balance_pln: number }[];
  history: { month: string; interest_income_pln: number; interest_expense_pln: number }[];
}
export interface FinanceScenario { shock_bps: number; deposit_beta: number; inject_issues: boolean }
export interface FinanceManifest {
  engine_version: string; engine_sha256: string; input_sha256: string; scenario_sha256: string;
}
export interface FinanceTotals {
  income_base_pln: number; expense_base_pln: number; nii_base_pln: number;
  income_scenario_pln: number; expense_scenario_pln: number; nii_scenario_pln: number; delta_nii_pln: number;
}
export interface FinanceMonth extends FinanceTotals { month: string }
export interface FinanceContribution {
  position_id: string; name: string; side: FinanceSide; balance_pln: number;
  rate_type: 'fixed' | 'floating'; repricing_month: number;
  base_interest_pln: number; scenario_interest_pln: number; delta_nii_pln: number;
  monthly: { month: string; base_rate: number; scenario_rate: number; base_interest_pln: number; scenario_interest_pln: number }[];
}
export interface FinanceReport {
  snapshot: FinanceSnapshot; scenario: FinanceScenario; manifest: FinanceManifest;
  assumptions: string[]; quality_status: 'passed' | 'blocked';
  reconciliation: { gl_account: string; side: FinanceSide; portfolio_pln: number; ledger_pln: number; difference_pln: number; status: 'matched' | 'mismatch' }[];
  anomalies: { month: string; nii_pln: number; baseline_pln: number; threshold_pln: number; deviation_pln: number }[];
  monthly: FinanceMonth[]; contributions: FinanceContribution[]; totals: FinanceTotals;
}
export interface FinanceRun {
  id: string; project_id: string; status: 'queued' | 'running' | 'succeeded' | 'failed';
  created_at: string; snapshot: FinanceSnapshot; scenario: FinanceScenario; manifest: FinanceManifest;
  error: string | null; result: FinanceReport | null;
}
