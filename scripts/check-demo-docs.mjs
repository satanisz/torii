// SPEC-0018 D07: documentation links and offline presentation interactions.
// Uses the existing frontend jsdom dependency. No network, browser or data writes.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(resolve(root, 'apps/web/package.json'));
const { JSDOM } = require('jsdom');
const files = [
  'README.md', 'apps/demo/README.md', 'apps/web/README.md',
  'docs/legacy-workspaces.md', 'docs/demo-operations.md', 'docs/demo-architecture.md',
  'docs/brand/README.md', 'docs/local-installation.md', 'docs/platform/README.md',
  'docs/presentation/README.md', 'docs/presentation/torii.html',
];
let links = 0;
for (const file of files) {
  const text = readFileSync(resolve(root, file), 'utf8');
  const matches = file.endsWith('.html')
    ? [...text.matchAll(/(?:href|src)="([^"]+)"/g)].map(match => match[1])
    : [...text.matchAll(/\]\(([^)]+)\)/g)].map(match => match[1]);
  for (const target of matches) {
    if (/^(?:https?:|mailto:|#)/.test(target)) continue;
    const path = target.split('#')[0];
    assert(existsSync(resolve(root, dirname(file), path)), `${file}: missing ${target}`);
    links++;
  }
}

const html = readFileSync(resolve(root, 'docs/presentation/torii.html'), 'utf8');
const dom = new JSDOM(html, { runScripts:'outside-only', url:'http://127.0.0.1/presentation/torii.html' });
const { window } = dom;
window.scrollTo = () => {};
const document = window.document;
const slides = [...document.querySelectorAll('.slide')];
assert.equal(slides.length, 12);
assert(slides.every(slide => !slide.hidden), 'No-JS fallback must expose every slide');
assert.equal(document.querySelectorAll('script[src],link[rel="stylesheet"]').length, 0, 'No external assets needed');
const ids = [...document.querySelectorAll('[id]')].map(element => element.id);
assert.equal(new Set(ids).size, ids.length, 'Duplicate IDs');
for (const element of document.querySelectorAll('[aria-labelledby]')) {
  assert(document.getElementById(element.getAttribute('aria-labelledby')), 'Missing labelled heading');
}
window.eval(document.querySelector('script').textContent);
const visible = () => slides.filter(slide => !slide.hidden);
assert.equal(visible()[0].id, 'slajd-1');
assert.equal(visible().length, 1);
assert(document.getElementById('previous').disabled);
assert.equal(document.querySelectorAll('#slide-picker option').length, 12);
document.getElementById('next').click();
assert.equal(visible()[0].id, 'slajd-2');
document.getElementById('previous').click();
assert.equal(visible()[0].id, 'slajd-1');
const picker = document.getElementById('slide-picker');
picker.value = '3';
picker.dispatchEvent(new window.Event('change'));
assert.equal(visible()[0].id, 'slajd-4');
document.getElementById('overview').click();
assert.equal(visible().length, 12);
assert(document.getElementById('next').disabled);
document.getElementById('overview').click();
assert.equal(visible().length, 1);
document.body.dispatchEvent(new window.KeyboardEvent('keydown', { key:'End', bubbles:true }));
assert.equal(visible()[0].id, 'slajd-12');
assert(document.getElementById('next').disabled);
document.body.dispatchEvent(new window.KeyboardEvent('keydown', { key:'Home', bubbles:true }));
assert.equal(visible()[0].id, 'slajd-1');
picker.dispatchEvent(new window.KeyboardEvent('keydown', { key:'End', bubbles:true }));
assert.equal(visible()[0].id, 'slajd-1', 'Native control must keep its keyboard handling');
window.location.hash = '#slajd-9';
window.dispatchEvent(new window.HashChangeEvent('hashchange'));
assert.equal(visible()[0].id, 'slajd-9');
let printed = false;
window.print = () => { printed = true; };
document.getElementById('print').click();
assert(printed);
assert(html.includes('@media print') && html.includes('.slide[hidden] { display:block !important;'));
window.close();
// Local-file hosts may reject history rewriting. Slide navigation must still work.
const fileDom = new JSDOM(html, { runScripts:'outside-only', url:'file:///torii/docs/presentation/torii.html' });
const fileWindow = fileDom.window;
fileWindow.scrollTo = () => {};
const navigationErrors = [];
fileWindow.addEventListener('error', event => { navigationErrors.push(event.error); event.preventDefault(); });
fileWindow.eval(fileWindow.document.querySelector('script').textContent);
fileWindow.document.getElementById('next').click();
assert.equal(navigationErrors.length, 0, 'Local-file navigation must tolerate rejected history rewriting');
assert.equal(fileWindow.document.querySelector('.slide:not([hidden])').id, 'slajd-2');
fileWindow.close();
console.log(`PASS: ${files.length} documents, ${links} local links, 12 slides, navigation, no-JS fallback and print action.`);
