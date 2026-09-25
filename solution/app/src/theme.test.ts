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

function resolved(tokens: Record<string, string>, name: string): string {
  const value = tokens[name];
  const ref = /^var\((--[\w-]+)\)$/.exec(value ?? "");
  return ref ? resolved(tokens, ref[1]) : value;
}

// The Hi-Fi v4 handoff's colour table (designPrototype/README.md § Design tokens → Colour), transcribed (DEC-044).
const HANDOFF: Record<string, string> = {
  "--hf-allowed": "#2E7D45", "--hf-allowed-tint": "#E6F2E8", "--hf-allowed-ink": "#1F5C33",
  "--hf-stopped": "#C0203A", "--hf-stopped-tint": "#F9E9EB", "--hf-stopped-ink": "#8E1729",
  "--hf-your-turn": "#8A1FA8", "--hf-your-turn-tint": "#F3E6F7", "--hf-your-turn-ink": "#6A1783",
  "--hf-agent-tint": "#EDEBF8", "--hf-agent-ink": "#3D3478",
  "--hf-ink": "#14151A", "--hf-muted": "#7C7C74", "--hf-line": "#DCDBD5", "--hf-divider": "#EFEEEA",
  "--hf-canvas": "#F4F4F2", "--hf-on-dark": "#7BC48F",
};

// The phone's existing token names, re-pointed at the handoff (LEASH-181).
const PHONE: Record<string, string> = {
  "--a-bg": "--hf-canvas", "--a-ink": "--hf-ink", "--a-muted": "--hf-muted", "--a-line": "--hf-line", "--a-blue": "--hf-ink",
  "--a-ok": "--hf-allowed", "--a-ok-soft": "--hf-allowed-tint", "--a-ok-text": "--hf-allowed-ink",
  "--a-warn": "--hf-your-turn", "--a-warn-soft": "--hf-your-turn-tint", "--a-warn-text": "--hf-your-turn-ink",
  "--a-bad": "--hf-stopped", "--a-bad-soft": "--hf-stopped-tint", "--a-bad-text": "--hf-stopped-ink",
};

