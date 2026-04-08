import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scanRoots = ["src", "tests"];
const extensions = new Set([".ts", ".tsx", ".css", ".md"]);
const suspiciousPatterns = [
  /�/,
  /・ｽ/,
  /(?:縺|繧|荳|譛|螳|蜀|隱|逕)[^\n ]{0,8}(?:縺|繧|荳|譛|螳|蜀|隱|逕)/,
];
const problems = [];

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      walk(fullPath);
      continue;
    }
    if (!extensions.has(extname(fullPath))) {
      continue;
    }
    const text = readFileSync(fullPath, "utf8");
    const lines = text.split(/\r?\n/);
    lines.forEach((line, index) => {
      if (suspiciousPatterns.some((pattern) => pattern.test(line))) {
        problems.push(`${fullPath}:${index + 1}: ${line.trim()}`);
      }
    });
  }
}

for (const relativeRoot of scanRoots) {
  walk(join(root, relativeRoot));
}

if (problems.length) {
  console.error("Suspicious mojibake detected:");
  for (const line of problems) {
    console.error(line);
  }
  process.exit(1);
}

console.log("No suspicious mojibake detected.");
