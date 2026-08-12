import { useEffect, useState } from 'react'

import { skillIcon } from '@/lib/skillIcons'
import type { SkillSummary } from '@/lib/api'

/**
 * The `/` command palette above the composer.
 *
 * Opens when the message starts with `/` and filters as you type. Arrow keys move, Enter picks,
 * Escape closes — the conventions every command palette shares, so nobody has to learn this one.
 *
 * The selected index is reset whenever the filter changes: leaving the highlight on row four
 * while the list shrinks to two is how a palette runs the wrong command.
 */
export function SkillPalette({
  skills,
  query,
  onPick,
  onClose,
}: {
  skills: SkillSummary[]
  query: string
  onPick: (skill: SkillSummary) => void
  onClose: () => void
}) {
  const filtered = skills.filter(
    (skill) =>
      skill.slug.includes(query.toLowerCase()) ||
      skill.name.toLowerCase().includes(query.toLowerCase()),
  )
  const [selected, setSelected] = useState(0)

  useEffect(() => setSelected(0), [query])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (!filtered.length) return
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSelected((current) => (current + 1) % filtered.length)
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSelected((current) => (current - 1 + filtered.length) % filtered.length)
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault()
        onPick(filtered[selected])
      }
    }
    // Capture, so the composer's own Enter handler does not send the "/summ" text as a message.
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [filtered, selected, onPick, onClose])

  if (!filtered.length) return null

  return (
    <div
      role="listbox"
      aria-label="Skills"
      className="mx-auto mb-2 max-h-64 max-w-3xl overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
    >
      {filtered.map((skill, index) => {
        const Icon = skillIcon(skill.icon)
        return (
          <button
            key={skill.slug}
            type="button"
            role="option"
            aria-selected={index === selected}
            onMouseEnter={() => setSelected(index)}
            onClick={() => onPick(skill)}
            className={`flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors ${
              index === selected ? 'bg-accent' : ''
            }`}
          >
            <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{skill.name}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {skill.description}
              </span>
            </span>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
              /{skill.slug}
            </span>
          </button>
        )
      })}
    </div>
  )
}
