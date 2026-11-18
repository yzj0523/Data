import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('常问与收藏复用普通提交，收藏可移除', async ({ page }) => {
  await mockSources(page)
  await page.route('**/api/questions/hot',(route) => route.fulfill({json:[{question:'常问收入',count:4}]}))
  let favorites = ['已收藏收入']
  await page.route('**/api/favorites',(route) => {
    if (route.request().method() === 'PUT') favorites = []
    return route.fulfill({json:favorites})
  })
  await page.route('**/api/sessions',(route) => route.fulfill({json:{id:'shortcut'}}))
  await page.route('**/api/sessions/shortcut/messages',(route) => route.fulfill({json:[]}))
  let count = 0
  await page.route('**/api/sessions/shortcut/queries',(route) => {
    const data = route.request().postDataJSON()
    expect(data.source_ids).toEqual(['sales'])
    count += 1
    return route.fulfill({json:{id:`m${count}`,session_id:'shortcut',position:count,request_id:data.request_id,
      source_ids:data.source_ids,active:true,question:data.question,status:'ok',result:{summary:`回答 ${data.question}`}}})
  })
  await page.goto('/ai-qa')
  await page.getByRole('button',{name:/数据源/}).click()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  await page.getByRole('button',{name:'快捷提问'}).click()
  await page.getByRole('button',{name:'常问收入'}).click()
  await expect(page.getByText('回答 常问收入')).toBeVisible()
  await page.getByRole('button',{name:'已收藏收入',exact:true}).click()
  await expect(page.getByText('回答 已收藏收入')).toBeVisible()
  await page.getByRole('button',{name:'移除收藏 已收藏收入'}).click()
  await expect(page.getByText('暂无收藏。可从会话中的问题添加。')).toBeVisible()
})
