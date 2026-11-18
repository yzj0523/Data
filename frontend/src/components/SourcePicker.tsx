import { useState } from 'react'

import type { Source } from '../api'
import { Modal } from './Modal'

export function SourcePicker({ sources, selected, onChange }: {
  sources: Source[]; selected: string[]; onChange: (ids: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" className="button" onClick={() => setOpen(true)}>数据源（已选 {selected.length}）</button>
    <Modal open={open} title="选择数据源" onClose={() => setOpen(false)}>
      {sources.length ? <>
        <div className="action-row">
          <button type="button" className="button" onClick={() => onChange(sources.filter((item) => item.available).map((item) => item.id))}>全选可用来源</button>
          <button type="button" className="button" onClick={() => onChange([])}>取消全选</button>
        </div>
        {sources.map((item) => <label className="source-option" key={item.id}>
          <input type="checkbox" disabled={!item.available} checked={selected.includes(item.id)}
            onChange={(event) => onChange(event.target.checked ? [...selected,item.id] : selected.filter((id) => id !== item.id))} />
          <span>{item.name} · {item.group}{item.available ? ` · 截至 ${item.as_of}` : ' · 暂不可用'}</span>
        </label>)}
      </> : <p>当前无法读取数据源。关闭弹窗后可重试。</p>}
    </Modal>
  </>
}
