import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('会话创建、重命名、置顶、取消删除和删除最后一个会话', async ({page}) => {
  await mockSources(page)
  let items: {id:string;title:string;pinned:boolean}[] = []
  await page.route('**/api/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      const item = {id:'s1',title:'新对话',pinned:false}
      items = [item]
      return route.fulfill({json:item})
    }
    return route.fulfill({json:items})
  })
  await page.route('**/api/sessions/s1/messages', (route) => route.fulfill({json:[]}))
  await page.route('**/api/sessions/s1', (route) => {
    if (route.request().method() === 'DELETE') { items = []; return route.fulfill({status:204}) }
    Object.assign(items[0]!,route.request().postDataJSON())
    return route.fulfill({json:items[0]})
  })
  await page.goto('/ai-qa')
  await page.getByRole('button',{name:'历史会话'}).click()
  await page.getByRole('button',{name:'新建对话'}).click()
  await page.getByRole('button',{name:'重命名 新对话'}).click()
  await page.getByRole('textbox',{name:'会话名称'}).fill('北京经营')
  await page.getByRole('button',{name:'保存名称'}).click()
  await page.getByRole('button',{name:'置顶 北京经营',exact:true}).click()
  await expect(page.getByRole('button',{name:'置顶 · 北京经营'})).toBeVisible()
  await page.getByRole('button',{name:'删除 北京经营'}).click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button',{name:'置顶 · 北京经营'})).toBeVisible()
  await page.getByRole('button',{name:'删除 北京经营'}).click()
  await page.getByRole('button',{name:'确认删除'}).click()
  await expect(page.getByText('暂无会话，可以新建对话开始提问。')).toBeVisible()
  await expect(page.getByRole('heading',{name:/你好/})).toBeVisible()
})
