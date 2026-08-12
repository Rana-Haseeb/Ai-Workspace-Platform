import {
  AlignLeft,
  ClipboardList,
  Code,
  FileText,
  LayoutGrid,
  Lightbulb,
  ListChecks,
  Mail,
  Search,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'

/**
 * Icon names declared by skills, mapped to components.
 *
 * Explicit rather than a dynamic lookup, for the same reasons as the workspace icons: only these
 * reach the bundle, and a typo fails at build time instead of rendering nothing. A skill whose
 * icon is not listed falls back to the sparkles mark rather than breaking the page — a missing
 * icon should never be the reason a new skill appears broken.
 */
const SKILL_ICONS: Record<string, LucideIcon> = {
  'align-left': AlignLeft,
  search: Search,
  'clipboard-list': ClipboardList,
  'list-checks': ListChecks,
  'layout-grid': LayoutGrid,
  'file-text': FileText,
  mail: Mail,
  code: Code,
  lightbulb: Lightbulb,
}

export function skillIcon(name: string): LucideIcon {
  return SKILL_ICONS[name] ?? Sparkles
}
