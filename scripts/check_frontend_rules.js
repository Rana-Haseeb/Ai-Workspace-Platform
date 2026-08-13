/**
 * Structural rules the frontend has to keep, checked against the source.
 *
 *   node scripts/check_frontend_rules.js
 *
 * These are the rules a type checker cannot see and a unit test cannot reach, so without this
 * they are enforced by memory — which is how the scroll bug below got shipped.
 *
 * Exits non-zero on any violation.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, relative } from 'node:path'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SRC = join(ROOT, 'web/src')

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

const files = walk(SRC).filter((path) => /\.tsx?$/.test(path))
const read = (path) => readFileSync(path, 'utf8')
let failures = 0

function check(label, ok, detail = '') {
  console.log(`   ${ok ? 'OK  ' : 'FAIL'} ${label}${detail ? `  [${detail}]` : ''}`)
  if (!ok) failures++
}

console.log('\n1. Exactly one module talks HTTP')
{
  // The API surface stays discoverable in one file, and error handling stays uniform.
  const offenders = files.filter(
    (path) =>
      !path.endsWith(join('lib', 'api.ts')) &&
      /\bfetch\s*\(/.test(read(path)),
  )
  check(
    'nothing outside lib/api.ts calls fetch',
    offenders.length === 0,
    offenders.map((p) => relative(ROOT, p)).join(', '),
  )
}

console.log('\n2. The app shell can scroll')
{
  // Shipped broken once: <main> had no scroll container, so every route that was not Chat had
  // its overflow clipped by the shell and was simply unreachable below the fold. A type checker
  // cannot see this and no unit test renders layout, so it is asserted here.
  const shell = read(join(SRC, 'components/layout/AppShell.tsx'))
  const mainTag = shell.match(/<main[^>]*className="([^"]*)"/)
  check('AppShell renders a <main>', Boolean(mainTag))
  if (mainTag) {
    check(
      '<main> owns a scroll container',
      /overflow-(y-)?auto|overflow-(y-)?scroll/.test(mainTag[1]),
      mainTag[1],
    )
  }

  // Chat is the one route that manages its own scrolling; it must fill <main> exactly so the
  // two never both scroll.
  const chat = read(join(SRC, 'routes/Chat.tsx'))
  check(
    'Chat fills the shell rather than growing it',
    /h-full/.test(chat) && /overflow-hidden/.test(chat),
  )
}

console.log('\n3. Scrollbars are visible')
{
  // The browser default is a low-contrast grey that disappears against #0F172A, so a scrollable
  // panel reads as a page that simply ends.
  const css = read(join(SRC, 'index.css'))
  check('scrollbar-color is themed', /scrollbar-color/.test(css))
  check('webkit scrollbar is styled', /::-webkit-scrollbar-thumb/.test(css))
}

console.log('\n4. No emoji used as an icon')
{
  // Emoji render differently on every platform and cannot take the theme's colour.
  const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u
  const offenders = files.filter((path) => emoji.test(read(path)))
  check(
    'no emoji in any component',
    offenders.length === 0,
    offenders.map((p) => relative(ROOT, p)).join(', '),
  )
}

console.log('\n5. Chart axes cannot clip their own labels')
{
  // Shipped broken once. A negative left margin pulls the Y axis outside the plot area, which is
  // invisible while the labels are short — and then a five-digit value has its leading character
  // clipped. A real 16,000 rendered as "6000", so the axis read 6000, 2000, 8000, 4000, 0:
  // descending nonsense, on the one screen whose entire claim is that its figures are exact.
  //
  // Only found by taking a screenshot with realistic data in it. Neither a type checker nor a
  // unit test renders an axis, so the root cause is asserted here instead.
  const offenders = files.filter((path) => {
    const source = read(path)
    if (!/recharts|<BarChart|<LineChart|<AreaChart/.test(source)) return false
    return /margin=\{\{[^}]*(top|right|bottom|left)\s*:\s*-\d/.test(source)
  })
  check(
    'no negative margin on a chart',
    offenders.length === 0,
    offenders.map((p) => relative(ROOT, p)).join(', '),
  )

  // A numeric axis needs a formatter, or it prints the raw value and grows without bound.
  const dashboard = join(SRC, 'routes/Dashboard.tsx')
  const source = read(dashboard)
  check(
    'the token axis formats its ticks compactly',
    /tickFormatter=\{compactTokens\}/.test(source) && /function compactTokens/.test(source),
  )
}

if (failures > 0) {
  console.log(`\n${failures} rule violation(s).\n`)
  process.exit(1)
}
console.log('\nAll frontend rules hold.\n')
