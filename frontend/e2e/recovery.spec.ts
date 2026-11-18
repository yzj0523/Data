import { expect, test } from '@playwright/test'
import { mockSources } from './mock-sources'

test('断线重试保留问题和请求标识，复制失败给出真实提示', async ({page}) => {
  await mockSources(page)
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {value:{writeText:() => Promise.reject(new Error('denied'))}})
  })
  await page.route('**/api/sessions',(route) => route.fulfill({json:{id:'s1'}}))
  await page.route('**/api/sessions/s1/messages',(route) => route.fulfill({json:[]}))
  let id: string | undefined
  await page.route('**/api/sessions/s1/queries',(route) => {
    const payload = route.request().postDataJSON()
    if (!id) {id = payload.request_id;return route.abort('internetdisconnected')}
    expect(payload.request_id).toBe(id)
    return route.fulfill({json:{id:'m1',session_id:'s1',position:1,request_id:payload.request_id,source_ids:payload.source_ids,
      active:true,question:payload.question,status:'ok',result:{summary:'已读取业务数据'}}})
  })
  await page.goto('/ai-qa')
  await page.getByRole('button',{name:/数据源/}).click()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  const field = page.getByRole('textbox',{name:'问题'})
  await field.fill('北京确认收入')
  await field.press('Enter')
  await expect(page.getByRole('alert')).toContainText('无法连接服务')
  await expect(field).toHaveValue('北京确认收入')
  await field.press('Enter')
  await expect(page.getByText('已读取业务数据')).toBeVisible()
  await page.getByRole('button',{name:'复制回复'}).click()
  await expect(page.getByRole('status')).toContainText('无法复制')
})

test('畸形的会话记录或查询响应可重试，失败编辑保留原对话', async ({page}) => {
  await mockSources(page)
  await page.addInitScript(() => sessionStorage.setItem('ai-query-session','s1'))
  const oldTurns = ['原问题','后续问题'].map((question, index) => ({
    id:`old-${index}`,session_id:'s1',position:index+1,request_id:`request-${index}`,source_ids:['sales'],
    question,status:'ok',active:true,result:{summary:`回答 ${question}`},
  }))
  let historyRecovered = false
  await page.route('**/api/sessions/s1/messages', (route) => route.fulfill({
    json: historyRecovered ? oldTurns : {unexpected:true},
  }))
  let editRequest: string | undefined
  await page.route('**/api/sessions/s1/queries', (route) => {
    const payload = route.request().postDataJSON()
    expect(payload.operation).toBe('edit')
    expect(payload.origin_id).toBe(oldTurns[0]!.id)
    const attempt = {...oldTurns[0],id:'edit-attempt',request_id:payload.request_id,question:payload.question}
    if (!editRequest) {
      editRequest = payload.request_id
      return route.fulfill({json:{...attempt,result:{summary:'格式错误',rows:[{}]}}})
    }
    expect(payload.request_id).toBe(editRequest)
    return route.fulfill({json:{...attempt,active:false,status:'failed',result:{summary:'模型响应超时，请重试。'}}})
  })
  await page.goto('/ai-qa')
  await expect(page.getByRole('alert')).toContainText('无法刷新会话记录')
  historyRecovered = true
  await page.getByRole('button',{name:'重试加载会话'}).click()
  await expect(page.getByText('回答 原问题',{exact:true})).toBeVisible()
  await page.getByRole('button',{name:/数据源/}).click()
  await page.getByRole('checkbox',{name:/商业市场台账/}).check()
  await page.getByRole('button',{name:'我知道了'}).click()
  await page.getByRole('article').filter({hasText:'回答 原问题'}).getByRole('button',{name:'编辑重发'}).click()
  const editor = page.getByRole('textbox',{name:'编辑问题'})
  await editor.fill('修改后的问题')
  await page.getByRole('button',{name:'发送修改'}).click()
  await expect(page.getByRole('alert')).toContainText('服务返回的内容格式异常')
  await expect(editor).toHaveValue('修改后的问题')
  await page.getByRole('button',{name:'发送修改'}).click()
  await expect(page.getByRole('alert')).toContainText('编辑未生效。模型响应超时')
  await expect(page.getByText('回答 原问题',{exact:true})).toBeVisible()
  await expect(page.getByText('回答 后续问题',{exact:true})).toBeVisible()
  await page.reload()
  await expect(page.getByText('回答 原问题',{exact:true})).toBeVisible()
  await expect(page.getByText('回答 后续问题',{exact:true})).toBeVisible()
})
