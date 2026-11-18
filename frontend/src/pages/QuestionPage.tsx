import { useEffect, useRef, useState, type FormEvent } from 'react'

import { ApiError, api, errorMessage, isHistory, isReportReceipt, isTurn, type Preferences, type Session, type Source, type Turn } from '../api'
import { AnswerCard, answerText } from '../components/AnswerCard'
import { Icon } from '../components/Icon'
import { Modal } from '../components/Modal'
import { SourcePicker } from '../components/SourcePicker'
import { SessionHistory } from '../components/SessionHistory'

const sessionKey = 'ai-query-session'

function readCurrentSession() {
  try { return sessionStorage.getItem(sessionKey) }
  catch { return null }
}

function storeCurrentSession(id: string | null) {
  try {
    if (id) sessionStorage.setItem(sessionKey,id)
    else sessionStorage.removeItem(sessionKey)
  } catch { /* Session navigation also works without browser storage. */ }
}

function newRequestId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2,'0')).join('')
}

export function QuestionPage() {
  const [session, setSession] = useState(readCurrentSession)
  const [histories, setHistories] = useState<Record<string, Turn[]>>({})
  const [sessions, setSessions] = useState<Session[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const activeSession = useRef(session)
  const activeQueries = useRef(new Set<string>())
  const historyVersions = useRef<Record<string, number>>({})
  const deletedSessions = useRef(new Set<string>())
  const retryIds = useRef(new Map<string,string>())
  const reportRetryIds = useRef(new Map<string,string>())
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const turns = session ? histories[session] ?? [] : []
  const [question, setQuestion] = useState('')
  const [editId, setEditId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [report, setReport] = useState<Turn | null>(null)
  const [reporting, setReporting] = useState(false)
  const [reportError, setReportError] = useState('')
  const busy = pending.has(session ?? '') || turns.some((turn) => turn.status === 'pending')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sources, setSources] = useState<Source[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [sourceError, setSourceError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [preferenceError, setPreferenceError] = useState('')
  const [preferenceAttempt, setPreferenceAttempt] = useState(0)
  const [sourceAttempt, setSourceAttempt] = useState(0)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [favorites, setFavorites] = useState<string[]>([])
  const [hot, setHot] = useState<{question:string;count:number}[]>([])
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  async function refreshShortcuts() {
    const [saved, frequent] = await Promise.all([api<string[]>('/favorites'),api<{question:string;count:number}[]>('/questions/hot')])
    setFavorites(saved)
    setHot(frequent)
  }

  async function favorite(text: string, enabled: boolean) {
    try { setFavorites(await api<string[]>('/favorites','PUT',{question:text,enabled})) }
    catch (failure) { setError(errorMessage(failure)) }
  }

  function choose(id: string | null, keepDraft = false) {
    activeSession.current = id
    storeCurrentSession(id)
    setSession(id)
    if (!keepDraft) setQuestion('')
    setEditId(null)
    setError('')
    setHistoryError('')
    setNotice('')
  }

  async function refreshSessions() {
    const items = await api<Session[]>('/sessions')
    setSessions(items)
    return items
  }

  async function changeSession(id: string, changes: Partial<Session>) {
    const updated = await api<Session>(`/sessions/${id}`, 'PATCH', changes)
    setSessions((items) => items.map((item) => item.id === id ? updated : item))
    void refreshSessions().catch((failure: unknown) => setError(errorMessage(failure)))
  }

  async function removeSession(id: string) {
    await api(`/sessions/${id}`, 'DELETE')
    deletedSessions.current.add(id)
    const remaining = sessions.filter((item) => item.id !== id)
    setSessions(remaining)
    if (id === activeSession.current) choose(remaining[0]?.id ?? null)
    void refreshSessions().catch((failure: unknown) => setError(errorMessage(failure)))
  }

  useEffect(() => {
    let current = true
    api<Source[]>('/sources').then((items) => { if (current) setSources(items) })
      .catch((failure: unknown) => { if (current) setSourceError(errorMessage(failure)) })
    return () => { current = false }
  }, [sourceAttempt])

  useEffect(() => {
    let current = true
    api<Preferences>('/app-config').then((value) => { if (current) {setPreferences(value);setPreferenceError('')} })
      .catch((failure:unknown) => { if (current) setPreferenceError(errorMessage(failure)) })
    return () => { current = false }
  }, [preferenceAttempt])

  useEffect(() => {
    if (!session) return
    let current = true
    const version = historyVersions.current[session]
    api(`/sessions/${session}/messages`, 'GET', undefined, isHistory).then((history) => {
      if (current && historyVersions.current[session] === version) {
        setHistories((previous) => ({...previous,[session]:history}))
        setHistoryError('')
      }
    }).catch((failure: unknown) => {
      if (!current || historyVersions.current[session] !== version) return
      if (failure instanceof ApiError && failure.code === 'session_not_found') {
        storeCurrentSession(null)
        activeSession.current = null
        setSession(null)
        setError(errorMessage(failure))
      } else {
        setHistoryError(errorMessage(failure))
      }
    })
    return () => { current = false }
  }, [session,historyRefresh])

  useEffect(() => {
    if (!session) return
    let current = true
    api<string[]>('/favorites').then((saved) => { if (current) setFavorites(saved) }).catch(() => undefined)
    return () => { current = false }
  }, [session])

  const waitingForHistory = turns.some((turn) => turn.status === 'pending')
  useEffect(() => {
    if (!waitingForHistory) return
    const timer = window.setInterval(() => setHistoryRefresh((n) => n + 1),1000)
    return () => window.clearInterval(timer)
  }, [waitingForHistory,session])

  async function send(text: string, operation: 'ask' | 'edit' | 'resend' = 'ask', origin?: string) {
    const value = text.trim()
    const owner = activeSession.current ?? ''
    if (!value || activeQueries.current.has(owner) || busy) return
    if (!selected.length) { setError('请先选择至少一个数据源。'); return }
    activeQueries.current.add(owner)
    setPending(new Set(activeQueries.current))
    setError('')
    setNotice('')
    let id = activeSession.current
    let retryKey = ''
    try {
      if (!id) {
        id = (await api<Session>('/sessions', 'POST', { title: value.slice(0, 60) })).id
        if (activeSession.current === null) choose(id,true)
        activeQueries.current.add(id)
        setPending(new Set(activeQueries.current))
      }
      retryKey = JSON.stringify([id,operation,origin,value,selected])
      const requestId = retryIds.current.get(retryKey) ?? newRequestId()
      retryIds.current.set(retryKey,requestId)
      const path = `/sessions/${id}/queries`
      const payload = {question:value,source_ids:selected,request_id:requestId,operation,origin_id:origin}
      let turn = await api(path, 'POST', payload, isTurn)
      for (let attempt = 0; turn.status === 'pending' && attempt < 20; attempt++) {
        await new Promise((resolve) => setTimeout(resolve,250))
        turn = await api(path,'POST',payload,isTurn)
      }
      if (turn.status === 'pending') throw new ApiError('查询仍在处理中，请稍后重试。','query_pending')
      retryIds.current.delete(retryKey)
      if (deletedSessions.current.has(id)) return
      if (!turn.active) {
        if (activeSession.current === id) setError(`编辑未生效。${turn.result?.summary ?? ''}`)
        return
      }
      const destination = id
      historyVersions.current[destination] = (historyVersions.current[destination] ?? 0) + 1
      setHistories((previous) => ({...previous, [destination]:[...(previous[destination] ?? []).filter((item) => item.id !== turn.id &&
        (operation !== 'edit' || item.position < turn.position)), turn].sort((a,b) => a.position-b.position)}))
      if (activeSession.current === id) {
        if (operation === 'edit') setEditId(null)
        setQuestion('')
      }
      if (historyOpen) void refreshSessions().catch(() => undefined)
      if (shortcutsOpen) void refreshShortcuts().catch(() => undefined)
    } catch (failure) {
      if (!(failure instanceof ApiError) || !['network_error','service_error','invalid_response','query_pending'].includes(failure.code)) retryIds.current.delete(retryKey)
      if (activeSession.current === id) setError(errorMessage(failure))
    } finally {
      activeQueries.current.delete(owner)
      if (id) activeQueries.current.delete(id)
      setPending(new Set(activeQueries.current))
    }
  }

  async function copy(text: string) {
    setNotice('')
    try { await navigator.clipboard.writeText(text); setNotice('已复制。') }
    catch { setNotice('无法复制，请选择文字后手动复制。') }
  }

  async function sendReport() {
    if (!report || reporting) return
    setReporting(true); setReportError('')
    const requestId = reportRetryIds.current.get(report.id) ?? newRequestId()
    reportRetryIds.current.set(report.id, requestId)
    try {
      await api('/feedbacks','POST',{turn_id:report.id,request_id:requestId},isReportReceipt)
      reportRetryIds.current.delete(report.id)
      setReport(null)
      setNotice('反馈已提交。')
    }
    catch (failure) { setReportError(errorMessage(failure)) }
    finally { setReporting(false) }
  }

  function submit(event: FormEvent) { event.preventDefault(); void send(question) }

  return (
    <section className="question-workspace" aria-label="智能问数工作区">
      <div className="conversation-header"><span>{sessions.find((item) => item.id === session)?.title ?? 'AI 智能问数对话'}</span>
        <button type="button" className="button quiet" aria-expanded={historyOpen} onClick={() => {
          if (!historyOpen) void refreshSessions().catch((failure: unknown) => setError(errorMessage(failure)))
          setHistoryOpen(!historyOpen)
        }}><Icon name="history" />历史会话</button>
      </div>
      {historyOpen && <SessionHistory sessions={sessions} active={session} onChoose={choose}
        onNew={() => { void api<Session>('/sessions', 'POST', {}).then((item) => { choose(item.id); return refreshSessions() }).catch((failure: unknown) => setError(errorMessage(failure))) }}
        onChange={changeSession} onDelete={removeSession} />}
      {turns.length ? <div className="conversation-turns" aria-label="会话消息">
        {turns.map((turn) => <article key={turn.id} className="conversation-turn">
          <div className="user-message">
            {editId === turn.id ? <form onSubmit={(event) => { event.preventDefault(); void send(editText, 'edit', turn.id) }}>
              <input className="field" aria-label="编辑问题" value={editText} onChange={(event) => setEditText(event.target.value)} />
              <div className="action-row"><button className="button primary" disabled={busy || !editText.trim()}>发送修改</button>
                <button type="button" className="button" onClick={() => setEditId(null)}>取消编辑</button></div>
            </form> : <>
              <p>{turn.question}</p>
              <div className="action-row">
                <button type="button" className="button quiet" onClick={() => void copy(turn.question)}>复制问题</button>
                <button type="button" className="button quiet" aria-pressed={favorites.includes(turn.question)}
                  onClick={() => void favorite(turn.question,!favorites.includes(turn.question))}>{favorites.includes(turn.question) ? '取消收藏' : '收藏问题'}</button>
                <button type="button" className="button quiet" disabled={busy} onClick={() => { setEditId(turn.id); setEditText(turn.question) }}>编辑重发</button>
                <button type="button" className="button quiet" disabled={busy} onClick={() => void send(turn.question, 'resend', turn.id)}>重新发送</button>
              </div>
            </>}
          </div>
          {turn.result && <div>
            {turn.status === 'failed' ? <p role="alert">查询失败。{turn.result.summary}</p> : <AnswerCard result={turn.result} />}
            <button type="button" className="button quiet" onClick={() => void copy(answerText(turn.result!))}>复制回复</button>
            {turn.status === 'ok' && <button type="button" className="button quiet" onClick={() => {setReport(turn);setReportError('')}}>数据有误</button>}
            {preferences?.suggestions_enabled && !!turn.result.suggestions?.length && <div className="action-row" aria-label="下一步问题建议">
              {turn.result.suggestions.map((item) => <button key={item} type="button" className="button" disabled={busy} onClick={() => void send(item)}>{item}</button>)}
            </div>}
          </div>}
        </article>)}
      </div> : <div className="welcome">
        <div className="welcome-mark"><Icon name="robot" /></div>
        <h2>你好<span>我是 AI 问数助手</span></h2>
        {preferences?.greeting_enabled && <p>{preferences.greeting}</p>}
        {preferences?.greeting_enabled && !!preferences.opening_questions.length && <div className="question-examples" aria-label="开场问题">
          <p className="examples-label">你可以这么问我</p>
          {preferences.opening_questions.map((example,index) => <button type="button" className="example-button" disabled={busy} key={index}
            onClick={() => void send(example)}><span>{example}</span><Icon name="arrow" /></button>)}
        </div>}
      </div>}
      <form className="question-composer" onSubmit={submit}>
        <div className="action-row">
          <SourcePicker sources={sources} selected={selected} onChange={setSelected} />
          <button type="button" className="button" aria-expanded={shortcutsOpen} onClick={() => {
            if (!shortcutsOpen) void refreshShortcuts().catch((failure: unknown) => setError(errorMessage(failure)))
            setShortcutsOpen(!shortcutsOpen)
          }}>快捷提问</button>
          {sourceError && <button type="button" className="button" onClick={() => { setSourceError(''); setSourceAttempt((n) => n + 1) }}>重试加载数据源</button>}
        </div>
        {shortcutsOpen && <section className="shortcut-list" aria-label="收藏问题">
          <h3>常问</h3>
          {!hot.length && <p>暂无常问问题。</p>}
          {hot.map((item) => <div className="action-row" key={item.question}>
            <button type="button" className="button" disabled={busy} onClick={() => void send(item.question)}>{item.question}</button>
            <span>{item.count} 次</span>
          </div>)}
          <h3>收藏</h3>
          {!favorites.length && <p>暂无收藏。可从会话中的问题添加。</p>}
          {favorites.map((item) => <div className="action-row" key={item}>
            <button type="button" className="button" disabled={busy} onClick={() => void send(item)}>{item}</button>
            <button type="button" className="button quiet" aria-label={`移除收藏 ${item}`} onClick={() => void favorite(item,false)}>移除</button>
          </div>)}
        </section>}
        {sourceError && <p className="action-error" role="alert">{sourceError}</p>}
        {historyError && <p className="action-error" role="alert">无法刷新会话记录。{historyError}{' '}
          <button type="button" className="button" onClick={() => setHistoryRefresh((n) => n+1)}>重试加载会话</button></p>}
        {preferenceError && <p className="action-error" role="alert">无法读取问答设置。{preferenceError}{' '}
          <button type="button" className="button" onClick={() => setPreferenceAttempt((n) => n+1)}>重试读取设置</button></p>}
        {error && <p className="action-error" role="alert">{error}</p>}
        {(busy || notice) && <p role="status">{busy ? '正在查询…' : notice}</p>}
        <div className="composer-input">
          <input aria-label="问题" placeholder="请写下您的想法…" value={question} disabled={busy} onChange={(event) => setQuestion(event.target.value)} />
          <button type="submit" className="send-button" aria-label="发送问题" disabled={busy || !question.trim()}><Icon name="arrow" /></button>
        </div>
      </form>
      <Modal open={!!report} title="报告数据有误" onClose={() => {if (!reporting) setReport(null)}}>
        <p>将提交该问题与答案的快照。</p><p>{report?.question}</p>
        {reportError && <p role="alert" className="action-error">{reportError}</p>}
        <button type="button" className="button primary" disabled={reporting} onClick={() => void sendReport()}>提交反馈</button>
      </Modal>
    </section>
  )
}
