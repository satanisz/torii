// SPEC-0018: isolated local-demo wire contract; not the enterprise API.
export type Scalar = string | number | boolean | null;
export interface Profile {
  name: string; dtype: 'number' | 'string' | 'boolean' | 'mixed' | 'empty';
  missing: number; unique: number; min: number | null; max: number | null; mean: number | null;
}
export interface Summary { columns?: string[]; row_count?: number; profile?: Profile[]; preview?: Record<string, Scalar>[] }
export interface Version { id: string; number: number; definition: Record<string, unknown>; sha256: string; created_at: string; summary: Summary }
export interface DemoObject {
  id: string; project_id: string; kind: 'dataset' | 'transformation' | 'model' | 'analysis';
  name: string; created_at: string; versions: Version[];
}
export interface Project { id: string; name: string; created_at: string }
export interface RunResult {
  metrics: { mae: number; rmse: number; r2: number };
  importance: { feature: string; value: number }[];
  predictions: { actual: number; predicted: number }[];
  train_rows: number; test_rows: number; mlflow_run_id: string; algorithm: 'linear' | 'dummy';
  environment: Record<string, unknown>;
}
export interface Run {
  id: string; project_id: string; model_version_id: string; dataset_version_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed'; result: RunResult | null;
  error: string | null; created_at: string; target: string; seed: number; test_size: number;
}
export interface DemoState { mode: 'local-demo'; projects: Project[]; objects: DemoObject[]; runs: Run[] }
export interface VersionRef { object: DemoObject; version: Version }
export type Mutation = (work: () => Promise<void>, message: string) => Promise<void>;
