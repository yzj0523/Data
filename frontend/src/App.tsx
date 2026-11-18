import { Link, Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { ApplicationPage } from './pages/ApplicationPage'
import { FeedbackPage } from './pages/FeedbackPage'
import { ModelPage } from './pages/ModelPage'
import { QuestionPage } from './pages/QuestionPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/ai-qa" replace />} />
        <Route path="/ai-qa" element={<QuestionPage />} />
        <Route path="/sys-app" element={<ApplicationPage />} />
        <Route path="/sys-model" element={<ModelPage />} />
        <Route path="/sys-feedback-user" element={<FeedbackPage />} />
        <Route path="*" element={<section className="page-body not-found"><p>这个地址暂时没有可访问的页面。</p><Link className="button primary" to="/ai-qa">返回智能问数</Link></section>} />
      </Route>
    </Routes>
  )
}
