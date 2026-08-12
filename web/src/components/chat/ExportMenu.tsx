import { useState } from 'react'
import { Download, FileDown, Loader2, Printer } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { dashboard } from '@/lib/api'

/**
 * Export one conversation.
 *
 * Markdown is fetched from the server. PDF is produced by the **browser's** print engine against
 * a clean print view, rather than by a server-side renderer — WeasyPrint, wkhtmltopdf and
 * headless Chrome are all heavy dependencies with their own install and failure modes, and the
 * browser already does this well. The trade is stated in the README rather than hidden.
 */
export function ExportMenu({
  workspaceId,
  conversationId,
  title,
}: {
  workspaceId: number
  conversationId: number
  title: string
}) {
  const [busy, setBusy] = useState(false)

  async function downloadMarkdown() {
    setBusy(true)
    try {
      const markdown = await dashboard.exportConversation(workspaceId, conversationId)
      const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `${title.replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 60) || 'conversation'}.md`
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      setBusy(false)
    }
  }

  async function printToPdf() {
    setBusy(true)
    try {
      const markdown = await dashboard.exportConversation(workspaceId, conversationId)
      const frame = document.createElement('iframe')
      // Off-screen rather than display:none — a hidden iframe does not lay out, and printing an
      // unlaid-out document produces a blank page.
      frame.style.cssText = 'position:fixed;right:100%;bottom:100%;width:800px;height:1000px'
      document.body.appendChild(frame)

      const doc = frame.contentDocument!
      doc.open()
      doc.write(`<!doctype html><html><head><title>${title}</title><style>
        body { font: 14px/1.7 system-ui, sans-serif; color:#111; max-width:44rem; margin:2rem auto; padding:0 1rem }
        h1 { font-size:1.6rem } h3 { margin-top:1.6rem; font-size:1rem }
        blockquote { border-left:3px solid #ddd; margin:.5rem 0; padding:.2rem 0 .2rem .8rem; color:#555; font-size:.9em }
        code { background:#f4f4f5; padding:.1rem .3rem; border-radius:3px; font-size:.9em }
        hr { border:0; border-top:1px solid #e5e5e5; margin:1.5rem 0 }
      </style></head><body><pre style="white-space:pre-wrap;font:inherit"></pre></body></html>`)
      doc.close()
      doc.querySelector('pre')!.textContent = markdown

      frame.contentWindow!.focus()
      frame.contentWindow!.print()
      // Left in the DOM briefly: removing it while the print dialog is open cancels the job.
      window.setTimeout(() => frame.remove(), 60_000)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Export conversation">
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Download className="size-4" aria-hidden />
            )}
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={downloadMarkdown}>
          <FileDown className="size-4" aria-hidden />
          Download as Markdown
        </DropdownMenuItem>
        <DropdownMenuItem onClick={printToPdf}>
          <Printer className="size-4" aria-hidden />
          Print or save as PDF
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
