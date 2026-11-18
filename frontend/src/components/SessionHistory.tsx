import { useState, type FormEvent } from 'react'

import type { Session } from '../api'
import { errorMessage } from '../api'
import { Modal } from './Modal'

export function SessionHistory({ sessions, active, onChoose, onNew, onChange, onDelete }: {
  sessions: Session[]; active: string | null; onChoose: (id: string) => void; onNew: () => void;
  onChange: (id: string, changes: Partial<Pick<Session, 'title' | 'pinned'>>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [rename, setRename] = useState<Session | null>(null)
  const [title, setTitle] = useState('')
  const [remove, setRemove] = useState<Session | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function commit(event: FormEvent) {
    event.preventDefault()
    if (!rename || !title.trim() || saving) return
    setSaving(true)
    setError('')
    try { await onChange(rename.id, { title: title.trim() }); setRename(null) }
    catch (failure) { setError(errorMessage(failure)) }
    finally { setSaving(false) }
  }

  async function confirmDelete() {
    if (!remove || saving) return
    setSaving(true)
    setError('')
    try { await onDelete(remove.id); setRemove(null) }
    catch (failure) { setError(errorMessage(failure)) }
    finally { setSaving(false) }
  }

  return <aside className="session-history" aria-label="会话历史">
    <div className="action-row"><strong>近 30 天记录</strong><button type="button" className="button" onClick={onNew}>新建对话</button></div>
    {!sessions.length && <p>暂无会话，可以新建对话开始提问。</p>}
    {!rename && !remove && error && <p role="alert" className="action-error">{error}</p>}
    <ul>{sessions.map((item) => <li key={item.id}>
      <button type="button" className="button session-title" aria-current={active === item.id ? 'true' : undefined} onClick={() => onChoose(item.id)}>{item.pinned ? '置顶 · ' : ''}{item.title}</button>
      <div className="action-row">
        <button type="button" className="button quiet" aria-label={`${item.pinned ? '取消置顶' : '置顶'} ${item.title}`} onClick={() => {
          setError('');void onChange(item.id,{pinned:!item.pinned}).catch((failure:unknown) => setError(errorMessage(failure)))
        }}>{item.pinned ? '取消置顶' : '置顶'}</button>
        <button type="button" className="button quiet" aria-label={`重命名 ${item.title}`} onClick={() => { setError('');setRename(item);setTitle(item.title) }}>重命名</button>
        <button type="button" className="button quiet" aria-label={`删除 ${item.title}`} onClick={() => {setError('');setRemove(item)}}>删除</button>
      </div>
    </li>)}</ul>
    <Modal open={!!rename} title="重命名会话" onClose={() => { if (!saving) setRename(null) }}>
      {error && <p role="alert" className="action-error">{error}</p>}
      <form className="action-row" onSubmit={(event) => void commit(event)}>
        <input className="field" aria-label="会话名称" value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} />
        <button className="button primary" disabled={!title.trim() || saving}>保存名称</button>
      </form>
    </Modal>
    <Modal open={!!remove} title="删除会话" onClose={() => { if (!saving) setRemove(null) }}>
      {error && <p role="alert" className="action-error">{error}</p>}
      <p>删除「{remove?.title}」及其会话消息？</p>
      <button type="button" className="button" onClick={() => void confirmDelete()} disabled={saving}>确认删除</button>
    </Modal>
  </aside>
}
