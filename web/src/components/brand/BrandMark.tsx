/**
 * The product mark: a claim tethered to its source.
 *
 * A speech bubble, a stepped tether, and the page it came from. It is the one shape that says
 * what this platform is for — every answer traceable to a document page — rather than "AI" in
 * general, which is what the placeholder sparkles icon said.
 *
 * Drawn on a 32-unit grid so it lines up with lucide's, and filled with `currentColor` so it
 * takes the theme instead of hard-coding indigo. That matters: `--primary` is #4338CA in light
 * and a lighter #5B54EA in dark, and `scripts/check_contrast.js` already verifies
 * primary-against-background at 3:1 in both. A hard-coded fill would silently fail dark mode.
 *
 * The page is a solid rectangle with no interior detail, which is what keeps the mark readable
 * at 16px in a browser tab.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      fill="none"
      role="img"
      aria-label="AI Workspace"
    >
      {/* The claim. */}
      <path
        d="M4.4 2h12.2a2.4 2.4 0 0 1 2.4 2.4v7.4a2.4 2.4 0 0 1-2.4 2.4h-4.9l-3.3 2.9a.6.6 0 0 1-1-.45V14.2H4.4A2.4 2.4 0 0 1 2 11.8V4.4A2.4 2.4 0 0 1 4.4 2Z"
        fill="currentColor"
      />
      {/* The tether. Steps down and across in clear space, so it survives shrinking. */}
      <path
        d="M8 19.4V25.6H18.2"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* The source. */}
      <rect x="20.4" y="17.6" width="9.6" height="12" rx="2" fill="currentColor" />
    </svg>
  )
}
