import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const here = resolve(__dirname);
const theme = readFileSync(resolve(here, "theme.css"), "utf8");
const visualSystem = readFileSync(resolve(here, "../../../designPrototype/Visual System.dc.html"), "utf8");
const indexHtml = readFileSync(resolve(here, "../index.html"), "utf8");

function rootTokens(css: string): Record<string, string> {
  const block = /:root\s*\{([^}]*)\}/.exec(css);
  if (!block) throw new Error("no :root block");
  const out: Record<string, string> = {};
  for (const [, name, value] of block[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[name] = value.trim();
  return out;
}

/** The palette swatches of the visual system, keyed as CSS custom properties ("allowed/tint" → --allowed-tint). */
function swatches(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [, token, hex] of html.matchAll(/token:\s*'([\w/-]+)',\s*hex:\s*'(#[0-9A-Fa-f]{6})'/g)) {
    out[`--${token.replace("/", "-")}`] = hex.toUpperCase();
  }
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
  const palette = swatches(visualSystem);

  it("carry every colour of the visual system's palette, unchanged", () => {
    expect(Object.keys(palette)).toHaveLength(12);
    for (const [name, hex] of Object.entries(palette)) expect(ours[name]?.toUpperCase(), name).toBe(hex);
  });

  it("use the visual system's typefaces: Inter, with IBM Plex Mono for machine text", () => {
    expect(ours["--sans"]).toMatch(/^Inter,/);
    expect(ours["--mono"]).toMatch(/^"IBM Plex Mono",/);
    expect(indexHtml).toContain("family=Inter");
    expect(indexHtml).toContain("family=IBM+Plex+Mono");
  });

  it("app text meets WCAG AA contrast (4.5:1) on its backgrounds", () => {
    const pairs: [string, string][] = [
      ["--ink", "--canvas"], ["--ink", "--surface"], ["--ink-muted-text", "--surface"], ["--ink-muted-text", "--canvas"], ["--ink-body", "--canvas"],
      ["--allowed-text", "--allowed-tint"], ["--stopped-text", "--stopped-tint"], ["--your-turn-text", "--your-turn-tint"],
      ["--surface", "--allowed"], ["--surface", "--your-turn"], ["--stopped", "--surface"], ["--on-dark", "--ink"],
    ];
    for (const [fg, bg] of pairs) expect(contrast(ours[fg], ours[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });
});
