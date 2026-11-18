import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('会话切换后的乱序响应仍显示在原会话', async ({page}) => {
  await mockSources(page)
  await page.route('**/api/sessions',(route) => route.fulfill({json:[{id:'a',title:'会话A'},{id:'b',title:'会话B'}]}))
  const history: Record<string, unknown[]> = {a:[],b:[]}
  await page.route('**/api/sessions/*/messages',(route) => {
    const id = new URL(route.request().url()).pathname.split('/')[3]!
    return route.fulfill({json:history[id]})
  })
  let unblock: () => void = () => undefined
  const aGate = new Promise<void>((resolve) => {unblock=resolve})
  await page.route('**/api/sessions/*/queries',async (route) => {
    const id = new URL(route.request().url()).pathname.split('/')[3]!
    if (id === 'a') await aGate
    const {question, request_id, source_ids} = route.request().postDataJSON()
    const turn = {id:`m-${id}`,session_id:id,position:1,request_id,source_ids,active:true,
      question,status:'ok',result:{summary:`回答 ${question}`}}
    history[id] = [turn]
    await route.fulfill({json:turn})
  })
  await page.goto('/ai-qa')
  await page.getByRole('button',{name:/数据源/}).click()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  await page.getByRole('button',{name:'历史会话'}).click()
  await page.getByRole('button',{name:'会话A',exact:true}).click()
  const input = page.getByRole('textbox',{name:'问题'})
  await input.fill('问题 A')
  const aRequested = page.waitForRequest('**/api/sessions/a/queries')
  await input.press('Enter')
  await aRequested
  await page.getByRole('button',{name:'会话B',exact:true}).click()
  await input.fill('问题 B')
  await input.press('Enter')
  await expect(page.getByText('回答 问题 B')).toBeVisible()
  const aResponse = page.waitForResponse('**/api/sessions/a/queries')
  unblock()
  await aResponse
  await expect(page.getByText('回答 问题 A')).toHaveCount(0)
  await page.getByRole('button',{name:'会话A',exact:true}).click()
  await expect(page.getByText('回答 问题 A')).toBeVisible()
  await expect(page.getByText('回答 问题 B')).toHaveCount(0)
})
