import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname, resolve, relative } from 'node:path';
import { STF_CONSTANTS } from '../scripts/lib/tabular/stf-constants.js';
import { STUDY_WRANGLER_VERSION } from '../scripts/lib/tools/study-wrangler-container.js';

const skill = new URL('../', import.meta.url).pathname;
const read = (p) => readFileSync(join(skill, p), 'utf8');

// SKILL.md and every Markdown file under resources/, relative to the skill.
const docs = () => ['SKILL.md', ...readdirSync(join(skill, 'resources'), { recursive: true })
  .filter((f) => f.endsWith('.md'))
  .map((f) => join('resources', f))];

test('every STF_CONSTANTS value is documented in the bundled metadata-fields.md', () => {
  const text = read('resources/stf/metadata-fields.md');
  const missing = Object.entries(STF_CONSTANTS)
    .flatMap(([set, values]) => values.filter((v) => !text.includes(`\`${v}\``)).map((v) => `${set}: ${v}`));
  assert.deepEqual(missing, []);
});

test('SOURCE.md names the pinned study-wrangler version and no other', () => {
  const text = read('resources/stf/SOURCE.md');
  assert.ok(text.includes(`v${STUDY_WRANGLER_VERSION}`), `SOURCE.md does not name v${STUDY_WRANGLER_VERSION}`);
  const tags = new Set(text.match(/v\d+\.\d+\.\d+/g));
  assert.deepEqual([...tags], [`v${STUDY_WRANGLER_VERSION}`]);
});

test('every relative link in SKILL.md and resources resolves inside the skill', () => {
  const broken = [];
  for (const doc of docs()) {
    for (const [, target] of read(doc).matchAll(/\]\(([^)\s]+)\)/g)) {
      if (/^[a-z]+:/i.test(target) || target.startsWith('#')) continue;
      const path = resolve(dirname(join(skill, doc)), target.split('#')[0]);
      if (relative(skill, path).startsWith('..') || !existsSync(path)) broken.push(`${doc}: ${target}`);
    }
  }
  assert.deepEqual(broken, []);
});

test('SKILL.md frontmatter names the skill tabular-to-stf', () => {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(read('SKILL.md'));
  assert.ok(m, 'SKILL.md has no frontmatter');
  assert.match(m[1], /^name: tabular-to-stf$/m);
  assert.match(m[1], /^description: \S/m);
});

test('every script the docs mention exists, with every --option used beside it', () => {
  const problems = [];
  for (const doc of docs().filter((d) => !d.startsWith(join('resources', 'stf')))) {
    for (const line of read(doc).split('\n')) {
      for (const [, script] of line.matchAll(/scripts\/([a-z-]+\.js)/g)) {
        const path = join(skill, 'scripts', script);
        if (!existsSync(path)) { problems.push(`${doc}: scripts/${script} does not exist`); continue; }
        const source = readFileSync(path, 'utf8');
        for (const [flag] of line.matchAll(/--[a-z][a-z-]*/g)) {
          if (!source.includes(`'${flag.slice(2)}'`) && !source.includes(` ${flag.slice(2)}:`)) problems.push(`${doc}: scripts/${script} has no ${flag}`);
        }
      }
    }
  }
  assert.deepEqual(problems, []);
});
