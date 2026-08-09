import {
  BookOpen,
  Briefcase,
  ChartBar,
  Code,
  FlaskConical,
  Folder,
  GraduationCap,
  Megaphone,
  PenTool,
  Rocket,
  Scale,
  Stethoscope,
  type LucideIcon,
} from 'lucide-react'

/**
 * Maps the icon names the API stores to lucide components.
 *
 * Explicit rather than a dynamic lookup on the lucide namespace: an explicit map is
 * tree-shakeable (only these twelve reach the bundle) and it fails at build time if a name is
 * wrong, instead of rendering nothing at runtime.
 *
 * The keys must stay in step with `WORKSPACE_ICONS` in `schemas/workspace.py`. A test in Phase 9
 * asserts the two lists match.
 */
export const WORKSPACE_ICONS: Record<string, LucideIcon> = {
  folder: Folder,
  flask: FlaskConical,
  briefcase: Briefcase,
  'graduation-cap': GraduationCap,
  code: Code,
  'pen-tool': PenTool,
  'chart-bar': ChartBar,
  megaphone: Megaphone,
  scale: Scale,
  stethoscope: Stethoscope,
  rocket: Rocket,
  'book-open': BookOpen,
}

/** Never returns undefined — an unknown name falls back rather than crashing the render. */
export function workspaceIcon(name: string): LucideIcon {
  return WORKSPACE_ICONS[name] ?? Folder
}
