import { useEffect, useState, type FormEvent } from 'react'

import { api, errorMessage, isFeedbackDetail, isFeedbackList, type FeedbackDetail, type FeedbackList } from '../api'
import { answerText } from '../components/AnswerCard'
import { Modal } from '../components/Modal'

const statuses = {pending:'待处理', resolved:'已处理'}
const initialFilters = {question:'',reporter:'',status:''}

export function FeedbackPage() {
  const [filters, setFilters] = useState(initialFilters)
  const [applied, setApplied] = useState(initialFilters)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [items, setItems] = useState<FeedbackList | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [detail, setDetail] = useState<FeedbackDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [reviewError, setReviewError] = useState('')

  useEffect(() => {
    let current = true
    const query = new URLSearchParams({...applied,page:String(page),page_size:String(size)})
    if (!applied.status) query.delete('status')
    api(`/feedbacks?${query}`,'GET',undefined,isFeedbackList).then((data) => { if (current) setItems(data) })
      .catch((failure:unknown) => { if (current) setError(errorMessage(failure)) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [applied,page,size,attempt])

  function load(change: () => void) { setLoading(true);setError('');change() }

  async function open(id: string) {
    setReviewError('');setError('')
    try { setDetail(await api(`/feedbacks/${id}`,'GET',undefined,isFeedbackDetail)) }
    catch (failure) { setError(errorMessage(failure)) }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!detail || saving) return
    setSaving(true);setReviewError('')
    try {
      await api(`/feedbacks/${detail.id}`,'PATCH',{status:detail.status,notes:detail.notes},isFeedbackDetail)
      setDetail(null);load(() => setAttempt((n) => n+1))
    } catch (failure) { setReviewError(errorMessage(failure)) }
    finally { setSaving(false) }
  }

  return <section className="page-body" aria-label="回复校对内容">
    {error && <p role="alert" className="action-error">{error} <button type="button" className="button" onClick={() => load(() => setAttempt((n) => n+1))}>重新加载</button></p>}
    <section className="panel feedback-panel" aria-label="回复校对列表">
      <form className="feedback-filters" onSubmit={(event) => {event.preventDefault();load(() => {setPage(1);setApplied({...filters})})}}>
        <label>搜索问题<input type="search" maxLength={200} value={filters.question} onChange={(event) => setFilters({...filters,question:event.target.value})} /></label>
        <label>搜索用户<input type="search" maxLength={120} value={filters.reporter} onChange={(event) => setFilters({...filters,reporter:event.target.value})} /></label>
        <label>处理状态<select value={filters.status} onChange={(event) => setFilters({...filters,status:event.target.value})}>
          <option value="">全部状态</option><option value="pending">待处理</option><option value="resolved">已处理</option>
        </select></label>
        <button className="button">筛选</button>
        <button type="button" className="button quiet" onClick={() => load(() => {setFilters(initialFilters);setApplied({...initialFilters});setPage(1)})}>清除筛选</button>
      </form>
      {loading && <p role="status" className="list-status">正在读取反馈…</p>}
      {!loading && items && <>
        <div className="table-scroll"><table><thead><tr>
          {['序号','用户','问题','反馈时间','状态','操作'].map((name) => <th key={name} scope="col">{name}</th>)}
        </tr></thead><tbody>
          {items.items.map((item,index) => <tr key={item.id}>
            <td>{(items.page-1)*size+index+1}</td><td>{item.reporter}</td><td>{item.question}</td>
            <td>{new Date(item.created_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</td><td>{statuses[item.status]}</td>
            <td><button type="button" className="button quiet" aria-label={`处理 ${item.question}`} onClick={() => void open(item.id)}>处理</button></td>
          </tr>)}
          {!items.items.length && <tr><td colSpan={6}><div className="empty-feedback"><h2>暂无匹配的反馈</h2><p>可调整筛选条件，或在智能问数中反馈数据问题。</p></div></td></tr>}
        </tbody></table></div>
        <footer className="panel-footer feedback-pagination">
          <span>共 {items.total} 条 · 第 {items.page} / {items.pages} 页</span>
          <label>每页条数 <select value={size} onChange={(event) => load(() => {setSize(Number(event.target.value));setPage(1)})}>
            {[5,10,20].map((count) => <option key={count}>{count}</option>)}
          </select></label>
          <button type="button" className="button" disabled={items.page <= 1} onClick={() => load(() => setPage(items.page-1))}>上一页</button>
          <button type="button" className="button" disabled={items.page >= items.pages} onClick={() => load(() => setPage(items.page+1))}>下一页</button>
        </footer>
      </>}
    </section>
    <Modal open={!!detail} title="处理反馈" onClose={() => {if (!saving) setDetail(null)}}>
      {detail && <form className="settings-form" onSubmit={(event) => void save(event)}>
        <p>{detail.question}</p><pre className="answer-snapshot">{answerText(detail.answer)}</pre>
        <label>处理结果<select value={detail.status} onChange={(event) => setDetail({...detail,status:event.target.value as FeedbackDetail['status']})}>
          <option value="pending">待处理</option><option value="resolved">已处理</option>
        </select></label>
        <label>处理备注<textarea className="field" value={detail.notes} maxLength={4000} rows={3} onChange={(event) => setDetail({...detail,notes:event.target.value})} /></label>
        {reviewError && <p role="alert" className="action-error">{reviewError}</p>}
        <div className="action-row"><button type="submit" className="button primary" disabled={saving}>保存处理</button>
          <button type="button" className="button quiet" disabled={saving} onClick={() => setDetail(null)}>取消处理</button></div>
      </form>}
    </Modal>
  </section>
}
