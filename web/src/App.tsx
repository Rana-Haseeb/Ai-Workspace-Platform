import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { useAuth } from '@/hooks/useAuth'
import Chat from '@/routes/Chat'
import Login from '@/routes/Login'
import Register from '@/routes/Register'
import WorkspaceHome from '@/routes/WorkspaceHome'
import WorkspaceIndex from '@/routes/WorkspaceIndex'
import WorkspaceSettings from '@/routes/WorkspaceSettings'

/**
 * Client-side route guards.
 *
 * These are a user-experience convenience, not a security boundary — anyone can edit client
 * JavaScript. The actual boundary is `get_current_user` and `get_owned_workspace` on the server;
 * a request that skips this guard still gets a 401 or 403.
 */
function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  return user ? children : <Navigate to="/login" replace />
}

function RedirectIfAuthed({ children }: { children: React.ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  return user ? <Navigate to="/" replace /> : children
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background">
      <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <Login />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthed>
            <Register />
          </RedirectIfAuthed>
        }
      />

      <Route
        path="/"
        element={
          <RequireAuth>
            <WorkspaceIndex />
          </RequireAuth>
        }
      />

      <Route
        path="/w/:workspaceId"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<WorkspaceHome />} />
        <Route path="c/:conversationId" element={<Chat />} />
        <Route path="settings" element={<WorkspaceSettings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
