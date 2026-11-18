import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('提问连接结构化结果、复制和刷新，空白不会提交', async ({ page, context }) => {
  const question = '<b>北京收入</b>'
  const turn = { id: 'm1', session_id: 's1', position: 1, request_id: 'q1', question,
    source_ids: ['sales'], active: true, status: 'ok', result: { summary: '北京收入 3000 万元。',
      columns: ['经营单元','收入（万元）'], rows: [['北京',3000]], statistics: { row_count: 1, total: 3000, unit: '万元' } } }
  await context.grantPermissions(['clipboard-read','clipboard-write'])
  let asked = false
  await mockSources(page)
  await page.route('**/api/sessions', (route) => route.fulfill({ json: { id: 's1', title: question, pinned: false } }))
  await page.route('**/api/sessions/s1/messages', (route) => route.fulfill({ json: asked ? [turn] : [] }))
  await page.route('**/api/sessions/s1/queries', async (route) => {
    expect(route.request().postDataJSON().question).toBe(question)
    asked = true
    await route.fulfill({ json: turn })
  })
  await page.goto('/ai-qa')
  await page.getByRole('button', {name:/数据源/}).click()
  await page.getByRole('checkbox', {name:/商业市场台账/}).check()
  await page.getByRole('button', {name:'我知道了'}).click()
  await expect(page.getByRole('button', { name: '发送问题' })).toBeDisabled()
  const input = page.getByRole('textbox', { name: '问题' })
  await input.fill(question)
  await input.press('Enter')
  await expect(page.getByRole('cell', { name: '3000' })).toBeVisible()
  await expect(page.getByText(question, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '编辑重发' }).click()
  await page.getByRole('textbox', { name: '编辑问题' }).fill('取消后不会出现')
  await page.getByRole('button', { name: '取消编辑' }).click()
  await expect(page.getByText(question, { exact: true })).toBeVisible()
  await expect(page.getByText('取消后不会出现')).toHaveCount(0)
  await page.getByRole('button', { name: '复制问题' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(question)
  await page.getByRole('button', { name: '复制回复' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('北京\t3000')
  let reportRequest: string | undefined
  await page.route('**/api/feedbacks', (route) => {
    const payload = route.request().postDataJSON()
    expect(payload.turn_id).toBe('m1')
    expect(payload.request_id).toMatch(/^[a-f0-9]{32}$/)
    if (!reportRequest) {
      reportRequest = payload.request_id
      return route.abort('internetdisconnected')
    }
    expect(payload.request_id).toBe(reportRequest)
    return route.fulfill({status:201,json:{id:'f1'}})
  })
  await page.getByRole('button', { name: '数据有误' }).click()
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByRole('alert')).toContainText('无法连接服务')
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByRole('status')).toHaveText('反馈已提交。')
  await page.reload()
  await expect(page.getByRole('cell', { name: '3000' })).toBeVisible()
})
