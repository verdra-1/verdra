// SPDX-FileCopyrightText: 2026 q0f7
// SPDX-License-Identifier: Apache-2.0
//
// D2 mock-up renderer. Reads the real design tokens from
// src/verdra/assets/brand/tokens.json, injects them as CSS custom properties (so the mock-ups
// carry no colour literals of their own), loads the real fonts, and screenshots each screen in
// both themes at 100 % and 200 % text scale with Playwright.
//
//   node docs/design/d2/render.mjs            render every screen in screens/ to renders/
//   node docs/design/d2/render.mjs 03-status  render only the matching screen(s)
//
// The grounds and every other colour come straight from tokens.json (the real Part-B tokens);
// decision record 0027's warm-paper shift is a proposed D3 token change, noted in README.md.

import { readFileSync, readdirSync, mkdirSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join, basename } from "node:path";
import { createRequire } from "node:module";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..", "..");
// Resolve playwright from the repo root, where it is installed (bare ESM import can't find it).
const { chromium } = createRequire(pathToFileURL(join(ROOT, "noop.cjs")))("playwright");
const TOKENS = JSON.parse(readFileSync(join(ROOT, "src/verdra/assets/brand/tokens.json"), "utf8"));
const FONTS = join(ROOT, "src/verdra/assets/fonts");
const SCREENS = join(HERE, "screens");
const OUT = join(HERE, "renders");

const THEMES = ["light", "dark"];
const SCALES = [100, 200];
// The default window from the D1 gallery; law 1 must hold at 200 % here too.
const VIEWPORT = { width: 1200, height: 760 };

function resolveColor(value, theme, raw) {
  if (value && typeof value === "object") value = value[theme] ?? value.light;
  if (typeof value === "string" && value.startsWith("{") && value.endsWith("}")) {
    return resolveColor(raw[value.slice(1, -1)], theme, raw);
  }
  return value;
}

function cssVars(theme, scale) {
  const raw = Object.fromEntries(TOKENS.color.tokens.map((t) => [t.name, t.value]));
  const lines = [];
  for (const t of TOKENS.color.tokens) {
    lines.push(`--color-${t.name}: ${resolveColor(t.value, theme, raw)};`);
  }
  for (const s of TOKENS.spacing.tokens) lines.push(`--${s.name}: ${s.value};`);
  for (const r of TOKENS.radius.tokens) lines.push(`--${r.name}: ${r.value};`);
  for (const l of TOKENS.layout.tokens) lines.push(`--${l.name}: ${l.value};`);
  const f = scale / 100;
  for (const st of TOKENS.type.styles) {
    lines.push(`--text-${st.name}-size: ${(st.size * f).toFixed(2)}px;`);
    lines.push(`--text-${st.name}-line: ${(st.lineHeight * f).toFixed(2)}px;`);
    lines.push(`--text-${st.name}-weight: ${st.weight};`);
    lines.push(`--text-${st.name}-tracking: ${((st.trackingPercent || 0) / 100).toFixed(3)}em;`);
  }
  const fam = TOKENS.type.families;
  lines.push(`--font-display: ${fam.display.map((x) => `"${x}"`).join(", ")};`);
  lines.push(`--font-sans: ${fam.sans.map((x) => `"${x}"`).join(", ")};`);
  lines.push(`--font-mono: ${fam.mono.map((x) => `"${x}"`).join(", ")};`);
  return `:root{\n${lines.join("\n")}\n}`;
}

function fontFaces() {
  const face = (family, file, weight) =>
    `@font-face{font-family:"${family}";src:url("file://${join(FONTS, file)}") format("truetype");` +
    `font-weight:${weight};font-style:normal;font-display:block;}`;
  return [
    face("Atkinson Hyperlegible Next", "AtkinsonHyperlegibleNext-Regular.ttf", 400),
    face("Atkinson Hyperlegible Next", "AtkinsonHyperlegibleNext-SemiBold.ttf", 600),
    face("Sora", "Sora-SemiBold.ttf", 600),
    face("JetBrains Mono", "JetBrainsMono-Regular.ttf", 400),
  ].join("\n");
}

const base = readFileSync(join(SCREENS, "base.css"), "utf8");

// A whole-leaf glyph (currentColor) for the header/tray status; the state sets the colour var.
const LEAF_COLOR = {
  working: "success", waiting: "success", "needs-you": "warning", stopped: "danger", off: "ink-muted",
};
function leaf(state, cls = "leaf") {
  return (
    `<svg class="${cls}" viewBox="0 0 64 64" style="color:var(--color-${LEAF_COLOR[state] || "ink-muted"})">` +
    `<path fill="currentColor" d="M5 6C3 25 13 44 31.2 55.5C26 41 19 24 5 6Z"/>` +
    `<path fill="currentColor" d="M59 12C60 29 50 45 32.8 55.5C37 43 44 27 59 12Z"/>` +
    `<circle fill="currentColor" cx="32" cy="59.6" r="3.4"/></svg>`
  );
}

