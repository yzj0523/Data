import { expect, test } from '@playwright/test'

test('回复校对可筛选、取消和保存处理', async ({page}) => {
  let writes = 0
  let item = {id:'f1',question:'原问题',reporter:'演示用户',status:'pending',created_at:'2026-08-31T00:00:00Z',notes:'',answer:{summary:'原答案'}}
  await page.route('**/api/feedbacks?*',(route) => {
    const params = new URL(route.request().url()).searchParams
    const list = (!params.get('status') || params.get('status') === item.status) ? [item] : []
    return route.fulfill({json:{items:list,page:1,pages:1,total:list.length}})
  })
  await page.route('**/api/feedbacks/f1',(route) => {
    if (route.request().method() === 'PATCH') {writes++;item = {...item,...route.request().postDataJSON()}}
    return route.fulfill({json:item})
  })
  await page.goto('/sys-feedback-user')
  await page.getByLabel('处理状态').selectOption('pending')
  await page.getByRole('button',{name:'筛选',exact:true}).click()
  await page.getByRole('button',{name:'处理 原问题'}).click()
  await expect(page.getByText('原答案')).toBeVisible()
  await page.getByRole('textbox',{name:'处理备注'}).fill('取消的草稿')
  await page.getByRole('button',{name:'取消处理'}).click()
  expect(writes).toBe(0)
  await page.getByRole('button',{name:'处理 原问题'}).click()
  await expect(page.getByRole('textbox',{name:'处理备注'})).toHaveValue('')
  await page.getByLabel('处理结果').selectOption('resolved')
  await page.getByRole('textbox',{name:'处理备注'}).fill('保留备注')
  await page.getByRole('button',{name:'保存处理'}).click()
  await expect(page.getByText('暂无匹配的反馈')).toBeVisible()
  await page.reload()
  await page.getByRole('button',{name:'处理 原问题'}).click()
  await expect(page.getByRole('textbox',{name:'处理备注'})).toHaveValue('保留备注')
})

test('回复校对响应格式异常时保留列表和备注草稿，可重试恢复', async ({page}) => {
  let badList = true
  let badDetail = true
  let badSave = true
  let item = {id:'f1',question:'待核对问题',reporter:'演示用户',status:'pending',
    created_at:'2026-08-31T00:00:00Z',notes:'',answer:{summary:'原答案'}}
  await page.route('**/api/feedbacks?*',(route) => route.fulfill({
    json:badList ? {unexpected:true} : {items:[item],page:1,pages:1,total:1},
  }))
  await page.route('**/api/feedbacks/f1',(route) => {
    if (route.request().method() === 'PATCH') {
      if (badSave) return route.fulfill({json:{unexpected:true}})
      item = {...item,...route.request().postDataJSON()}
    } else if (badDetail) {
      return route.fulfill({json:{...item,answer:{summary:'原答案',rows:[{}]}}})
    }
    return route.fulfill({json:item})
  })
  await page.goto('/sys-feedback-user')
  const pageError = page.getByRole('alert')
  await expect(pageError).toContainText('格式异常')
  await expect(page.getByRole('link',{name:'智能问数',exact:true})).toBeVisible()
  badList = false
  await page.getByRole('button',{name:'重新加载'}).click()
  const review = page.getByRole('button',{name:'处理 待核对问题'})
  await expect(review).toBeVisible()

  badList = true
  await page.getByRole('button',{name:'筛选',exact:true}).click()
  await expect(pageError).toContainText('格式异常')
  await expect(review).toBeVisible()
  badList = false
  await page.getByRole('button',{name:'重新加载'}).click()
  await review.click()
  await expect(pageError).toContainText('格式异常')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  badDetail = false
  await review.click()
  const dialog = page.getByRole('dialog',{name:'处理反馈'})
  await expect(dialog.getByText('原答案')).toBeVisible()
  await dialog.getByLabel('处理结果').selectOption('resolved')
  const notes = dialog.getByRole('textbox',{name:'处理备注'})
  await notes.fill('保留这份草稿')
  await dialog.getByRole('button',{name:'保存处理'}).click()
  await expect(dialog.getByRole('alert')).toContainText('格式异常')
  await expect(notes).toHaveValue('保留这份草稿')
  badSave = false
  await dialog.getByRole('button',{name:'保存处理'}).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('cell',{name:'已处理'})).toBeVisible()
})
