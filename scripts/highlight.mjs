// Tokenize source files with Shiki, for scripts/preview.py.
// Usage: node scripts/highlight.mjs THEME FILE...
// Prints JSON: {"bg": ..., "fg": ..., "files": [[[[text, color, style], ...], ...line], ...file]}
// style is "", "italic", "bold" or "bold italic".
import { readFileSync } from "node:fs";
import { extname } from "node:path";
import { codeToTokensBase, getSingletonHighlighter } from "shiki";

const LANGS = { ".py": "python", ".ts": "typescript", ".rs": "rust", ".js": "javascript" };
const STYLES = { 0: "", 1: "italic", 2: "bold", 3: "bold italic" };

const [theme, ...files] = process.argv.slice(2);
const out = { files: [] };
for (const file of files) {
  const code = readFileSync(file, "utf8").replace(/\n$/, "");
  const lines = await codeToTokensBase(code, { lang: LANGS[extname(file)], theme });
  out.files.push(lines.map((line) => line.map((t) => [t.content, t.color, STYLES[t.fontStyle ?? 0] ?? ""])));
}
const t = (await getSingletonHighlighter({ themes: [theme] })).getTheme(theme);
Object.assign(out, { bg: t.bg, fg: t.fg });
console.log(JSON.stringify(out));