describe("design tokens", () => {
  const ours = rootTokens(theme);
  const theirs = rootTokens(prototype);

  it("match the v4 handoff tokens exactly", () => {
    for (const [name, value] of Object.entries(HANDOFF)) expect(ours[name], name).toBe(value);
    for (const [name, handoff] of Object.entries(PHONE)) expect(resolved(ours, name), name).toBe(HANDOFF[handoff]);
    // The only additions beyond the handoff and the prototype are darker text variants, for colours that fail WCAG AA
    // as text, and the handoff's type scale (LEASH-182).
    const extra = Object.keys(ours).filter((name) => !(name in theirs) && !(name in HANDOFF));
    expect(extra.every((name) => /^--(a|hf)-[\w-]+-text$|^--(fs|ls)-[\w-]+$/.test(name)), extra.join(", ")).toBe(true);
  });

  it("leave the inspector's tokens as the prototype defined them", () => {
    // --sans and --mono are shared with the phone and follow the handoff's type (LEASH-182).
    const inspector = Object.entries(theirs).filter(([name]) => !name.startsWith("--a-") && name !== "--sans" && name !== "--mono");
    expect(inspector.length).toBeGreaterThanOrEqual(15);  // --page … --dim
    for (const [name, value] of inspector) expect(ours[name], name).toBe(value);
    expect(theme).toContain("--page:#0E1014; --panel:#171A20;");  // both dark-mode blocks keep the inspector's dark set
    expect(theme.match(/--page:#0E1014; --panel:#171A20;/g)).toHaveLength(2);
  });

  it("app text meets WCAG AA contrast (4.5:1) on its backgrounds", () => {
    const pairs: [string, string][] = [
      ["--a-ink", "--a-bg"], ["--a-ink", "--a-card"], ["--a-muted-text", "--a-card"], ["--a-muted-text", "--a-bg"],
      ["--a-blue", "--a-card"], ["--a-ok-text", "--a-ok-soft"], ["--a-warn-text", "--a-warn-soft"],
      ["--a-bad-text", "--a-bad-soft"],
      ["--hf-allowed-ink", "--hf-allowed-tint"], ["--hf-stopped-ink", "--hf-stopped-tint"],
      ["--hf-your-turn-ink", "--hf-your-turn-tint"], ["--hf-agent-ink", "--hf-agent-tint"],
      ["--hf-ink", "--hf-canvas"], ["--hf-muted-text", "--hf-canvas"], ["--hf-muted-text", "--a-card"],
      // LEASH-184 primitives: draft badge, destructive outline, white labels on the filled buttons
      ["--hf-muted-text", "--hf-divider"], ["--hf-stopped", "--a-card"],
    ];
    for (const bg of ["--hf-ink", "--hf-allowed", "--hf-stopped", "--hf-your-turn"])
      expect(contrast("#FFFFFF", resolved(ours, bg)), `white on ${bg}`).toBeGreaterThanOrEqual(4.5);
    for (const [fg, bg] of pairs) expect(contrast(resolved(ours, fg), resolved(ours, bg)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });

  it("cites the v4 handoff decision, not the superseded prototype port", () => {
    const first = theme.split("\n")[0];
    expect(first).toContain("DEC-044");
    expect(first).not.toContain("DEC-021");
  });
});

describe("type and focus (LEASH-182)", () => {
  const ours = rootTokens(theme);
  const rule = (selector: string) => new RegExp(`(^|[},\\s])${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*[,{][^}]*`, "m").exec(theme)?.[0] ?? "";

  it("sets Inter and IBM Plex Mono, each with a system fallback", () => {
    expect(ours["--sans"]).toMatch(/^"Inter",.*sans-serif$/);
    expect(ours["--mono"]).toMatch(/^"IBM Plex Mono",.*monospace$/);
  });

  it("loads the handoff fonts instead of Figtree and JetBrains Mono", () => {
    const html = readFileSync(resolve(here, "../index.html"), "utf8");
    expect(html).toContain("family=Inter:wght@");
    expect(html).toContain("family=IBM+Plex+Mono:wght@");
    expect(html).not.toMatch(/Figtree|JetBrains/);
  });

  it("defines the handoff type scale as tokens", () => {
    for (const name of ["--fs-amount", "--fs-greeting", "--fs-title", "--fs-body", "--fs-chip", "--fs-overline", "--ls-overline", "--fs-mono"])
      expect(ours[name], name).toBeTruthy();
    expect(ours["--fs-amount"]).toBe("28px");
    expect(ours["--ls-overline"]).toBe(".07em");
  });

  it("uses tabular numerals on every phone amount", () => {
    for (const selector of [".sum-row .v", ".sum-row .v2", ".ramt", ".p-amt"])
      expect(rule(selector), selector).toContain("font-variant-numeric:tabular-nums");
  });

  it("rings focus inside the phone in 3px violet at 2px, and leaves the inspector's ring alone", () => {
    expect(theme).toMatch(/\.screen :focus-visible\{outline:3px solid var\(--hf-your-turn\);outline-offset:2px\}/);
    expect(theme).not.toMatch(/outline:2px solid var\(--a-blue\)/);  // no leftover per-element phone rings
    expect(theme).toContain(":focus-visible{outline:2px solid var(--accent);outline-offset:2px}");
    expect(theme).toContain(".irow:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}");
  });
});

describe("phone shell (LEASH-185)", () => {
  const block = (selector: string) => {
    const at = theme.indexOf(`\n${selector}{`);
    return at < 0 ? "" : theme.slice(at + 1, theme.indexOf("}", at));
  };

  it("keeps scrolled cards at their natural height, on the canvas with 18px gutters", () => {
    expect(block(".view")).toContain("display:grid");
    expect(block(".view")).toContain("grid-auto-rows:max-content");
    // one column that may shrink: an auto column grows to its widest child's min-content (the composer's input on
    // mobile Chromium) and pushed the Agent screen past the phone's edge (found in LEASH-194's screenshots)
    expect(block(".view")).toContain("grid-template-columns:minmax(0,1fr)");
    expect(block(".view")).toMatch(/padding:\d+px 18px \d+px/);
    expect(block(".screen")).toContain("background:var(--a-bg)");
  });

  it("uses the handoff screen title and status bar", () => {
    expect(block(".view h1")).toContain("font-size:var(--fs-title)");
    expect(block(".view h1")).toContain("font-weight:700");
    expect(block(".sbar")).toContain("height:42px");
  });

  it("gives the tab bar the handoff's white, divider-topped look", () => {
    expect(block(".tabs")).toContain("background:var(--a-card)");
    expect(block(".tabs")).toContain("border-top:1px solid var(--hf-divider)");
  });
});
