/**
 * Contrast audit for the design tokens.
 *
 *   node scripts/check_contrast.js
 *
 * Reads the oklch values straight out of web/src/index.css, converts them to sRGB, and checks
 * every pair that carries text or defines a control's shape. Runs without a browser, so it can
 * sit in CI and in the Phase 9 accessibility evidence.
 *
 * Thresholds are WCAG 2.1 AA: 4.5:1 for body text, 3.0:1 for large text and for the boundary of
 * a user-interface component (success criterion 1.4.11).
 *
 * Exits non-zero if any pair fails.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const CSS = readFileSync(join(ROOT, 'web/src/index.css'), 'utf8')

// ------------------------------------------------------------------ colour maths
function oklchToRgb(L, C, H) {
  const hRad = (H * Math.PI) / 180
  const a = C * Math.cos(hRad)
  const b = C * Math.sin(hRad)

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b

  const l = l_ ** 3
  const m = m_ ** 3
  const s = s_ ** 3

  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]

  return linear.map((v) => {
    const clamped = Math.min(Math.max(v, 0), 1)
    const encoded = clamped <= 0.0031308 ? clamped * 12.92 : 1.055 * clamped ** (1 / 2.4) - 0.055
    return Math.round(encoded * 255)
  })
}

const relativeLuminance = ([r, g, b]) =>
  [r, g, b]
    .map((v) => {
      const c = v / 255
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    })
    .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0)

const contrast = (a, b) => {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const toHex = ([r, g, b]) =>
  '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')

// ------------------------------------------------------------- token extraction
/** Pull `--name: oklch(L C H)` declarations out of one CSS block. */
function tokensIn(blockSelector) {
  const block = CSS.split(blockSelector)[1]?.split('}')[0] ?? ''
  const tokens = {}
  for (const [, name, l, c, h] of block.matchAll(
    /--([\w-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)/g,
  )) {
    tokens[name] = oklchToRgb(Number(l), Number(c), Number(h))
  }
  return tokens
}

// Pairs that must hold. `min` is 4.5 where the foreground is body text, 3.0 where the pair
// describes a component's shape against what surrounds it.
const PAIRS = [
  ['foreground', 'background', 4.5, 'body text on the page'],
  ['muted-foreground', 'background', 4.5, 'secondary text on the page'],
  ['card-foreground', 'card', 4.5, 'text on a card'],
  ['muted-foreground', 'card', 4.5, 'secondary text on a card'],
  ['primary-foreground', 'primary', 4.5, 'label on a primary button'],
  ['primary', 'background', 3.0, 'primary button shape against the page'],
  ['sidebar-foreground', 'sidebar', 4.5, 'text in the sidebar'],
  ['brand', 'background', 3.0, 'brand accent against the page'],
  ['destructive', 'background', 4.5, 'error text on the page'],
  ['destructive', 'card', 4.5, 'error text on a card'],
  // Chart series carry no text, so 3.0 applies (WCAG 1.4.11, non-text contrast). They are
  // checked against the card because that is what a chart is drawn on.
  ['chart-1', 'card', 3.0, 'chart series 1 on a card'],
  ['chart-2', 'card', 3.0, 'chart series 2 on a card'],
  ['chart-3', 'card', 3.0, 'chart series 3 on a card'],
  ['chart-4', 'card', 3.0, 'chart series 4 on a card'],
  ['chart-5', 'card', 3.0, 'chart series 5 on a card'],
]

let failures = 0
for (const [selector, label] of [[':root {', 'light'], ['.dark {', 'dark']]) {
  const tokens = tokensIn(selector)
  console.log(`\n${label} theme`)
  for (const [fg, bg, min, description] of PAIRS) {
    if (!tokens[fg] || !tokens[bg]) {
      console.log(`  SKIP  ${description} (token not defined as oklch)`)
      continue
    }
    const ratio = contrast(tokens[fg], tokens[bg])
    const ok = ratio >= min
    if (!ok) failures++
    console.log(
      `  ${ok ? 'OK  ' : 'FAIL'}  ${ratio.toFixed(2).padStart(5)} : 1  (needs ${min})  ` +
        `${description}  [${toHex(tokens[fg])} on ${toHex(tokens[bg])}]`,
    )
  }
}

if (failures > 0) {
  console.log(`\n${failures} contrast failure(s).\n`)
  process.exit(1)
}
console.log('\nAll pairs meet WCAG AA.\n')
