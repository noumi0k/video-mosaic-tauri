import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

const repoRoot = process.cwd();
const scanRoots = [
  "apps",
  "docs",
  "installer",
  "scripts",
  "tools",
  "README.md",
  "AGENTS.md",
  "CLAUDE.md",
];

const textExtensions = new Set([
  ".md",
  ".txt",
  ".json",
  ".js",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".css",
  ".html",
  ".py",
  ".rs",
  ".toml",
  ".yml",
  ".yaml",
]);

const skipDirs = new Set([
  ".git",
  ".claude",
  "node_modules",
  "dist",
  "target",
  ".venv",
  "__pycache__",
  ".pytest-tmp",
  ".pytest_cache",
  ".mypy_cache",
  "review-runtime",
]);

const strongSuspiciousPatterns = [/・ｽ/, /繝ｻ・ｽ/, /�/];
const suspiciousFragments = ["邵ｺ", "郢ｧ", "闕ｳ", "隴斈陞ｳ", "陷", "髫ｱ", "騾・"];
const ignoredRelativePaths = new Set([
  "apps/desktop/scripts/check-mojibake.mjs",
  "scripts/check-mojibake.mjs",
]);
const ignoredLinePatterns = [/`�`\s*混入チェック/];

const problems = [];

function scanPath(pathLike) {
  const fullPath = join(repoRoot, pathLike);
  const stat = safeStat(fullPath);
  if (!stat) {
    return;
  }
  if (stat.isDirectory()) {
    walk(fullPath);
    return;
  }
  scanFile(fullPath);
}

function walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  for (const entry of entries) {
    if (skipDirs.has(entry)) {
      continue;
    }
    const fullPath = join(dir, entry);
    const stat = safeStat(fullPath);
    if (!stat) {
      continue;
    }
    if (stat.isDirectory()) {
      walk(fullPath);
      continue;
    }
    scanFile(fullPath);
  }
}

function scanFile(fullPath) {
  const relPath = relative(repoRoot, fullPath).replaceAll("\\", "/");
  if (ignoredRelativePaths.has(relPath)) {
    return;
  }
  if (!textExtensions.has(extname(fullPath)) && !fullPath.endsWith("AGENTS.md") && !fullPath.endsWith("CLAUDE.md")) {
    return;
  }

  let text;
  try {
    text = readFileSync(fullPath, "utf8");
  } catch {
    return;
  }
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    if (ignoredLinePatterns.some((pattern) => pattern.test(line))) {
      return;
    }
    const strongHit = strongSuspiciousPatterns.some((pattern) => pattern.test(line));
    const fragmentHits = suspiciousFragments.filter((fragment) => line.includes(fragment)).length;
    if (strongHit || fragmentHits >= 2) {
      problems.push(`${relative(repoRoot, fullPath)}:${index + 1}: ${line.trim()}`);
    }
  });
}

function safeStat(fullPath) {
  try {
    return statSync(fullPath);
  } catch {
    return null;
  }
}

for (const scanRoot of scanRoots) {
  scanPath(scanRoot);
}

if (problems.length > 0) {
  console.error("Suspicious mojibake detected:");
  for (const problem of problems) {
    console.error(problem);
  }
  process.exit(1);
}

console.log("No suspicious mojibake detected.");
