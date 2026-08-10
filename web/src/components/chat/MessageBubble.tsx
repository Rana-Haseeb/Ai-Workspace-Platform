import { Pin, Sparkles } from 'lucide-react'

import { CitationChips } from '@/components/chat/CitationChips'
import type { Message } from '@/lib/api'

/**
 * One turn in the transcript.
 *
 * The two roles are shaped differently on purpose: the user's message is a bounded card aligned
 * right, the assistant's is full-width flowing text. That mirrors how they are read — you skim
 * your own question and read the answer — and it means the roles stay distinguishable without
 * relying on colour alone.
 */
export function MessageBubble({
  message,
  streaming = false,
  assistantName,
  onTogglePin,
}: {
  message: Message
  streaming?: boolean
  assistantName: string
  onTogglePin?: () => void
}) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="group max-w-[80%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5">
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="group flex gap-3">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary">
        <Sparkles className="size-3.5 text-primary-foreground" aria-hidden />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-medium">{assistantName}</span>
          {message.model && !streaming && (
            <span className="text-[11px] text-muted-foreground">{message.model}</span>
          )}
          {message.latency_ms > 0 && !streaming && (
            <span className="tabular text-[11px] text-muted-foreground">
              {(message.latency_ms / 1000).toFixed(1)}s
            </span>
          )}
          {onTogglePin && !streaming && (
            <button
              type="button"
              onClick={onTogglePin}
              aria-label={message.is_pinned ? 'Unpin message' : 'Pin message'}
              aria-pressed={message.is_pinned}
              className={[
                'ml-auto rounded p-1 transition-opacity',
                message.is_pinned
                  ? 'text-primary opacity-100'
                  : 'text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
              ].join(' ')}
            >
              <Pin className="size-3.5" aria-hidden />
            </button>
          )}
        </div>

        <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
          {message.content}
          {streaming && (
            // A caret that keeps blinking while tokens arrive, so a pause reads as thinking
            // rather than as a hang.
            <span
              className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-primary"
              aria-hidden
            />
          )}
        </p>

        {/* Shown during streaming too: the sources are known before the answer is written, and
            seeing what is being consulted is reassuring while you wait. */}
        <CitationChips citations={message.citations} />
      </div>
    </div>
  )
}
