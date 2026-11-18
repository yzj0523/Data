import { lazy, Suspense } from 'react'

import type { Answer } from '../api'

const ResultChart = lazy(() => import('./ResultChart'))

export function answerText(result: Answer) {
  const table = [result.columns ?? [], ...(result.rows ?? [])]
    .map((row) => row.map((cell) => cell ?? '不可计算').join('\t')).filter(Boolean).join('\n')
  return [result.summary, table].filter(Boolean).join('\n')
}

export function AnswerCard({ result }: { result: Answer }) {
  const stats = result.statistics
  const run = result.execution
  return (
    <div className="answer-card">
      <p>{result.summary}</p>
      {stats && <p className="answer-stats">{stats.row_count} 条结果
        {stats.total !== undefined && ` · 合计 ${stats.total} ${stats.unit}`}
        {stats.average !== undefined && ` · 平均 ${stats.average} ${stats.unit} · 最小 ${stats.minimum} · 最大 ${stats.maximum}`}
      </p>}
      {!!result.rows?.length && <div className="table-scroll"><table><thead><tr>
        {result.columns?.map((name, index) => <th key={index} scope="col">{name}</th>)}
      </tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>
        {row.map((cell, column) => <td key={column}>{cell ?? '不可计算'}</td>)}
      </tr>)}</tbody></table></div>}
      {result.chart ? <Suspense fallback={<p>正在加载图表…</p>}><ResultChart data={result.chart} /></Suspense>
        : result.chart_reason && <p>{result.chart_reason}</p>}
      {run && <details className="execution"><summary>分析过程</summary>
        <p>模型 {run.model} · {run.row_count} 行 · {run.elapsed_ms} 毫秒{run.tokens !== undefined && ` · ${run.tokens} Token`}</p>
        <p>{run.definition}</p>
        {run.date_start && run.date_end_exclusive && <p>统计区间 {run.date_start} 至 {run.date_end_exclusive}（不含）</p>}
        <ul>{run.sources.map((source) => <li key={source.id}>{source.name} · 截至 {source.as_of} · {source.version}</li>)}</ul>
        <pre>{JSON.stringify(run.filters, null, 2)}</pre>
        <pre>{run.sql}{'\n参数 '}{JSON.stringify(run.parameters)}</pre>
        {run.comparison && <pre>{run.comparison.sql}{'\n对比参数 '}{JSON.stringify(run.comparison.parameters)}</pre>}
      </details>}
    </div>
  )
}
