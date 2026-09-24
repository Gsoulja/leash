import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const here = resolve(__dirname);
const theme = readFileSync(resolve(here, "theme.css"), "utf8");
const prototype = readFileSync(resolve(here, "../../prototype/index.html"), "utf8");

function rootTokens(css: string): Record<string, string> {
  const block = /:root\s*\{([^}]*)\}/.exec(css);
  if (!block) throw new Error("no :root block");
  const out: Record<string, string> = {};
  for (const [, name, value] of block[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[name] = value.trim();
  return out;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("design tokens", () => {
  const ours = rootTokens(theme);
  const theirs = rootTokens(prototype);

  it("match the prototype exactly", () => {
    expect(Object.keys(theirs).length).toBeGreaterThan(20);
    for (const [name, value] of Object.entries(theirs)) expect(ours[name], name).toBe(value);
    // The only additions are darker text variants, because some prototype colours fail WCAG AA as text.
    const extra = Object.keys(ours).filter((name) => !(name in theirs));
    expect(extra.every((name) => /^--a-[\w]+-text$/.test(name)), extra.join(", ")).toBe(true);
  });

  it("app text meets WCAG AA contrast (4.5:1) on its backgrounds", () => {
    const pairs: [string, string][] = [
      ["--a-ink", "--a-bg"], ["--a-ink", "--a-card"], ["--a-muted-text", "--a-card"], ["--a-muted-text", "--a-bg"],
      ["--a-blue", "--a-card"], ["--a-ok-text", "--a-ok-soft"], ["--a-warn-text", "--a-warn-soft"],
      ["--a-bad-text", "--a-bad-soft"],
    ];
    for (const [fg, bg] of pairs) expect(contrast(ours[fg], ours[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });
});