// A static brand leaf in ink (the window icon and the sidebar mark; never status-coloured).
function brandMark(cls, color = "ink") {
  return (
    `<svg class="${cls}" viewBox="0 0 64 64" style="color:var(--color-${color})">` +
    `<path fill="currentColor" d="M5 6C3 25 13 44 31.2 55.5C26 41 19 24 5 6Z"/>` +
    `<path fill="currentColor" d="M59 12C60 29 50 45 32.8 55.5C37 43 44 27 59 12Z"/>` +
    `<circle fill="currentColor" cx="32" cy="59.6" r="3.4"/></svg>`
  );
}

// Main screens at the top; Activity, Settings and About at the foot (plan 7.1). Traffic is
// Advanced-only, so it isn't in the default view.
const NAV = [
  ["replacements", "Replacements", `<path d="M5 19C5 10.5 10.5 5 19 5c0 8.5-5.5 14-14 14z"/><path d="M5 19l8-8"/>`],
  ["library", "Library", `<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/>`],
  ["tweaks", "Tweaks", `<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>`],
  ["accounts", "Accounts", `<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>`],
];
const FOOT = [
  ["activity", "Activity", `<path d="M3 12h4l3 8 4-16 3 8h4"/>`],
  ["settings", "Settings", `<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>`],
  ["about", "About", `<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>`],
];

function navLink(active, [id, label, ico]) {
  const cls = id === active ? "active" : "";
  const later = id === "library"
    ? ` <span class="caption later">coming later</span>`
    : "";
  return `<a class="${cls}" href="#"><svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ico}</svg>${label}${later}</a>`;
}

function shell(active, title, status, word, content) {
  const nav = NAV.map((e) => navLink(active, e)).join("");
  const foot = FOOT.map((e) => navLink(active, e)).join("");
  // The native title bar (0027 §2) is drawn by Windows; it is shown here as the tinted strip with
  // the window icon (the static leaf) and title. The brand and the status leaf live in the app,
  // not the OS bar: the brand at the sidebar top, the status leaf in the header.
  return `<div class="window">
    <div class="titlebar">${brandMark("mark", "ink-muted")}<span class="app">Verdra</span>
      <span class="caption"><span>&#8211;</span><span>&#9633;</span><span>&#10005;</span></span></div>
    <div class="body">
      <aside class="sidebar">
        <div class="brand">${brandMark("mark")}<span class="name">Verdra</span></div>
        <nav class="nav">${nav}</nav>
        <div class="spacer"></div>
        <nav class="nav">${foot}</nav>
        <div class="profilecard"><div class="label">Profile</div><div class="name">My replacements</div><div class="caption">5 replacements</div></div>
        <button class="chevron" aria-label="Collapse the sidebar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg></button>
      </aside>
      <main class="main">
        <div class="header"><h1>${title}</h1><div class="grow"></div>
          <div class="status">${leaf(status)}<span class="word">${word}</span></div></div>
        ${content}
      </main>
    </div></div>`;
}

const DIRECTIVE = /^\s*<!--\s*shell\s+active="([^"]*)"\s+title="([^"]*)"\s+status="([^"]*)"\s+word="([^"]*)"\s*-->/;

function screenBody(raw) {
  const m = raw.match(DIRECTIVE);
  if (!m) return raw;
  return shell(m[1], m[2], m[3], m[4], raw.slice(m[0].length));
}

function page(bodyHtml, theme, scale) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFaces()}
${cssVars(theme, scale)}
${base}
</style></head><body data-theme="${theme}">${bodyHtml}</body></html>`;
}

const filter = process.argv[2];
const screens = readdirSync(SCREENS)
  .filter((f) => f.endsWith(".html"))
  .filter((f) => !filter || f.includes(filter));

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
for (const file of screens) {
  const name = basename(file, ".html");
  const body = screenBody(readFileSync(join(SCREENS, file), "utf8"));
  for (const theme of THEMES) {
    for (const scale of SCALES) {
      const p = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 2 });
      await p.setContent(page(body, theme, scale), { waitUntil: "load" });
      await p.evaluate(() => document.fonts.ready);
      await p.screenshot({ path: join(OUT, `${name}-${theme}-${scale}.png`) });
      await p.close();
      console.log(`${name}-${theme}-${scale}.png`);
    }
  }
}
await browser.close();
