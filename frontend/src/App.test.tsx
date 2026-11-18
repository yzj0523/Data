import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { App } from './App'

function renderAt(path = '/') {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
}

describe('页面骨架', () => {
  it('默认进入智能问数，空白问题无法提交', () => {
    renderAt()
    expect(screen.getByRole('heading', { level: 1, name: '智能问数' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '问题' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled()
    expect(screen.getByRole('link', { name: '智能问数' })).toHaveAttribute('aria-current', 'page')
  })

  it('按可见名称访问全部四个页面', async () => {
    const user = userEvent.setup()
    renderAt()
    for (const title of ['应用配置', '模型配置', '回复校对', '智能问数']) {
      await user.click(screen.getByRole('link', { name: title }))
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: title })).toHaveAttribute('aria-current', 'page')
      expect(document.title).toBe(`${title} · AI问数`)
    }
  })

  it('应用配置入口可进入模型页，业务保存不可用', async () => {
    const user = userEvent.setup()
    renderAt('/sys-app')
    await user.click(screen.getByRole('link', { name: '查看模型配置' }))
    expect(screen.getByRole('heading', { level: 1, name: '模型配置' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '选择模型' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '新增模型' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '保存配置' })).toBeDisabled()
    expect(screen.getByText('尚未保存自定义模型选择。')).toBeInTheDocument()
  })

  it.each(['/sys-model/', '/SYS-MODEL', '/sys-model///'])('路由变体 %s 的标题、内容与选中导航一致', (path) => {
    renderAt(path)
    expect(screen.getByRole('heading', { level: 1, name: '模型配置' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '选择模型' })).toBeDisabled()
    expect(screen.getByRole('link', { name: '模型配置' })).toHaveAttribute('aria-current', 'page')
  })

  it('回复校对保留问题、用户和状态查询入口', () => {
    renderAt('/sys-feedback-user')
    expect(screen.getByRole('searchbox', { name: '搜索问题' })).toBeEnabled()
    expect(screen.getByRole('searchbox', { name: '搜索用户' })).toBeEnabled()
    expect(screen.getByRole('combobox', { name: '处理状态' })).toBeEnabled()
  })

  it('侧栏收起后仍可通过有名称的链接导航并重新展开', async () => {
    const user = userEvent.setup()
    renderAt()
    await user.click(screen.getByRole('button', { name: '收起侧边栏' }))
    expect(screen.getByRole('button', { name: '展开侧边栏' })).toHaveAttribute('aria-expanded', 'false')
    await user.click(screen.getByRole('link', { name: '回复校对' }))
    expect(screen.getByRole('heading', { level: 1, name: '回复校对' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '展开侧边栏' }))
    expect(screen.getByRole('button', { name: '收起侧边栏' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('公共说明弹窗可以打开、关闭并再次打开', async () => {
    const user = userEvent.setup()
    renderAt()
    const trigger = screen.getByRole('button', { name: '查看预览说明' })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: '预览说明' })
    expect(within(dialog).getByText('在智能问数中先选择数据源，再输入经营数据问题。')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: '我知道了' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: '关闭预览说明' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it.each(['/not-a-page', '/sys-model/unknown'])('未知地址 %s 有明确页面和返回入口', async (path) => {
    const user = userEvent.setup()
    renderAt(path)
    expect(screen.getByRole('heading', { level: 1, name: '页面不存在' })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: '主导航' })
    for (const link of within(navigation).getAllByRole('link')) {
      expect(link).not.toHaveAttribute('aria-current')
    }
    await user.click(screen.getByRole('link', { name: '返回智能问数' }))
    expect(screen.getByRole('heading', { level: 1, name: '智能问数' })).toBeInTheDocument()
  })

  it('导航不包含登录、用户管理或遗留报表', () => {
    renderAt()
    const navigation = screen.getByRole('navigation', { name: '主导航' })
    expect(within(navigation).getAllByRole('link')).toHaveLength(4)
    expect(within(navigation).queryByRole('link', { name: /登录|用户管理|驾驶舱|台账|报表/ })).not.toBeInTheDocument()
  })
})
