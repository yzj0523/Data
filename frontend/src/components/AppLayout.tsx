import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'

import { Icon, type IconName } from './Icon'
import { Modal } from './Modal'

const navigation: { group: string; links: { path: string; title: string; icon: IconName }[] }[] = [
  { group: '工作台', links: [{ path: '/ai-qa', title: '智能问数', icon: 'robot' }] },
  { group: '系统管理', links: [
    { path: '/sys-app', title: '应用配置', icon: 'sliders' },
    { path: '/sys-model', title: '模型配置', icon: 'model' },
  ] },
  { group: '反馈管理', links: [{ path: '/sys-feedback-user', title: '回复校对', icon: 'feedback' }] },
]

const descriptions: Record<string, string> = {
  '/ai-qa': '用自然语言探索销售与经营数据。',
  '/sys-app': '管理对话引导与问答偏好。',
  '/sys-model': '设置智能问数使用的模型。',
  '/sys-feedback-user': '查看并核对用户标记的数据问题。',
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(() => window.matchMedia?.('(max-width: 700px)').matches ?? false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const { pathname } = useLocation()
  const currentPath = pathname.replace(/\/+$/, '').toLowerCase()
  const currentGroup = navigation.find((section) => section.links.some((link) => link.path === currentPath))
  const current = currentGroup?.links.find((link) => link.path === currentPath)
  const title = current?.title ?? '页面不存在'

  useEffect(() => { document.title = `${title} · AI问数` }, [title])

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳转到主要内容</a>
      <header className="top-bar">
        <Link to="/ai-qa" className="brand" aria-label="AI问数首页">
          <span className="brand-mark"><Icon name="chart" /></span><span>AI问数</span>
        </Link>
        <span className="brand-caption">销售经营数据</span>
        <button type="button" className="preview-button" aria-label="查看预览说明" onClick={() => setPreviewOpen(true)}>
          <span className="preview-label">界面预览</span><Icon name="info" />
        </button>
      </header>
      <div className="app-body">
        <aside className={`sidebar${collapsed ? ' collapsed' : ''}`} aria-label="主侧栏">
          <nav id="primary-navigation" aria-label="主导航">
            {navigation.map((section) => (
              <div className="nav-group" key={section.group}>
                <p className="nav-group-title">{section.group}</p>
                {section.links.map((link) => (
                  <Link key={link.path} to={link.path} aria-label={link.title} title={link.title}
                    aria-current={currentPath === link.path ? 'page' : undefined}
                    className={`nav-link${currentPath === link.path ? ' active' : ''}`}>
                    <Icon name={link.icon} /><span className="nav-label">{link.title}</span>
                  </Link>
                ))}
              </div>
            ))}
          </nav>
          <div className="sidebar-footer">
            <button type="button" className="sidebar-toggle" aria-controls="primary-navigation"
              aria-expanded={!collapsed} aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
              onClick={() => setCollapsed((value) => !value)}>
              <Icon name="panel" /><span className="nav-label">收起侧边栏</span>
            </button>
          </div>
        </aside>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <header className="page-header">
            <nav className="breadcrumb" aria-label="面包屑">
              <span>{currentGroup?.group ?? '工作台'}</span><Icon name="chevron" /><span>{title}</span>
            </nav>
            <h1>{title}</h1>
            {descriptions[currentPath] && <p>{descriptions[currentPath]}</p>}
          </header>
          <Outlet />
        </main>
      </div>
      <Modal open={previewOpen} title="预览说明" onClose={() => setPreviewOpen(false)}>
        <p>在智能问数中先选择数据源，再输入经营数据问题。</p>
        <p>可在模型配置中检查连接，在回复校对中查看和处理数据反馈。</p>
      </Modal>
    </div>
  )
}
