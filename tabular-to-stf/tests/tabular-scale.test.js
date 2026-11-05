import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync, createWriteStream, readFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { once } from 'node:events';
import { readTable } from '../scripts/lib/tabular/read-table.js';
import { profileTables } from '../scripts/lib/tabular/profile.js';
import { renderStf } from '../scripts/lib/tabular/render.js';
import { checkStf } from '../scripts/lib/tabular/check.js';

// Opt-in: 1,000 parents and 1,000,000 children, in the default heap.
const PARENTS = 1000;
const CHILDREN = 1_000_000;

test('scale: profile, render and check 1M child rows', { skip: process.env.STF_SCALE_TEST !== '1', timeout: 900_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), 'stf-scale-'));
  try {
    const started = Date.now();
    let peak = 0;
    const sample = setInterval(() => { peak = Math.max(peak, process.memoryUsage().rss); }, 200);
    const stage = (label) => {
      peak = Math.max(peak, process.memoryUsage().rss);
      console.log(`  ${label}: ${((Date.now() - started) / 1000).toFixed(1)}s, rss ${(process.memoryUsage().rss / 2 ** 20).toFixed(0)} MiB`);
    };

    writeFileSync(join(dir, 'parent.csv'), `parent_id,name\n${Array.from({ length: PARENTS }, (_, i) => `P${i},Parent ${i}`).join('\n')}\n`);
    const out = createWriteStream(join(dir, 'child.csv'));
    out.write('child_id,parent_id,age,weight,visit_date,sex,status,note\n');
    for (let i = 0; i < CHILDREN; i++) {
      const month = String((i % 12) + 1).padStart(2, '0');
      const day = String((i % 28) + 1).padStart(2, '0');
      const ok = out.write(`C${i},P${i % PARENTS},${i % 90},${(30 + (i % 500) / 10).toFixed(1)},2023-${month}-${day},${i % 2 ? 'F' : 'M'},${['ok', 'late', 'lost'][i % 3]},${i % 7 === 0 ? '' : `note ${i % 1000}`}\n`);
      if (!ok) await once(out, 'drain');
    }
    out.end();
    await once(out, 'finish');
    stage('generated');

    const tables = ['parent', 'child'].map((n) => readTable(join(dir, `${n}.csv`)));
    stage('read');
    const profile = profileTables(tables);
    assert.equal(profile.files.length, 2);
    stage('profiled');

    // The CLI's --out path: the full profile to a file, a summary line per file on stdout; then one file with --file.
    const profilePath = join(dir, 'work', 'profile.json');
    mkdirSync(join(dir, 'work'));
    const cli = new URL('../scripts/profile-tables.js', import.meta.url).pathname;
    const summary = execFileSync('node', [cli, dir, '--out', profilePath], { encoding: 'utf8' });
    assert.match(summary, /^child\.csv: 1000000 rows, 8 columns, /m);
    assert.equal(JSON.parse(readFileSync(profilePath, 'utf8')).files.length, 2);
    const one = execFileSync('node', [cli, dir, '--file', 'child.csv'], { encoding: 'utf8' });
    assert.ok(one.length < 30_000, `--file child.csv printed ${one.length} chars`);
    console.log(`  profile CLI: --out summary ${summary.length} chars, --file child.csv ${one.length} chars`);
    stage('profile CLI --out and --file');

    const spec = {
      specVersion: 1,
      study: { name: 'Scale test' },
      inputDir: dir,
      entities: [
        { name: 'parent', displayName: 'Parent', displayNamePlural: 'Parents', file: 'parent.csv', idColumn: 'parent_id', variables: [{ column: 'name' }] },
        {
          name: 'child', displayName: 'Child', displayNamePlural: 'Children', file: 'child.csv', idColumn: 'child_id',
          parent: 'parent', parentColumn: 'parent_id',
          variables: ['age', 'weight', 'visit_date', 'sex', 'status', 'note'].map((column) => ({ column })),
        },
      ],
      transforms: [],
    };
    const { files } = renderStf(spec, new Map(tables.map((t, i) => [['parent', 'child'][i], { headers: t.headers, rows: t.rows }])), { sourceDir: dir });
    stage('rendered');

    const outDir = join(dir, 'stf');
    mkdirSync(outDir);
    for (const [name, text] of Object.entries(files)) writeFileSync(join(outDir, name), text);
    const result = checkStf(outDir);
    stage('checked');
    clearInterval(sample);

    assert.deepEqual(result.errors, []);
    peak = Math.max(peak, process.memoryUsage().rss);
    console.log(`  scale result: wall ${((Date.now() - started) / 1000).toFixed(1)}s, peak rss ${(peak / 2 ** 20).toFixed(0)} MiB`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
