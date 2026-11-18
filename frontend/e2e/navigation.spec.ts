import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test.beforeEach(async ({ page }) => {
  await mockSources(page)
  await page.route('**/api/models', (route) => route.fulfill({json:{items:[],selected_id:null,default_name:null,custom_enabled:false}}))
  await page.route('**/api/feedbacks?*',(route) => route.fulfill({json:{items:[],page:1,pages:1,total:0}}))
})

test('四个页面导航、浏览器前进后退及未接入状态', async ({ page }) => {
  const pageErrors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('request', (request) => { if (request.method() !== 'GET' && new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()) })
  await page.goto('/')
  await expect(page).toHaveURL(/\/ai-qa$/)
  await expect(page.getByRole('button', { name: '发送问题' })).toBeDisabled()
  for (const [title, path] of [['应用配置', '/sys-app'], ['模型配置', '/sys-model'], ['回复校对', '/sys-feedback-user'], ['智能问数', '/ai-qa']]) {
    await page.getByRole('link', { name: title, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    await expect(page.getByRole('link', { name: title, exact: true })).toHaveAttribute('aria-current', 'page')
  }
  await page.goBack()
  await expect(page.getByRole('heading', { level: 1, name: '回复校对' })).toBeVisible()
  await expect(page.getByRole('searchbox', { name: '搜索问题' })).toBeEnabled()
  await page.goForward()
  await expect(page.getByRole('heading', { level: 1, name: '智能问数' })).toBeVisible()
  expect(pageErrors).toEqual([])
  expect(apiRequests).toEqual([])
})

test('收起侧栏后保留图标导航与键盘展开', async ({ page }) => {
  await page.goto('/ai-qa')
  const sidebar = page.getByRole('complementary', { name: '主侧栏' })
  const expandedWidth = await sidebar.boundingBox()
  await page.getByRole('button', { name: '收起侧边栏' }).click()
  await expect(page.getByRole('button', { name: '展开侧边栏' })).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBeLessThan(expandedWidth!.width)
  await page.getByRole('link', { name: '模型配置', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '模型配置' })).toBeVisible()
  const expand = page.getByRole('button', { name: '展开侧边栏' })
  await expand.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: '收起侧边栏' })).toHaveAttribute('aria-expanded', 'true')
})

test('公共弹窗支持焦点约束、Escape关闭、焦点返回和遮罩关闭', async ({ page }) => {
  await page.goto('/ai-qa')
  const trigger = page.getByRole('button', { name: '查看预览说明' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: '预览说明' })
  await expect(dialog).toBeVisible()
  await page.getByRole('button', { name: '我知道了' }).focus()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '关闭预览说明' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button', { name: '我知道了' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  await trigger.click()
  await page.mouse.click(4, 4)
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
})

test('应用配置中的模型入口可导航，未读取模型时无法操作', async ({ page }) => {
  await page.route('**/api/models', (route) => route.fulfill({status:503,json:{error:{message:'模型服务不可用'}}}))
  await page.goto('/sys-app')
  await page.getByRole('link', { name: '查看模型配置' }).click()
  await expect(page.getByRole('combobox', { name: '选择模型' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存配置' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '新增模型' })).toBeDisabled()
  await expect(page.getByRole('alert')).toHaveText('模型服务不可用')
})

test('直接访问未知地址时可以返回主要页面', async ({ page }) => {
  await page.goto('/not-a-page')
  await expect(page.getByRole('heading', { level: 1, name: '页面不存在' })).toBeVisible()
  await page.getByRole('link', { name: '返回智能问数' }).click()
  await expect(page.getByRole('heading', { level: 1, name: '智能问数' })).toBeVisible()
})

test('窄视口下页面及图标导航仍可使用', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/ai-qa')
  await expect(page.getByRole('button', { name: '展开侧边栏' })).toBeVisible()
  for (const title of ['智能问数', '应用配置', '模型配置', '回复校对']) {
    await page.getByRole('link', { name: title, exact: true }).click()
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})

for (const width of [320, 390]) {
  test(`侧栏回归：${width}px窄屏展开后可立即收起且不挤压内容`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/ai-qa')
    const main = page.getByRole('main')
    const before = await main.boundingBox()
    await page.getByRole('button', { name: '展开侧边栏' }).click()
    await page.evaluate(() => window.scrollTo(0, 0))
    const collapse = page.getByRole('button', { name: '收起侧边栏' })
    await expect(collapse).toBeInViewport({ ratio: 1 })
    await expect.poll(async () => (await main.boundingBox())?.width).toBe(before!.width)
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await expect(collapse).toBeInViewport({ ratio: 1 })
    await collapse.click()
    await expect(page.getByRole('button', { name: '展开侧边栏' })).toBeInViewport({ ratio: 1 })
  })
}

test('侧栏回归：桌面缩到窄屏后收起按钮仍可直接使用', async ({ page }) => {
  await page.goto('/ai-qa')
  await page.setViewportSize({ width: 390, height: 844 })
  const collapse = page.getByRole('button', { name: '收起侧边栏' })
  await expect(collapse).toBeInViewport({ ratio: 1 })
  await expect.poll(async () => (await page.getByRole('main').boundingBox())?.width).toBeGreaterThan(300)
  await collapse.click()
  await expect(page.getByRole('button', { name: '展开侧边栏' })).toBeInViewport({ ratio: 1 })
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.getByRole('button', { name: '展开侧边栏' }).click()
  await expect(page.getByRole('button', { name: '收起侧边栏' })).toBeInViewport({ ratio: 1 })
})

test('路由回归：尾斜杠地址的标题与唯一选中导航一致', async ({ page }) => {
  const paths = [
    ['/ai-qa/', '智能问数'],
    ['/sys-app/', '应用配置'],
    ['/sys-model/', '模型配置'],
    ['/sys-feedback-user/', '回复校对'],
    ['/SYS-MODEL', '模型配置'],
    ['/sys-model///', '模型配置'],
  ]
  for (const [path, title] of paths) {
    await page.goto(path!)
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    const navigation = page.getByRole('navigation', { name: '主导航' })
    await expect(navigation.getByRole('link', { name: title, exact: true })).toHaveAttribute('aria-current', 'page')
    await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1)
  }
  await page.goto('/sys-model/unknown')
  await expect(page.getByRole('heading', { level: 1, name: '页面不存在' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '主导航' }).locator('[aria-current="page"]')).toHaveCount(0)
})

test('弹窗回归：内容与遮罩之间拖动不误关闭，单击遮罩仍可关闭', async ({ page }) => {
  await page.goto('/ai-qa')
  const trigger = page.getByRole('button', { name: '查看预览说明' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: '预览说明' })
  const text = page.getByText('在智能问数中先选择数据源，再输入经营数据问题。')
  const box = await text.boundingBox()
  await page.mouse.move(box!.x + 20, box!.y + 10)
  await page.mouse.down()
  await page.mouse.move(4, 4, { steps: 5 })
  await page.mouse.up()
  await expect(dialog).toBeVisible()
  await page.mouse.down()
  await page.mouse.move(box!.x + 20, box!.y + 10, { steps: 5 })
  await page.mouse.up()
  await expect(dialog).toBeVisible()
  await page.mouse.click(4, 4)
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
})
