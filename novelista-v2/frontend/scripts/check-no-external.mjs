// Fails the build if dist/ references any remote URL other than provider placeholders.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ALLOWED = ["https://api.openai.com", "https://openrouter.ai", "http://localhost", "http://127.0.0.1",
  // inert strings inside React: XML namespace identifiers and an error-message docs link (never fetched)
  "http://www.w3.org/", "https://react.dev/errors"];
const TEXT = new Set([".html", ".js", ".css", ".json", ".svg", ".txt", ".map", ".webmanifest"]);
const URL_RE = /https?:\/\/[^\s"'`)<>\\]+/g;
const bad = [];

function walk(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) { walk(p); continue; }
    if (!TEXT.has(extname(p))) continue;
    const src = readFileSync(p, "utf8").replace(/\/\*[\s\S]*?\*\//g, ""); // license comments
    for (const m of src.matchAll(URL_RE))
      if (!ALLOWED.some((a) => m[0].startsWith(a))) bad.push(`${p}: ${m[0]}`);
  }
}
walk("dist");
if (bad.length) { console.error("External URLs found in dist:\n" + bad.join("\n")); process.exit(1); }
console.log("check-no-external: ok");
