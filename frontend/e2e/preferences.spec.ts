import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('应用配置可取消、校验并保存，欢迎区使用已保存配置', async ({page}) => {
  await mockSources(page)
  let config = {greeting_enabled:true,greeting:'原开场白',opening_questions:['开场收入'],hot_threshold:3,hot_enabled:true,
    suggestions_enabled:true,custom_model_enabled:false}
  let writes = 0
  await page.route('**/api/app-config',(route) => {
    if (route.request().method() === 'PUT') { config = route.request().postDataJSON(); writes++ }
    return route.fulfill({json:config})
  })
  await page.goto('/sys-app')
  const greeting = page.getByRole('textbox',{name:'开场白',exact:true})
  await greeting.fill('取消草稿')
  await page.getByRole('button',{name:'取消修改'}).click()
  await expect(greeting).toHaveValue('原开场白')
  await greeting.fill(' ')
  await page.getByRole('button',{name:'保存应用配置'}).click()
  await expect(page.getByRole('alert')).toContainText('请填写开场白')
  expect(writes).toBe(0)
  await greeting.fill('新的开场白')
  for (let i=1;i<10;i++) await page.getByRole('button',{name:'添加开场问题'}).click()
  await expect(page.getByRole('button',{name:'添加开场问题'})).toBeDisabled()
  for (let i=10;i>1;i--) await page.getByRole('button',{name:`删除开场问题 ${i}`,exact:true}).click()
  await page.getByRole('spinbutton',{name:'常问阈值'}).fill('5')
  await page.getByRole('button',{name:'保存应用配置'}).click()
  await expect(page.getByRole('status')).toContainText('配置已保存')
  await page.reload()
  await expect(greeting).toHaveValue('新的开场白')
  expect(config.hot_threshold).toBe(5)
  await page.getByRole('link',{name:'智能问数',exact:true}).click()
  await expect(page.getByText('新的开场白',{exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'开场收入'})).toBeVisible()
})

test('下一步建议走同一会话，关闭后隐藏建议', async ({page}) => {
  await mockSources(page)
  const config = {greeting_enabled:false,greeting:'开场白',opening_questions:[],hot_threshold:3,hot_enabled:true,
    suggestions_enabled:true,custom_model_enabled:false}
  await page.route('**/api/app-config',(route) => {
    if (route.request().method() === 'PUT') Object.assign(config,route.request().postDataJSON())
    return route.fulfill({json:config})
  })
  await page.route('**/api/sessions',(route) => route.fulfill({json:{id:'suggest'}}))
  const turns: unknown[] = []
  await page.route('**/api/sessions/suggest/messages',(route) => route.fulfill({json:turns}))
  await page.route('**/api/sessions/suggest/queries',(route) => {
    const input = route.request().postDataJSON()
    const position = turns.length + 1
    const turn = {id:`turn${position}`,session_id:'suggest',position,request_id:input.request_id,source_ids:input.source_ids,
      active:true,question:input.question,status:'ok',
      result:{summary:`结果 ${input.question}`,suggestions:position === 1 ? ['按月查看','按产品线查看','查看同期'] : []}}
    turns.push(turn)
    return route.fulfill({json:turn})
  })
  await page.goto('/ai-qa')
  await page.getByRole('button',{name:/数据源/}).click()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  await page.getByRole('textbox',{name:'问题'}).fill('确认收入')
  await page.getByRole('button',{name:'发送问题'}).click()
  await page.getByRole('button',{name:'按月查看'}).click()
  await expect(page.getByText('结果 按月查看')).toBeVisible()
  await page.getByRole('link',{name:'应用配置',exact:true}).click()
  await page.getByRole('checkbox',{name:'回答后显示相关问题'}).uncheck()
  await page.getByRole('button',{name:'保存应用配置'}).click()
  await expect(page.getByRole('status')).toContainText('已保存')
  await page.getByRole('link',{name:'智能问数',exact:true}).click()
  await expect(page.getByText('结果 按月查看')).toBeVisible()
  await expect(page.getByRole('button',{name:'按月查看'})).toHaveCount(0)
})
