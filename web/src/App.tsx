import { Moon, Sun, Database, ShieldCheck, Palette, Type } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { useTheme } from '@/hooks/useTheme'

/**
 * Phase 0 verification screen.
 *
 * Its only job is to prove the foundations render: both themes, the type scale, every semantic
 * colour token, and the shadcn primitives the rest of the app is built from. Phase 2 replaces
 * this with the real app shell.
 */

const SWATCHES = [
  { token: 'bg-background', label: 'background' },
  { token: 'bg-card', label: 'card' },
  { token: 'bg-muted', label: 'muted' },
  { token: 'bg-primary', label: 'primary' },
  { token: 'bg-brand', label: 'brand' },
  { token: 'bg-destructive', label: 'destructive' },
] as const

const CHECKS = [
  { icon: Database, label: '12 tables', detail: 'users through logs, all indexed' },
  { icon: ShieldCheck, label: 'Secrets safe', detail: '.env is gitignored' },
  { icon: Palette, label: 'Two themes', detail: 'dark primary, light toggle' },
  { icon: Type, label: 'Inter', detail: 'self-hosted, tabular figures' },
] as const

export default function App() {
  const { theme, toggle } = useTheme()

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight">AI Workspace Platform</h1>
              <Badge variant="secondary">Phase 0</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Foundations verified. Database, configuration, and design system are in place.
            </p>
          </div>
          <Button variant="outline" size="icon" onClick={toggle} aria-label="Toggle theme">
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        </header>

        <Separator className="my-8" />

        <div className="grid gap-4 sm:grid-cols-2">
          {CHECKS.map(({ icon: Icon, label, detail }) => (
            <Card key={label}>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-primary" aria-hidden />
                  <CardTitle className="text-base">{label}</CardTitle>
                </div>
                <CardDescription>{detail}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Colour tokens</CardTitle>
            <CardDescription>
              Every one is defined for both themes. Toggle above to check contrast in each.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
              {SWATCHES.map(({ token, label }) => (
                <div key={label} className="space-y-1.5">
                  <div className={`h-12 rounded-md border border-border ${token}`} />
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              ))}
            </div>

            <Separator className="my-6" />

            <div className="flex flex-wrap items-center gap-6">
              <div>
                <p className="text-xs text-muted-foreground">Tokens used</p>
                <p className="tabular text-2xl font-semibold">1,284,096</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Estimated cost</p>
                <p className="tabular text-2xl font-semibold">$0.00</p>
              </div>
              <div className="flex gap-2">
                <Button>Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="outline">Outline</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
