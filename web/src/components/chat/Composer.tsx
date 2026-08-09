import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Square } from 'lucide-react'

import { Button } from '@/components/ui/button'

/**
 * The message input.
 *
 * Enter sends, Shift+Enter breaks the line — the convention every chat product uses, so getting
 * it wrong is immediately noticeable. The textarea grows with its content up to a ceiling, past
 * which it scrolls, so a long paste does not push the send button off screen.
 */
export function Composer({
  onSend,
  onStop,
  streaming,
  placeholder = 'Ask anything',
}: {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
  placeholder?: string
}) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [value])

  // Focus returns to the input when a reply finishes, so the next question needs no click.
  useEffect(() => {
    if (!streaming) textareaRef.current?.focus()
  }, [streaming])

  function submit() {
    const text = value.trim()
    if (!text || streaming) return
    onSend(text)
    setValue('')
  }

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          rows={1}
          placeholder={placeholder}
          aria-label="Message"
          className="max-h-50 min-h-9 flex-1 resize-none rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />

        {streaming ? (
          <Button variant="outline" size="icon" onClick={onStop} aria-label="Stop generating">
            <Square className="size-3.5" aria-hidden />
          </Button>
        ) : (
          <Button size="icon" onClick={submit} disabled={!value.trim()} aria-label="Send message">
            <ArrowUp className="size-4" aria-hidden />
          </Button>
        )}
      </div>

      <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-muted-foreground">
        Enter to send, Shift+Enter for a new line.
      </p>
    </div>
  )
}
