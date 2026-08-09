import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import './index.css'
import App from './App.tsx'
import { AuthProvider } from './hooks/useAuth'
import { applyTheme, storedTheme } from './hooks/useTheme'

// Before the first paint, so a returning dark-mode user never sees a white flash.
applyTheme(storedTheme())

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 401 means the session ended; retrying it three times just delays the redirect to login.
      retry: (failureCount, error) =>
        !(error instanceof Error && 'status' in error && error.status === 401) && failureCount < 2,
      staleTime: 30_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
