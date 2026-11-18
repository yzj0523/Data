import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('四类图表共用表格数据，空结果显示原因', async ({ page }) => {
  const label = '用于确认窄屏长标签显示的北京经营单元'
  await mockSources(page)
  const types = [['bar','柱状图'], ['horizontal','条形图'], ['line','折线图'], ['pie','饼图']] as const
  const history = types.map(([type], position) => ({ id:`m${position}`, session_id:'chart', question:type,
    position:position+1, request_id:`q${position}`, source_ids:['sales'], active:true,
    status:'ok', result:{ summary:'确认收入为 10 万元', columns:['经营单元','收入（万元）'], rows:[[label,10]],
      chart:{ type,dimension:'经营单元',metric:'收入（万元）',unit:'万元',points:[{label,value:10}] } } }))
  await page.addInitScript(() => sessionStorage.setItem('ai-query-session','chart'))
  await page.route('**/api/sessions/chart/messages', (route) => route.fulfill({ json:[...history,
    {id:'empty',session_id:'chart',position:5,request_id:'q-empty',source_ids:['sales'],active:true,
      question:'空结果',status:'empty',result:{summary:'没有符合范围的记录。',chart_reason:'没有适合绘图的数值。'}}] }))
  await page.goto('/ai-qa')
  for (const [,name] of types) await expect(page.getByRole('img',{name:new RegExp(name)})).toHaveCount(1)
  await expect(page.getByRole('cell',{name:label})).toHaveCount(4)
  await expect(page.getByText('没有适合绘图的数值。')).toBeVisible()
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByRole('img',{name:/折线图/})).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
})
