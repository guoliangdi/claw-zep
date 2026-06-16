import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/Login'
import { ProjectsPage } from './pages/Projects'
import { GraphPage } from './pages/Graph'
import { MemoryTreePage } from './pages/MemoryTree'
import { TemporalPage } from './pages/Temporal'
import { PalantirPage } from './pages/Palantir'
import { PlaygroundPage } from './pages/Playground'
import { UsersPage } from './pages/Users'
import { WebhooksPage } from './pages/Webhooks'
import { AuditPage } from './pages/Audit'
import { TenantsPage } from './pages/Tenants'
import { ProfilePage } from './pages/Profile'

export const App: React.FC = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/projects" replace />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="memory-tree" element={<MemoryTreePage />} />
        <Route path="temporal" element={<TemporalPage />} />
        <Route path="palantir" element={<PalantirPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="webhooks" element={<WebhooksPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="tenants" element={<TenantsPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </BrowserRouter>
)
