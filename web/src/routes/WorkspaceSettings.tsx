import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { Check, Loader2, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { workspaces, type AssistantSettings, type WorkspaceDetail } from '@/lib/api'

const DEPLOYMENT_DEFAULT = '__default__'

const TOKEN_CHOICES = [512, 1024, 2048, 4096, 8192]

/** Plain-language description of what each temperature actually does. */
function temperatureHint(value: number): string {
  if (value <= 0.2) return 'Near-deterministic. Same question, near-identical answer.'
  if (value <= 0.6) return 'Focused. Good for factual work and document questions.'
  if (value <= 1.0) return 'Balanced. Some variation between runs.'
  if (value <= 1.5) return 'Creative. Noticeably different each time.'
  return 'Very loose. Expect tangents.'
}

export default function WorkspaceSettings() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data: meta } = useQuery({ queryKey: ['workspace-meta'], queryFn: workspaces.meta })
  const [form, setForm] = useState<AssistantSettings>(workspace.settings)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Re-seed when the user switches workspace without leaving this screen.
  useEffect(() => setForm(workspace.settings), [workspace.id, workspace.settings])

  const dirty = JSON.stringify(form) !== JSON.stringify(workspace.settings)

  const save = useMutation({
    mutationFn: () => workspaces.updateSettings(workspace.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace', String(workspace.id)] })
      setError(null)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2500)
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : 'Could not save the changes.'),
  })

  const remove = useMutation({
    mutationFn: () => workspaces.remove(workspace.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      navigate('/', { replace: true })
    },
  })

  const set = <K extends keyof AssistantSettings>(key: K, value: AssistantSettings[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Assistant settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            These apply to every conversation in {workspace.name}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved && !dirty && (
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Check className="size-4" aria-hidden />
              Saved
            </span>
          )}
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save changes
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* ---------------------------------------------------------------- identity */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Identity</CardTitle>
          <CardDescription>Who the assistant is and what it is for.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="assistant-name">Assistant name</Label>
            <Input
              id="assistant-name"
              value={form.assistant_name}
              onChange={(event) => set('assistant_name', event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="role">Role</Label>
            <Input
              id="role"
              value={form.role}
              onChange={(event) => set('role', event.target.value)}
              placeholder="Compares vector databases for a small team"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="system-prompt">System prompt</Label>
            <Textarea
              id="system-prompt"
              rows={5}
              value={form.system_prompt}
              onChange={(event) => set('system_prompt', event.target.value)}
              className="font-mono text-xs leading-relaxed"
            />
            <p className="text-xs text-muted-foreground">
              Sent before every message in this workspace.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* --------------------------------------------------------------- behaviour */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Behaviour</CardTitle>
          <CardDescription>How it writes, and how much it varies.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-3">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="temperature">Temperature</Label>
              <span className="tabular text-sm font-medium">{form.temperature.toFixed(1)}</span>
            </div>
            <Slider
              id="temperature"
              min={0}
              max={2}
              step={0.1}
              value={form.temperature}
              onValueChange={(value) =>
                // Rounded because floating-point steps produce values like 0.7000000000000001,
                // which the API would store verbatim.
                set('temperature', Math.round((value as number) * 10) / 10)
              }
            />
            <p className="text-xs text-muted-foreground">{temperatureHint(form.temperature)}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="personality">Personality</Label>
              <Select
                value={form.personality}
                onValueChange={(value) => set('personality', value as string)}
              >
                <SelectTrigger id="personality">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(meta?.personalities ?? [form.personality]).map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="response-style">Response style</Label>
              <Select
                value={form.response_style}
                onValueChange={(value) => set('response_style', value as string)}
              >
                <SelectTrigger id="response-style">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(meta?.response_styles ?? [form.response_style]).map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------- model */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Model</CardTitle>
          <CardDescription>
            If the chosen model is rate limited or down, the platform falls back to another
            provider automatically.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="model">Model</Label>
            <Select
              value={form.model ?? DEPLOYMENT_DEFAULT}
              onValueChange={(value) =>
                set('model', value === DEPLOYMENT_DEFAULT ? null : (value as string))
              }
            >
              <SelectTrigger id="model">
                {/* Base UI's SelectValue prints the raw value unless given a formatter, which
                    leaked the "__default__" sentinel into the UI. */}
                <SelectValue>
                  {(value) =>
                    value === DEPLOYMENT_DEFAULT
                      ? 'Deployment default'
                      : (meta?.models.find((m) => m.id === value)?.label ?? String(value))
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEPLOYMENT_DEFAULT}>Deployment default</SelectItem>
                {(meta?.models ?? []).map((option) => (
                  <SelectItem key={option.id} value={option.id}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="max-tokens">Maximum tokens</Label>
            <Select
              value={String(form.max_tokens)}
              onValueChange={(value) => set('max_tokens', Number(value))}
            >
              <SelectTrigger id="max-tokens">
                {/* Thousands separator, so the trigger matches the options rather than showing
                    a bare "2048" next to a list of "2,048". */}
                <SelectValue>{(value) => Number(value).toLocaleString()}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {TOKEN_CHOICES.map((option) => (
                  <SelectItem key={option} value={String(option)}>
                    {option.toLocaleString()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Ceiling on one reply, not on cost.</p>
          </div>
        </CardContent>
      </Card>

      {/* -------------------------------------------------------------- capabilities */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Capabilities</CardTitle>
          <CardDescription>What the assistant is allowed to draw on.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="text-sm font-medium">Long-term memory</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                Remembers your preferences and recurring topics across sessions.
              </span>
            </span>
            <Switch
              checked={form.use_memory}
              onCheckedChange={(checked) => set('use_memory', checked)}
              aria-label="Long-term memory"
            />
          </label>

          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="text-sm font-medium">Knowledge base</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                Searches this workspace's documents and cites what it used.
              </span>
            </span>
            <Switch
              checked={form.use_knowledge_base}
              onCheckedChange={(checked) => set('use_knowledge_base', checked)}
              aria-label="Knowledge base"
            />
          </label>
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ danger */}
      <Card className="mt-4 border-destructive/40">
        <CardHeader>
          <CardTitle className="text-base">Delete workspace</CardTitle>
          <CardDescription>
            Removes {workspace.name} and everything in it — conversations, documents and memory
            scoped to it. This cannot be undone.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            className="border-destructive/50 text-destructive hover:bg-destructive/10"
            onClick={() => {
              if (window.confirm(`Delete "${workspace.name}" and everything in it?`)) {
                remove.mutate()
              }
            }}
            disabled={remove.isPending}
          >
            {remove.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-4" aria-hidden />
            )}
            Delete this workspace
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
