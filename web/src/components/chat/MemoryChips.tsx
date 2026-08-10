import { useState } from 'react'
import { BrainCircuit, X } from 'lucide-react'

import type { MemoryUsed } from '@/lib/api'

/**
 * What the assistant remembered while writing this answer.
 *
 * Rendered beside the citation chips on purpose. Seeing "page 103 of the handbook" next to
 * "prefers concise answers" in the same row is the clearest possible statement that these are
 * two different systems: one retrieved because of the question, one applied regardless of it.
 */
export function MemoryChips({ memories }: { memories: MemoryUsed[] }) {
  const [open, setOpen] = useState(false)

  if (!memories.length) return null

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
      >
        <BrainCircuit className="size-3 shrink-0 text-primary" aria-hidden />
        Remembered {memories.length} thing{memories.length === 1 ? '' : 's'} about you
      </button>

      {open && (
        <div className="mt-2 rounded-lg border border-border bg-muted/40 p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] font-medium">Applied from memory</p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close memory list"
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
          <ul className="mt-1.5 space-y-1">
            {memories.map((item) => (
              <li key={item.id} className="text-xs leading-relaxed text-muted-foreground">
                <span className="mr-1.5 rounded border border-border px-1 py-0.5 text-[10px]">
                  {item.kind}
                </span>
                {item.content}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
