import { useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { documents, type Citation, type WorkspaceDetail } from '@/lib/api'

const ACCEPTED = '.pdf,.docx,.txt,.md,.markdown'

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function StatusBadge({ status, error }: { status: string; error: string | null }) {
  if (status === 'ready' && !error) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <CheckCircle2 className="size-3.5 text-primary" aria-hidden />
        Ready
      </span>
    )
  }
  if (status === 'ready' && error) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title={error}>
        <AlertCircle className="size-3.5" aria-hidden />
        Keyword only
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive" title={error ?? ''}>
        <AlertCircle className="size-3.5" aria-hidden />
        Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" aria-hidden />
      Processing
    </span>
  )
}

export default function Documents() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)

  const [dragging, setDragging] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Citation[] | null>(null)
  const [searchMeta, setSearchMeta] = useState<{ mode: string; ms: number } | null>(null)

  const list = useQuery({
    queryKey: ['documents', workspace.id],
    queryFn: () => documents.list(workspace.id),
    // Ingestion runs in the background, so poll while anything is still processing.
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.status === 'pending' || d.status === 'processing')
        ? 1500
        : false,
  })

  const status = useQuery({
    queryKey: ['kb-status', workspace.id],
    queryFn: () => documents.status(workspace.id),
    refetchInterval: list.data?.some((d) => d.status !== 'ready' && d.status !== 'failed')
      ? 1500
      : false,
  })

  const upload = useMutation({
    mutationFn: (file: File) => documents.upload(workspace.id, file),
    onSuccess: () => {
      setUploadError(null)
      queryClient.invalidateQueries({ queryKey: ['documents', workspace.id] })
      queryClient.invalidateQueries({ queryKey: ['kb-status', workspace.id] })
    },
    onError: (error) =>
      setUploadError(error instanceof Error ? error.message : 'The upload failed.'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => documents.remove(workspace.id, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', workspace.id] })
      queryClient.invalidateQueries({ queryKey: ['kb-status', workspace.id] })
      setResults(null)
    },
  })

  const search = useMutation({
    mutationFn: () => documents.search(workspace.id, query.trim()),
    onSuccess: (found) => {
      setResults(found.citations)
      setSearchMeta({ mode: found.mode, ms: found.took_ms })
    },
  })

  function handleFiles(files: FileList | null) {
    if (!files) return
    for (const file of Array.from(files)) upload.mutate(file)
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Documents</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {workspace.settings.assistant_name} searches these and cites the page it used.
      </p>

      {/* ------------------------------------------------------------- uploader */}
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          handleFiles(event.dataTransfer.files)
        }}
        className={[
          'mt-6 rounded-xl border border-dashed p-8 text-center transition-colors',
          dragging ? 'border-primary bg-primary/5' : 'border-border',
        ].join(' ')}
      >
        <Upload className="mx-auto size-6 text-muted-foreground" aria-hidden />
        <p className="mt-3 text-sm font-medium">Drop files here</p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, Word, text or Markdown. Up to 20 MB each.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
        >
          {upload.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
          Choose files
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          className="hidden"
          onChange={(event) => {
            handleFiles(event.target.files)
            // Reset so choosing the same file twice fires a change event both times.
            event.target.value = ''
          }}
        />
      </div>

      {uploadError && (
        <p role="alert" className="mt-3 flex items-start gap-2 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {uploadError}
        </p>
      )}

      {/* --------------------------------------------------------- kb status */}
      {status.data && status.data.documents > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg bg-muted/40 px-4 py-3">
          <div>
            <p className="text-[11px] text-muted-foreground">Chunks</p>
            <p className="tabular text-sm font-medium">
              {status.data.chunks.toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-muted-foreground">Embedded</p>
            <p className="tabular text-sm font-medium">
              {status.data.embedded_chunks.toLocaleString()}
            </p>
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">Search</p>
            <p className="truncate text-sm font-medium">
              {/* Said out loud rather than degrading silently, so a keyword-only result is
                  explained instead of just being worse. */}
              {status.data.semantic_search_available ? 'Keyword + semantic' : 'Keyword only'}
            </p>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- search */}
      {status.data && status.data.chunks > 0 && (
        <form
          className="mt-6 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (query.trim()) search.mutate()
          }}
        >
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your documents"
              aria-label="Search documents"
              className="pl-9"
            />
          </div>
          <Button type="submit" disabled={!query.trim() || search.isPending}>
            {search.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Search
          </Button>
        </form>
      )}

      {results && (
        <div className="mt-4 space-y-2">
          <p className="text-xs text-muted-foreground">
            {results.length} result{results.length === 1 ? '' : 's'}
            {searchMeta && ` · ${searchMeta.mode} · ${searchMeta.ms}ms`}
          </p>
          {results.map((citation) => (
            <Card key={citation.chunk_id}>
              <CardContent className="py-3">
                <p className="flex items-center gap-1.5 text-xs font-medium">
                  <FileText className="size-3.5 text-muted-foreground" aria-hidden />
                  {citation.filename}
                  {citation.page && (
                    <span className="text-muted-foreground">· page {citation.page}</span>
                  )}
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  {citation.snippet}
                </p>
              </CardContent>
            </Card>
          ))}
          {results.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nothing matched that.
            </p>
          )}
        </div>
      )}

      {/* -------------------------------------------------------------- list */}
      <div className="mt-8 space-y-2">
        {list.data?.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No documents yet</CardTitle>
              <CardDescription>
                Upload one and the assistant will answer from it, citing the page.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {list.data?.map((document) => (
          <div
            key={document.id}
            className="flex items-center gap-3 rounded-lg border border-border px-4 py-3"
          >
            <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{document.filename}</p>
              <p className="tabular text-xs text-muted-foreground">
                {humanSize(document.size_bytes)}
                {document.page_count > 0 && ` · ${document.page_count} pages`}
                {document.chunk_count > 0 && ` · ${document.chunk_count} chunks`}
              </p>
            </div>
            <StatusBadge status={document.status} error={document.error} />
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`Delete "${document.filename}"?`)) remove.mutate(document.id)
              }}
              aria-label={`Delete ${document.filename}`}
              className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:text-destructive"
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
