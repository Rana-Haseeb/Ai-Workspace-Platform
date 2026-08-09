import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import Home from '@/routes/Home'
import Login from '@/routes/Login'
import Register from '@/routes/Register'

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
            <Home />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
