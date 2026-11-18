import { expect, test } from '@playwright/test'

test('模型测试失败和修改字段会禁用添加，选择可保存且密钥不进入浏览器存储', async ({page}) => {
  const secret = 'browser-test-key'
  const item = {id:'custom',name:'模型B',base_url:'https://example.test/v1'}
  const state = {items:[] as (typeof item)[],selected_id:null as string | null,default_name:'默认模型',custom_enabled:false}
  await page.route('**/api/models', (route) => {
    if (route.request().method() === 'POST') { state.items = [item]; return route.fulfill({json:item}) }
    return route.fulfill({json:state})
  })
  await page.route('**/api/models/test', (route) => {
    const valid = route.request().postDataJSON().api_key === secret
    return route.fulfill(valid ? {json:{status:'connected'}} : {status:502,json:{error:{message:'模型服务拒绝了凭证。'}}})
  })
  await page.route('**/api/models/selection', (route) => {
    state.selected_id = route.request().postDataJSON().model_id
    return route.fulfill({json:{selected_id:state.selected_id}})
  })
  await page.goto('/sys-model')
  await page.getByRole('button',{name:'新增模型'}).click()
  await page.getByLabel('Base URL').fill(item.base_url)
  await page.getByLabel('Model Name').fill('模型A')
  await page.getByLabel('API Key').fill('bad')
  await page.getByRole('button',{name:'测试连接'}).click()
  await expect(page.getByRole('alert')).toContainText('拒绝了凭证')
  await expect(page.getByRole('button',{name:'添加模型'})).toBeDisabled()
  await page.getByLabel('API Key').fill(secret)
  await page.getByRole('button',{name:'测试连接'}).click()
  await expect(page.getByRole('button',{name:'添加模型'})).toBeEnabled()
  await page.getByLabel('Model Name').fill(item.name)
  await expect(page.getByRole('button',{name:'添加模型'})).toBeDisabled()
  await page.getByRole('button',{name:'测试连接'}).click()
  await page.getByRole('button',{name:'添加模型'}).click()
  await page.getByRole('button',{name:'保存配置'}).click()
  await expect(page.getByRole('status')).toHaveText('模型选择已保存。')
  await page.reload()
  await expect(page.getByLabel('选择模型')).toHaveValue(item.id)
  expect(await page.evaluate(() => JSON.stringify([localStorage,sessionStorage]))).not.toContain(secret)
})
