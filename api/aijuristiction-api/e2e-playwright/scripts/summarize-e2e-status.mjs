import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const [catalogPath, reportPath, outputPath] = process.argv.slice(2);

if (!catalogPath || !reportPath || !outputPath) {
  console.error(
    'Usage: node scripts/summarize-e2e-status.mjs <catalog.json> <playwright-report.json> <summary.md>'
  );
  process.exit(2);
}

const catalog = JSON.parse(stripBom(await readFile(catalogPath, 'utf8')));
const report = JSON.parse(stripBom(await readFile(reportPath, 'utf8')));

const resultsByFileAndTitle = new Map();
collectSpecs(report.suites ?? [], []);

const generatedAt = new Date().toISOString();
const lines = [
  '# Scheduled E2E test status',
  '',
  `Generated: ${generatedAt}`,
  '',
  '| Test | Description | Area | Status | Duration | Notes |',
  '| --- | --- | --- | --- | ---: | --- |',
];

for (const item of catalog) {
  const result = findResult(item);
  const status = result?.status ?? (item.scheduled ? 'not run' : 'not scheduled');
  const duration = result ? formatDuration(result.duration) : 'n/a';
  const notes = [item.prerequisite, result?.error].filter(Boolean).join(' ');

  lines.push(
    [
      escapeCell(item.name),
      escapeCell(item.description),
      escapeCell(item.area),
      escapeCell(status),
      escapeCell(duration),
      escapeCell(notes || 'n/a'),
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |')
  );
}

await writeFile(outputPath, `${lines.join('\n')}\n`, 'utf8');

function collectSpecs(suites, parentFiles) {
  for (const suite of suites) {
    const suiteFile = suite.file ? normalizePath(suite.file) : undefined;
    const files = suiteFile ? [...parentFiles, suiteFile] : parentFiles;

    for (const spec of suite.specs ?? []) {
      const specFile = normalizePath(spec.file ?? files[files.length - 1] ?? '');
      const tests = spec.tests ?? [];
      const flattenedResults = tests.flatMap((test) => test.results ?? []);
      const status = resolveStatus(tests, flattenedResults);
      const duration = flattenedResults.reduce((total, result) => total + (result.duration ?? 0), 0);
      const error = flattenedResults
        .map((result) => result.error?.message)
        .find((message) => typeof message === 'string' && message.trim().length > 0);

      resultsByFileAndTitle.set(`${specFile}::${spec.title}`, {
        status,
        duration,
        error: error ? firstLine(error) : undefined,
      });
    }

    collectSpecs(suite.suites ?? [], files);
  }
}

function findResult(item) {
  const exact = resultsByFileAndTitle.get(`${normalizePath(item.file)}::${item.title}`);
  if (exact) return exact;

  for (const [key, value] of resultsByFileAndTitle.entries()) {
    const [file, title] = key.split('::');
    if (file === normalizePath(item.file) && title.startsWith(item.title)) {
      return value;
    }
  }

  return undefined;
}

function resolveStatus(tests, results) {
  const statuses = new Set(tests.map((test) => test.status).filter(Boolean));
  if (statuses.has('unexpected')) return 'failed';
  if (statuses.has('flaky')) return 'flaky';
  if (statuses.has('skipped')) return 'skipped';
  if (statuses.has('expected')) return 'passed';

  const resultStatuses = new Set(results.map((result) => result.status).filter(Boolean));
  if (resultStatuses.has('failed') || resultStatuses.has('timedOut')) return 'failed';
  if (resultStatuses.has('skipped')) return 'skipped';
  if (resultStatuses.has('passed')) return 'passed';

  return 'not run';
}

function normalizePath(value) {
  return value.replaceAll('\\', '/').replace(/^.*?tests\//, 'tests/');
}

function formatDuration(milliseconds) {
  if (!milliseconds) return '0s';
  if (milliseconds < 1000) return `${milliseconds}ms`;
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function firstLine(value) {
  return value.split(/\r?\n/).find((line) => line.trim().length > 0)?.trim() ?? value.trim();
}

function escapeCell(value) {
  return String(value ?? '').replaceAll('|', '\\|').replace(/\r?\n/g, '<br>');
}

function stripBom(value) {
  return value.charCodeAt(0) === 0xfeff ? value.slice(1) : value;
}
