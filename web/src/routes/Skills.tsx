import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, Check, Copy, FileText, Loader2, Play } from 'lucide-react'

import { CitationChips } from '@/components/chat/CitationChips'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { skillIcon } from '@/lib/skillIcons'
import { skills, type SkillRunResult, type SkillSummary, type WorkspaceDetail } from '@/lib/api'

export default function Skills() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const [active, setActive] = useState<SkillSummary | null>(null)
  const [input, setInput] = useState('')
  const [result, setResult] = useState<SkillRunResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const { data } = useQuery({
    queryKey: ['skills', workspace.id],
    queryFn: () => skills.list(workspace.id),
  })

  const run = useMutation({
    mutationFn: () => skills.run(workspace.id, active!.slug, input.trim()),
    onSuccess: (value) => {
      setResult(value)
      setError(null)
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : 'The skill failed to run.'),
  })

  function open(skill: SkillSummary) {
    setActive(skill)
    setInput('')
    setResult(null)
    setError(null)
  }

  // Group for display, so nine skills read as four short lists rather than one long one.
  const grouped = (data ?? []).reduce<Record<string, SkillSummary[]>>((acc, skill) => {
    ;(acc[skill.category] ??= []).push(skill)
    return acc
  }, {})

  if (active) {
    const Icon = skillIcon(active.icon)
    return (
      <div className="mx-auto w-full max-w-2xl px-6 py-8">
        <Button variant="ghost" size="sm" onClick={() => setActive(null)} className="mb-4">
          ← All skills
        </Button>

        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
            <Icon className="size-5 text-muted-foreground" aria-hidden />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{active.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{active.description}</p>
          </div>
        </div>

        {active.uses_documents && (
          <p className="mt-4 flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <FileText className="size-3.5 shrink-0" aria-hidden />
            Searches this workspace&rsquo;s documents and cites what it used.
          </p>
        )}

        <div className="mt-6 space-y-2">
          <label htmlFor="skill-input" className="text-sm font-medium">
            {active.input_label}
          </label>
          <Textarea
            id="skill-input"
            rows={7}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={active.input_placeholder}
          />
          {active.examples.length > 0 && !input && (
            <p className="text-xs text-muted-foreground">
              For example: {active.examples[0]}
            </p>
          )}
        </div>

        <Button
          className="mt-4"
          onClick={() => input.trim() && run.mutate()}
          disabled={!input.trim() || run.isPending}
        >
          {run.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Play className="size-4" aria-hidden />
          )}
          Run {active.name}
        </Button>

        {error && (
          <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {error}
          </p>
        )}

        {result && (
          <div className="mt-6 rounded-lg border border-border">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <p className="tabular text-xs text-muted-foreground">
                {result.model} · {(result.latency_ms / 1000).toFixed(1)}s ·{' '}
                {result.tokens_out.toLocaleString()} tokens out
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(result.output)
                  setCopied(true)
                  window.setTimeout(() => setCopied(false), 2000)
                }}
              >
                {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <div className="px-4 py-3">
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{result.output}</p>
              <CitationChips citations={result.citations} />
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Skills</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Reusable tasks that work in every workspace. Type <kbd className="rounded border border-border px-1">/</kbd> in
        the chat box to run one there instead.
      </p>

      {Object.entries(grouped).map(([category, list]) => (
        <section key={category} className="mt-6">
          <h2 className="text-xs uppercase tracking-wide text-muted-foreground">{category}</h2>
          <div className="mt-2 space-y-2">
            {list.map((skill) => {
              const Icon = skillIcon(skill.icon)
              return (
                <button
                  key={skill.slug}
                  type="button"
                  onClick={() => open(skill)}
                  className="flex w-full items-start gap-3 rounded-lg border border-border px-4 py-3 text-left transition-colors hover:border-primary/50"
                >
                  <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-medium">{skill.name}</span>
                      {skill.uses_documents && (
                        <FileText className="size-3 text-muted-foreground" aria-label="Uses documents" />
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {skill.description}
                    </span>
                  </span>
                  {skill.use_count > 0 && (
                    <span className="tabular shrink-0 text-[11px] text-muted-foreground">
                      {skill.use_count}x
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </section>
      ))}

      {data?.length === 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">No skills registered</CardTitle>
            <CardDescription>Add one in skills/builtin and register it.</CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}
