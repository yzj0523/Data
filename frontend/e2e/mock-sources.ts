import { type Page } from '@playwright/test'

export async function mockSources(page: Page) {
  await page.route('**/api/app-config', (route) => route.fulfill({json:{greeting_enabled:false,opening_questions:[],suggestions_enabled:false}}))
  await page.route('**/api/favorites', (route) => route.fulfill({json:[]}))
  await page.route('**/api/sources', (route) => route.fulfill({ json:[
    {id:'sales',name:'商业市场台账',group:'台账',available:true,as_of:'2026-08-31'},
    {id:'targets',name:'整体目标台账',group:'台账',available:true,as_of:'2026-08-31'},
    {id:'solution',name:'商解专项',group:'报表',available:false},
  ] }))
}
