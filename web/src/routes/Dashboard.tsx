import { useOutletContext } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertCircle, BrainCircuit, CheckCircle2, FileText, MessagesSquare } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboard, type WorkspaceDetail } from '@/lib/api'

/**
 * One number and its label.
 *
 * Tabular figures throughout: a token count that reflows its width as it grows is distracting in
 * a row of stats that update together.
 */
function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-muted/40 px-4 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="tabular mt-0.5 text-xl font-semibold">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

const EVENT_LABEL: Record<string, string> = {
  chat: 'Chat',
  skill: 'Skills',
  upload: 'Documents',
  memory: 'Memory',
  embed: 'Embeddings',
}

/** Axis ticks that stay narrow at any magnitude: 0, 900, 4k, 16k, 1.2M. */
function compactTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`
  return String(value)
}

export default function Dashboard() {
  const workspace = useOutletContext<WorkspaceDetail>()

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', workspace.id],
    queryFn: () => dashboard.get(workspace.id),
  })

  if (isLoading || !data) {
    return <div className="px-6 py-8 text-sm text-muted-foreground">Loading…</div>
  }

  const { totals, usage, daily, by_event: byEvent, activity, top_memories: topMemories } = data
  const allFree = usage.estimated_cost_usd === 0

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every figure is counted live from the database, not from a stored total.
      </p>

      {/* ----------------------------------------------------------- contents */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Conversations" value={totals.conversations.toLocaleString()}
              hint={`${totals.messages.toLocaleString()} messages`} />
        <Stat label="Documents" value={totals.documents.toLocaleString()}
              hint={`${totals.chunks.toLocaleString()} chunks`} />
        <Stat label="Memory items" value={totals.memories.toLocaleString()} />
        <Stat label="Prompt templates" value={totals.prompts.toLocaleString()} />
        <Stat label="Tokens used" value={usage.tokens_total.toLocaleString()}
              hint={`${usage.tokens_in.toLocaleString()} in · ${usage.tokens_out.toLocaleString()} out`} />
        <Stat
          label="Estimated cost"
          value={`$${usage.estimated_cost_usd.toFixed(4)}`}
          // Said out loud rather than letting $0.00 imply the platform is free everywhere.
          hint={allFree ? `${data.provider_chain.join(' → ')} — free tier` : undefined}
        />
      </div>

      {/* ------------------------------------------------------------- speed */}
      <div className="mt-3 grid grid-cols-3 gap-3">
        <Stat label="Model calls" value={usage.calls.toLocaleString()}
              hint={usage.failed_calls ? `${usage.failed_calls} failed` : 'none failed'} />
        <Stat label="Average reply" value={`${(usage.average_latency_ms / 1000).toFixed(1)}s`} />
        <Stat label="Slowest 5%" value={`${(usage.p95_latency_ms / 1000).toFixed(1)}s`}
              hint="p95, not the worst case" />
      </div>

      {/* ------------------------------------------------------- daily tokens */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Tokens per day</CardTitle>
          <CardDescription>
            The last {daily.length} days. Quiet days are shown as zero rather than skipped.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value: string) => value.slice(5)}
                  tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  // Compact ticks, and no negative left margin.
                  //
                  // Both matter, and the bug needed both to show up: `left: -18` pulled the axis
                  // outside the plot area, which is invisible while the labels are short. At
                  // five digits the leading character was clipped, so a real 16,000 rendered as
                  // "6000" and the axis read 6000, 2000, 8000, 4000, 0 — descending nonsense on
                  // a dashboard whose whole claim is that its figures are trustworthy.
                  tickFormatter={compactTokens}
                  tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                />
                <Tooltip
                  cursor={{ fill: 'var(--muted)' }}
                  contentStyle={{
                    background: 'var(--popover)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value) => [Number(value ?? 0).toLocaleString(), 'tokens']}
                />
                <Bar dataKey="tokens" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* --------------------------------------------------- where tokens went */}
      {byEvent.length > 0 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">Where the tokens went</CardTitle>
            <CardDescription>
              Chat is not the only thing that costs tokens — embedding, memory extraction and
              skills all show up here.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byEvent} layout="vertical"
                          margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="event"
                    tickFormatter={(value: string) => EVENT_LABEL[value] ?? value}
                    tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    tickLine={false}
                    axisLine={false}
                    width={80}
                  />
                  <Tooltip
                    cursor={{ fill: 'var(--muted)' }}
                    contentStyle={{
                      background: 'var(--popover)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={(value, _name, item) => [
                      `${Number(value ?? 0).toLocaleString()} tokens`,
                      `${(item?.payload as { calls?: number } | undefined)?.calls ?? 0} calls`,
                    ]}
                  />
                  <Bar dataKey="tokens" radius={[0, 3, 3, 0]}>
                    {byEvent.map((entry, index) => (
                      <Cell key={entry.event} fill={`var(--chart-${(index % 5) + 1})`} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------- top memories */}
      {topMemories.length > 0 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">Memories that shape answers</CardTitle>
            <CardDescription>The ones actually applied, most-used first.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {topMemories.map((memory) => (
                <li key={memory.content} className="flex items-start gap-2.5 text-sm">
                  <BrainCircuit className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
                  <span className="flex-1">{memory.content}</span>
                  <span className="tabular shrink-0 text-xs text-muted-foreground">
                    {memory.use_count}x
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* ----------------------------------------------------- recent activity */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Recent activity</CardTitle>
        </CardHeader>
        <CardContent>
          {activity.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nothing yet. Send a message or upload a document.
            </p>
          )}
          <ul className="space-y-2.5">
            {activity.map((entry, index) => {
              const Icon =
                entry.event === 'upload' ? FileText
                : entry.event === 'memory' ? BrainCircuit
                : MessagesSquare
              return (
                <li key={index} className="flex items-start gap-2.5 text-sm">
                  {entry.status === 'ok' ? (
                    <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  ) : (
                    <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{EVENT_LABEL[entry.event] ?? entry.event}</span>
                    {entry.detail && (
                      <span className="ml-1.5 text-muted-foreground">{entry.detail}</span>
                    )}
                  </span>
                  <span className="tabular shrink-0 text-[11px] text-muted-foreground">
                    {entry.tokens > 0 && `${entry.tokens.toLocaleString()} tok`}
                    {entry.latency_ms > 0 && ` · ${(entry.latency_ms / 1000).toFixed(1)}s`}
                  </span>
                </li>
              )
            })}
          </ul>
        </CardContent>
      </Card>

      <p className="mt-6 flex items-center gap-1.5 text-xs text-muted-foreground">
        <CheckCircle2 className="size-3.5" aria-hidden />
        Counted live from the database — a test asserts these match raw SQL.
      </p>
    </div>
  )
}
