import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { api, errorMessage, type Preferences } from '../api'
import { Icon } from '../components/Icon'

export function ApplicationPage() {
  const [saved, setSaved] = useState<Preferences | null>(null)
  const [draft, setDraft] = useState<Preferences | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    api<Preferences>('/app-config').then((value) => { if (active) { setSaved(value); setDraft(value) } })
      .catch((failure: unknown) => { if (active) setError(errorMessage(failure)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  function change(update: Partial<Preferences>) {
    setDraft((value) => value && {...value,...update})
    setNotice('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!draft || saving) return
    setError('')
    setNotice('')
    if (!draft.greeting.trim() || draft.opening_questions.some((item) => !item.trim() || Array.from(item.trim()).length > 100)) {
      setError('请填写开场白，开场问题不得为空或超过 100 字。'); return
    }
    if (!Number.isInteger(draft.hot_threshold) || draft.hot_threshold < 1) {
      setError('常问阈值必须是正整数。'); return
    }
    setSaving(true)
    try {
      const value = await api<Preferences>('/app-config','PUT',draft)
      setSaved(value); setDraft(value); setNotice('配置已保存。')
    } catch (failure) { setError(errorMessage(failure)) }
    finally { setSaving(false) }
  }

  return <section className="page-body" aria-label="应用配置内容">
    {loading && <p role="status">正在读取配置…</p>}
    {error && <p className="action-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && !draft && <button type="button" className="button" onClick={() => { setLoading(true); setError(''); setAttempt((n) => n+1) }}>重新读取配置</button>}
    <div className="action-row"><Link className="text-link" to="/sys-model">查看模型配置<Icon name="chevron" /></Link></div>
    {draft && <form className="settings-form" onSubmit={(event) => void save(event)} noValidate>
      <fieldset disabled={saving}>
        <legend>对话开场白</legend>
        <label className="check-label"><input type="checkbox" checked={draft.greeting_enabled} onChange={(event) => change({greeting_enabled:event.target.checked})} />在新对话显示开场白</label>
        <label>开场白<textarea className="field" rows={3} value={draft.greeting} onChange={(event) => change({greeting:event.target.value})} /></label>
        <p>{draft.opening_questions.length} / 10 条开场问题</p>
        {draft.opening_questions.map((item, index) => <div className="action-row" key={index}>
          <input className="field" aria-label={`开场问题 ${index + 1}`} value={item} onChange={(event) => change({opening_questions:draft.opening_questions.map((q,i) => i === index ? event.target.value : q)})} />
          <button type="button" className="button quiet" aria-label={`删除开场问题 ${index + 1}`} onClick={() => change({opening_questions:draft.opening_questions.filter((_,i) => i !== index)})}>删除</button>
        </div>)}
        <button type="button" className="button" disabled={draft.opening_questions.length >= 10} onClick={() => change({opening_questions:[...draft.opening_questions,'']})}>添加开场问题</button>
      </fieldset>
      <fieldset disabled={saving}>
        <legend>常问设置</legend>
        <label className="check-label"><input type="checkbox" checked={draft.hot_enabled} onChange={(event) => change({hot_enabled:event.target.checked})}/>显示常问问题</label>
        <label>常问阈值<input type="number" className="field" min={1} step={1} value={Number.isNaN(draft.hot_threshold) ? '' : draft.hot_threshold}
          onChange={(event) => change({hot_threshold:event.target.valueAsNumber})} /></label>
        <p>提问次数超过阈值时列入常问。</p>
      </fieldset>
      <fieldset disabled={saving}>
        <legend>下一步问题建议</legend>
        <label className="check-label"><input type="checkbox" checked={draft.suggestions_enabled}
          onChange={(event) => change({suggestions_enabled:event.target.checked})} />回答后显示相关问题</label>
      </fieldset>
      <fieldset disabled={saving}>
        <legend>模型设置</legend>
        <label className="check-label"><input type="checkbox" checked={draft.custom_model_enabled}
          onChange={(event) => change({custom_model_enabled:event.target.checked})} />使用已选择的自定义模型</label>
        <p>关闭时使用部署配置的默认模型。</p>
      </fieldset>
      <div className="action-row">
        <button type="submit" className="button primary" disabled={saving}>{saving ? '正在保存…' : '保存应用配置'}</button>
        <button type="button" className="button" disabled={saving} onClick={() => { setDraft(saved); setError(''); setNotice('') }}>取消修改</button>
      </div>
    </form>}
  </section>
}
