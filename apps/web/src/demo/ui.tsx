import { cloneElement, useId } from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { DemoObject, Scalar, VersionRef } from './types';

export function number(value: number | null | undefined): string {
  return value == null ? '—' : new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 4 }).format(value);
}
export function text(value: unknown): string { return typeof value === 'string' ? value : ''; }
export function refs(objects: DemoObject[], kind: DemoObject['kind']): VersionRef[] {
  return objects.filter(object => object.kind === kind).flatMap(object => [...object.versions].sort((a, b) => b.number - a.number).map(version => ({ object, version })));
}
export function label(ref: VersionRef | undefined): string { return ref ? `${ref.object.name} · v${String(ref.version.number)}` : 'Nieznana wersja'; }
export function Field({ title, children, hint }: { title: string; children: ReactElement<{ id?: string; 'aria-describedby'?: string }>; hint?: string }) {
  const id = useId();
  return <div className="demo-field"><span><label htmlFor={id}>{title}</label></span>{cloneElement(children, { id, ...(hint ? { 'aria-describedby': `${id}-hint` } : {}) })}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>;
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="demo-empty"><span aria-hidden="true">◇</span><h3>{title}</h3><p>{children}</p></div>;
}
export function DataTable({ columns, rows, title }: { columns: string[]; rows: Record<string, Scalar>[]; title: string }) {
  return <div className="table-scroll"><table aria-label={title}><thead><tr>{columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column}>{row[column] === null || row[column] === undefined ? <span className="demo-null">brak</span> : typeof row[column] === 'number' ? number(row[column]) : String(row[column])}</td>)}</tr>)}</tbody></table></div>;
}
