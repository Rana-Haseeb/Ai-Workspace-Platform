import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Square, X } from 'lucide-react'

import { SkillPalette } from '@/components/chat/SkillPalette'
import { Button } from '@/components/ui/button'
import { skillIcon } from '@/lib/skillIcons'
import type { SkillSummary } from '@/lib/api'

/**
 * The message input.
 *
 * Enter sends, Shift+Enter breaks the line — the convention every chat product uses, so getting
 * it wrong is immediately noticeable. The textarea grows with its content up to a ceiling, past
 * which it scrolls, so a long paste does not push the send button off screen.
 *
 * Typing `/` at the start opens the skill palette. Picking a skill attaches it to the next
 * message rather than sending immediately: a skill needs input, and a palette that fires on
 * selection would leave nowhere to type it.
 */
export function Composer({
  onSend,
  onStop,
  streaming,
  placeholder = 'Ask anything',
  skills = [],
}: {
  onSend: (text: string, skillSlug?: string) => void
  onStop: () => void
  streaming: boolean
  placeholder?: string
  skills?: SkillSummary[]
}) {
  const [value, setValue] = useState('')
  const [attached, setAttached] = useState<SkillSummary | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // The palette is open while the text is a lone `/command` with no space yet.
  const paletteQuery =
    !attached && value.startsWith('/') && !value.includes(' ') ? value.slice(1) : null

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
    onSend(text, attached?.slug)
    setValue('')
    setAttached(null)
  }

  const AttachedIcon = attached ? skillIcon(attached.icon) : null

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      {paletteQuery !== null && (
        <SkillPalette
          skills={skills}
          query={paletteQuery}
          onPick={(skill) => {
            setAttached(skill)
            setValue('')
            textareaRef.current?.focus()
          }}
          onClose={() => setValue('')}
        />
      )}

      {attached && AttachedIcon && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-xs text-primary">
            <AttachedIcon className="size-3.5" aria-hidden />
            {attached.name}
            <button
              type="button"
              onClick={() => setAttached(null)}
              aria-label={`Remove ${attached.name}`}
              className="ml-0.5 hover:opacity-70"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
          <span className="text-xs text-muted-foreground">{attached.input_label}</span>
        </div>
      )}

      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            // While the palette is open it owns Enter and the arrow keys.
            if (paletteQuery !== null) return
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
            if (event.key === 'Backspace' && !value && attached) setAttached(null)
          }}
          rows={1}
          placeholder={attached ? attached.input_placeholder : placeholder}
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
        Enter to send, Shift+Enter for a new line. Type / for skills.
      </p>
    </div>
  )
}
