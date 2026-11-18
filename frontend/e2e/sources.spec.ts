import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('来源范围随请求传递，执行摘要可核查', async ({ page }) => {
  await mockSources(page)
  await page.route('**/api/sessions', (route) => route.fulfill({json:{id:'s1'}}))
  await page.route('**/api/sessions/s1/messages', (route) => route.fulfill({json:[]}))
  let requests = 0
  await page.route('**/api/sessions/s1/queries', async (route) => {
    requests++
    expect(route.request().postDataJSON().source_ids).toEqual(['sales'])
    await route.fulfill({json:{id:'m1',session_id:'s1',position:1,request_id:route.request().postDataJSON().request_id,
      source_ids:['sales'],active:true,question:'北京收入',status:'ok',result:{summary:'查询结果',execution:{model:'demo',
        row_count:1,elapsed_ms:10,definition:'确认收入',sources:[{id:'sales',name:'商业市场台账',as_of:'2026-08-31',version:'demo-1'}],
        sql:'SELECT SUM(value) FROM sales',parameters:[],filters:{}}}}})
  })
  await page.goto('/ai-qa')
  await page.getByRole('textbox',{name:'问题'}).fill('北京收入')
  await page.getByRole('button',{name:'发送问题'}).click()
  await expect(page.getByRole('alert')).toContainText('请先选择至少一个数据源')
  expect(requests).toBe(0)
  await page.getByRole('button',{name:'数据源（已选 0）'}).click()
  await page.getByRole('button',{name:'全选可用来源'}).click()
  await expect(page.getByRole('checkbox',{name:/商业市场台账/})).toBeChecked()
  await expect(page.getByRole('checkbox',{name:/商解专项/})).toBeDisabled()
  await page.getByRole('button',{name:'取消全选'}).click()
  await expect(page.getByRole('checkbox',{name:/整体目标台账/})).not.toBeChecked()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  await page.getByRole('button',{name:'发送问题'}).click()
  await page.getByText('分析过程',{exact:true}).click()
  await expect(page.getByText(/SELECT SUM/)).toBeVisible()
  await expect(page.getByText(/商业市场台账 · 截至 2026-08-31/)).toBeVisible()
})
