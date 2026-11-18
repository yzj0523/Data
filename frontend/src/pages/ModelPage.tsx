import { useEffect, useState } from 'react'

import { ApiError, api, errorMessage } from '../api'
import { Icon } from '../components/Icon'

type ModelList = { items: {id:string;name:string;base_url:string}[]; selected_id: string | null; default_name: string | null; custom_enabled: boolean }
const blank = {name:'',base_url:'',api_key:''}

export function ModelPage() {
  const [models, setModels] = useState<ModelList | null>(null)
  const [active, setActive] = useState('')
  const [draft, setDraft] = useState(blank)
  const [showForm, setShowForm] = useState(false)
  const [verified, setVerified] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    api<ModelList>('/models').then((value) => { if (current) { setModels(value); setActive(value.selected_id ?? '') } })
      .catch((failure: unknown) => { if (current) setError(errorMessage(failure)) })
    return () => { current = false }
  }, [attempt])

  function change(field: keyof typeof blank, value: string) {
    setDraft((current) => ({...current,[field]:value})); setVerified(false); setNotice(''); setError('')
  }

  async function operate(action: 'test' | 'add' | 'select') {
    if (busy) return
    if (action === 'add' && !verified) return
    setBusy(true); setError(''); setNotice('')
    try {
      if (action === 'test') {
        setVerified(false)
        const response = await api<{status:string}>('/models/test','POST',draft)
        if (response.status !== 'connected') throw new ApiError('模型服务未确认连接。','model_response')
        setVerified(true); setNotice('连接测试通过。')
      } else if (action === 'add') {
        const item = await api<ModelList['items'][number]>('/models','POST',draft)
        setModels((value) => value && {...value,items:[...value.items,item]})
        setActive(item.id); setDraft(blank); setVerified(false); setShowForm(false); setNotice('已添加模型，可保存为当前选择。')
      } else {
        await api('/models/selection','PUT',{model_id:active})
        setModels((value) => value && {...value,selected_id:active})
        setNotice('模型选择已保存。')
      }
    } catch (failure) { setError(errorMessage(failure)) }
    finally { setBusy(false) }
  }

  return <section className="page-body" aria-label="模型配置内容">
    {error && <p role="alert" className="action-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!models && error && <button type="button" className="button" onClick={() => {setError('');setAttempt((n) => n+1)}}>重试读取模型</button>}
    <section className="panel model-panel" aria-labelledby="model-panel-title">
      <div className="panel-heading"><span className="setting-icon"><Icon name="model" /></span>
        <div><h2 id="model-panel-title">智能问数模型</h2>
          {models && <p>{models.custom_enabled ? '正在使用自定义模型设置。' : `部署默认模型：${models.default_name ?? '尚未配置'}`}</p>}</div>
      </div>
      <div className="model-form">
        <label htmlFor="model-selection">选择模型</label>
        <select id="model-selection" value={active} disabled={!models?.items.length || busy} onChange={(event) => {setActive(event.target.value);setNotice('')}}>
          <option value="">{models ? '请选择已添加的模型' : '模型列表未加载'}</option>
          {models?.items.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.base_url}</option>)}
        </select>
        <p className="field-help">{models?.selected_id ? '已保存的选择可在启用自定义模型后使用。' : '尚未保存自定义模型选择。'}</p>
      </div>
      <footer className="panel-footer">
        <button type="button" className="button" disabled={!models || busy || showForm} onClick={() => {setNotice('');setShowForm(true)}}>新增模型</button>
        <button type="button" className="button primary" disabled={!active || busy || active === models?.selected_id} onClick={() => void operate('select')}>保存配置</button>
      </footer>
    </section>
    {showForm && <form className="settings-form" onSubmit={(event) => {event.preventDefault();void operate('add')}}>
      <fieldset disabled={busy}>
        <legend>新增兼容模型</legend>
        <label>Base URL<input className="field" type="url" value={draft.base_url} required onChange={(event) => change('base_url',event.target.value)} /></label>
        <label>Model Name<input className="field" value={draft.name} required maxLength={160} onChange={(event) => change('name',event.target.value)} /></label>
        <label>API Key<input className="field" type="password" autoComplete="off" value={draft.api_key} required onChange={(event) => change('api_key',event.target.value)} /></label>
        <div className="action-row">
          <button type="button" className="button" disabled={!draft.name.trim() || !draft.base_url.trim() || !draft.api_key} onClick={() => void operate('test')}>测试连接</button>
          <button type="submit" className="button primary" disabled={!verified}>添加模型</button>
          <button type="button" className="button" onClick={() => {setDraft(blank);setVerified(false);setShowForm(false);setNotice('')}}>取消添加</button>
        </div>
      </fieldset>
    </form>}
  </section>
}
