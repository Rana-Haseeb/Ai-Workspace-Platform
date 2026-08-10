import { useState } from 'react'
import { FileText, X } from 'lucide-react'

import type { Citation } from '@/lib/api'

/**
 * The sources behind one answer.
 *
 * A chip shows the filename and page; clicking it opens the exact text the model was given.
 * That last part is what separates a citation from a decoration — the reader can check the
 * claim against the passage without leaving the conversation.
 */
export function CitationChips({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<Citation | null>(null)

  if (!citations.length) return null

  return (
    <div className="mt-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground">Sources</span>
        {citations.map((citation, index) => (
          <button
            key={citation.chunk_id}
            type="button"
            onClick={() => setOpen(citation)}
            title={`${citation.filename}${citation.page ? `, page ${citation.page}` : ''}`}
            className="inline-flex max-w-56 items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          >
            <span className="font-medium text-primary">{index + 1}</span>
            <FileText className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{citation.filename}</span>
            {citation.page && <span className="shrink-0 tabular">p{citation.page}</span>}
          </button>
        ))}
      </div>

      {open && (
        <div className="mt-2 rounded-lg border border-border bg-muted/40 p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] font-medium">
              {open.filename}
              {open.page && <span className="text-muted-foreground"> · page {open.page}</span>}
            </p>
            <button
              type="button"
              onClick={() => setOpen(null)}
              aria-label="Close excerpt"
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
          <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
            {open.snippet}
          </p>
        </div>
      )}
    </div>
  )
}
