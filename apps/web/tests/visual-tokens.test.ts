import { describe, expect, it } from 'vitest';
import css from '../src/styles.css?raw';

function luminance(hex: string): number {
  const channels = hex.replace('#', '').match(/../g)?.map((part) => {
    const value = Number.parseInt(part, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  if (!channels || channels.length !== 3) throw new Error('Invalid test color');
  return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722;
}
function contrast(first: string, second: string): number {
  const a = luminance(first); const b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
function token(name: string): string {
  const match = new RegExp(`--${name}: (#[0-9a-f]{6})`).exec(css);
  if (!match?.[1]) throw new Error(`Missing token ${name}`);
  return match[1];
}

describe('SPEC-0017 AC-06 declared color tokens (not a full accessibility audit)', () => {
  it.each([
    ['text', 'surface'], ['text', 'background'], ['muted', 'surface'], ['muted', 'background'],
    ['primary', 'surface'], ['success', 'surface'], ['warning', 'surface'], ['danger', 'surface'],
  ])('%s text on %s meets 4.5:1', (foreground, background) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(4.5);
  });
  it.each([['focus', 'surface'], ['focus', 'background'], ['cyan', 'navy'], ['control-border', 'surface']])('%s affordance on %s meets 3:1', (foreground, background) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(3);
  });
  it.each([['danger', '#fff2f2'], ['warning', '#fff8e9'], ['success', '#edf8f1']])('%s notice text meets 4.5:1', (foreground, background) => {
    expect(contrast(token(foreground), background)).toBeGreaterThanOrEqual(4.5);
  });
  it('keeps system fonts, visible focus, and no remote visual dependencies', () => {
    expect(css).toContain(':focus-visible');
    expect(css).toContain('system-ui');
    expect(css).not.toMatch(/@import|url\(\s*["']?https?:/);
  });
});
