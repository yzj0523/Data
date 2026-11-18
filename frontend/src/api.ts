export class ApiError extends Error {
  constructor(message: string, public readonly code: string) { super(message) }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, validate?: (value: unknown) => value is T): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    })
  } catch {
    throw new ApiError('无法连接服务，请检查网络后重试。', 'network_error')
  }
  if (response.status === 204 && !validate) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok || data === null) {
    throw new ApiError(data?.error?.message ?? '服务暂时不可用，请稍后重试。', data?.error?.code ?? 'service_error')
  }
  if (validate && !validate(data)) {
    throw new ApiError('服务返回的内容格式异常，请重试。', 'invalid_response')
  }
  return data as T
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失败，请稍后重试。'
}

export type Session = { id: string; title: string; pinned: boolean; updated_at: string }
export type Source = { id: string; name: string; group: string; fields: string[]; available: boolean; as_of: string | null; version: string | null }
export type Cell = string | number | null
export type ChartData = { type: 'bar' | 'horizontal' | 'line' | 'pie'; dimension: string; metric: string; unit: string; points: { label: string; value: number | null }[] }
export type Execution = { sql: string; parameters: Cell[]; sources: Source[]; elapsed_ms: number; model: string; tokens?: number;
  row_count: number; definition: string; date_start?: string; date_end_exclusive?: string; filters: Record<string, unknown>;
  comparison?: { sql: string; parameters: Cell[] } }
export type Answer = { summary: string; columns?: string[]; rows?: Cell[][]; code?: string;
  statistics?: { row_count: number; unit: string; total?: number; average?: number; maximum?: number; minimum?: number };
  chart?: ChartData | null; chart_reason?: string | null; execution?: Execution; suggestions?: string[] }
export type Turn = { id: string; session_id: string; position: number; request_id: string; question: string;
  status: 'pending' | 'ok' | 'empty' | 'clarification' | 'failed'; result: Answer | null; source_ids: string[]; active: boolean }
export type Preferences = { greeting_enabled: boolean; greeting: string; opening_questions: string[];
  suggestions_enabled: boolean; hot_enabled: boolean; hot_threshold: number; custom_model_enabled: boolean }
type FeedbackStatus = 'pending' | 'resolved'
type FeedbackItem = { id: string; question: string; reporter: string; status: FeedbackStatus; created_at: string }
export type FeedbackDetail = FeedbackItem & { notes: string; answer: Answer }
export type FeedbackList = { items: FeedbackItem[]; page: number; pages: number; total: number }

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const isString = (value: unknown): value is string => typeof value === 'string'
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const isCell = (value: unknown): value is Cell => value === null || isString(value) || isNumber(value)
const isArrayOf = (value: unknown, check: (entry: unknown) => boolean) => Array.isArray(value) && value.every(check)
const optional = (value: unknown, check: (entry: unknown) => boolean) => value === undefined || check(value)

function isExecution(value: unknown) {
  return isObject(value) && isString(value.sql) && isArrayOf(value.parameters, isCell) && isObject(value.filters) &&
    isString(value.model) && isString(value.definition) && isNumber(value.row_count) && isNumber(value.elapsed_ms) &&
    optional(value.tokens, isNumber) && optional(value.date_start, isString) && optional(value.date_end_exclusive, isString) &&
    isArrayOf(value.sources, (source) => isObject(source) && isString(source.id) && isString(source.name) &&
      (source.as_of === null || isString(source.as_of)) && (source.version === null || isString(source.version))) &&
    optional(value.comparison, (comparison) => isObject(comparison) && isString(comparison.sql) &&
      isArrayOf(comparison.parameters, isCell))
}

function isAnswer(value: unknown) {
  return isObject(value) && isString(value.summary) && optional(value.columns, (columns) => isArrayOf(columns, isString)) &&
    optional(value.rows, (rows) => isArrayOf(rows, (row) => isArrayOf(row, isCell))) &&
    optional(value.suggestions, (suggestions) => isArrayOf(suggestions, isString)) &&
    optional(value.execution, isExecution) && optional(value.chart_reason, (reason) => reason === null || isString(reason)) &&
    optional(value.statistics, (stats) => isObject(stats) && isNumber(stats.row_count) && isString(stats.unit) &&
      [stats.total, stats.average, stats.minimum, stats.maximum].every((number) => optional(number, isNumber))) &&
    optional(value.chart, (chart) => chart === null || (isObject(chart) &&
      ['bar','horizontal','line','pie'].some((type) => type === chart.type) &&
      isString(chart.dimension) && isString(chart.metric) && isString(chart.unit) &&
      isArrayOf(chart.points, (point) => isObject(point) && isString(point.label) && (point.value === null || isNumber(point.value)))))
}

export function isTurn(value: unknown): value is Turn {
  return isObject(value) && isString(value.id) && isString(value.session_id) && isNumber(value.position) &&
    isString(value.request_id) && isString(value.question) && typeof value.active === 'boolean' &&
    isArrayOf(value.source_ids, isString) &&
    (value.status === 'pending' ? value.result === null :
      ['ok','empty','clarification','failed'].some((status) => status === value.status) && isAnswer(value.result))
}

export function isHistory(value: unknown): value is Turn[] {
  return isArrayOf(value, (turn) => isTurn(turn) && turn.active)
}

export function isReportReceipt(value: unknown): value is { id: string } {
  return isObject(value) && isString(value.id) && value.id.length > 0
}

function isFeedbackItem(value: unknown): value is FeedbackItem {
  return isObject(value) && isString(value.id) && isString(value.question) && isString(value.reporter) &&
    (value.status === 'pending' || value.status === 'resolved') &&
    isString(value.created_at) && Number.isFinite(Date.parse(value.created_at))
}

export function isFeedbackList(value: unknown): value is FeedbackList {
  return isObject(value) && Array.isArray(value.items) && value.items.every(isFeedbackItem) &&
    isNumber(value.page) && Number.isInteger(value.page) && value.page >= 1 &&
    isNumber(value.pages) && Number.isInteger(value.pages) && value.pages >= value.page &&
    isNumber(value.total) && Number.isInteger(value.total) && value.total >= value.items.length
}

export function isFeedbackDetail(value: unknown): value is FeedbackDetail {
  return isObject(value) && isString(value.notes) && isAnswer(value.answer) && isFeedbackItem(value)
}
