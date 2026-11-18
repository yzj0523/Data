"""Translate a natural-language request and record its database result."""

import json
import logging
from datetime import date
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from app.api import ApiError, settings_for
from app.config import Settings
from app.models import active_model
from app.preferences import load_preferences
from app.provider import complete
from app.query_plan import METRICS, TARGET_METRICS, Interpretation, Plan, compile_plan, compile_special, execute_plan, prior_year_window, time_window
from app.results import shape_result
from app.sessions import expire_pending, require_session, session_store, turn_json, utc_now
from app.sources import catalog
from app.shortcuts import record_question

router = APIRouter()
logger = logging.getLogger(__name__)
RequestId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class QueryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    source_ids: list[str] = Field(max_length=8)
    request_id: RequestId
    operation: Literal['ask','edit','resend'] = 'ask'
    origin_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode='after')
    def operation_origin(self):
        if (self.operation == 'ask' and self.origin_id is not None) or (
            self.operation != 'ask' and not (self.origin_id or '').strip()
        ):
            raise ValueError('Only edit and resend require an origin message')
        return self


def interpret(settings: Settings, model, question: str, prior: dict | None):
    schema = json.dumps(Interpretation.model_json_schema(), ensure_ascii=False)
    result, tokens = complete(model, [
        {'role':'system','content': '''你是销售问数的查询计划解析器。只输出符合 JSON Schema 的对象，不生成 SQL。
确认收入 revenue，含税签约额 gross_contract，不含税签约额 net_contract，回款 paid，商业/商解完成率 commercial_rate/solution_rate，高风险项目数量/明细 risk_count/risk_details（未要求分组时用 total）。
年度商业目标金额 commercial_target，年度商解目标金额 solution_target，支持按经营单元或合计。
division 填经营单元名称或地区，group 是聚合维度，min_wan/max_wan 是聚合后的万元区间。政企是行业大类。排行的 top 是名次，share 表示占比。
明确年份输出整数；相对时间使用 this_year、last_year、this_month，按月趋势用 group=month 并选 line，同比用 yoy=true。
未指定时间时省略 year；高风险项目显式指定时间时按落地日期筛选。
独立问题返回完整 plan。若明显引用同会话的上一次成功查询，返回 changes 对象，仅列出本次修改的 Plan 字段。
没有前次计划时遇到省略式追问，或「销量最好」等缺少指标口径的问题，返回 clarification=true。
''' + schema + '\n前次成功查询计划：' + json.dumps(prior, ensure_ascii=False)},
        {'role':'user','content':question},
    ], structured=True, timeout=settings.model_timeout_seconds)
    try:
        return Interpretation.model_validate(result), tokens
    except ValidationError:
        raise ApiError(502, 'model_plan_invalid', '模型返回的查询计划不符合约束。') from None


def answer(settings: Settings, question, source_ids, sources, prior=None):
    start = monotonic()
    model = active_model(settings)
    if model is None:
        raise ApiError(503, 'model_unavailable', '没有可用模型，请配置默认模型或选择自定义模型。')
    interpretation, tokens = interpret(settings, model, question, prior)
    if interpretation.clarification:
        return 'clarification', {'summary':'请明确指标、时间范围或筛选条件。'}
    plan = interpretation.plan
    if interpretation.changes is not None:
        if prior is None:
            return 'clarification', {'summary':'当前会话没有可继承的查询。请补充指标和时间范围。'}
        try:
            plan = Plan.model_validate(prior | interpretation.changes)
        except ValidationError:
            raise ApiError(502, 'model_plan_invalid', '模型返回的追问条件不符合约束。') from None
    source = 'projects' if plan.metric.startswith('risk_') else 'targets' if plan.metric in TARGET_METRICS else 'sales'
    start_date, end_date = time_window(plan, sources.get(source, {}).get('as_of') or '1900-01-01')
    compiler = compile_plan if plan.metric in METRICS else compile_special
    sql, args, used = compiler(plan, source_ids, settings.query_max_rows, start_date, end_date)
    raw_rows = execute_plan(settings, sql, args, used, allow_top_boundary=plan.top is not None and plan.top <= settings.query_max_rows)
    incomplete_sales = plan.metric in METRICS and any(row['value'] is None for row in raw_rows)
    if incomplete_sales and (plan.top is not None or plan.min_wan is not None or plan.max_wan is not None or plan.share):
        return 'clarification', {'summary':'查询范围内有金额缺失，无法确定排名、金额区间或占比。请缩小范围，或查看不带这些条件的结果。'}
    if plan.top and (plan.share or (len(raw_rows) > plan.top and raw_rows[plan.top-1]['value'] == raw_rows[plan.top]['value'])):
        return 'clarification', {'summary':'Top N 的并列或占比口径尚待确认，请取消占比或改为展示完整排名。'}
    if plan.top:
        raw_rows = raw_rows[:plan.top]
    if plan.metric == 'risk_details':
        values = [list(row.values()) for row in raw_rows]
        columns = ['项目编号','项目名称','经营单元','阶段','落地日期']
    elif plan.metric == 'risk_count':
        values = [[row['label'],row['value']] for row in raw_rows]
        columns = ['分组','高风险项目数（个）']
    elif plan.metric in ('commercial_rate','solution_rate'):
        columns = ['经营单元','完成率（%）','实际（万元）','目标（万元）']
        if any(not row['target_cents'] or row['target_cents'] < 0 for row in raw_rows):
            return 'clarification', {'summary':'查询范围含零值或缺失目标，完成率口径尚待确认。请指定目标完整的经营单元。'}
        if plan.group == 'total' and raw_rows:
            actuals = [row['actual_cents'] for row in raw_rows]
            raw_rows = [{'label':'合计','actual_cents':sum(actuals) if all(value is not None for value in actuals) else None,
                         'target_cents':sum(row['target_cents'] for row in raw_rows)}]
        values = [[row['label'], round(row['actual_cents']/row['target_cents']*100,2) if row['actual_cents'] is not None else None,
                   row['actual_cents']/1_000_000 if row['actual_cents'] is not None else None,row['target_cents']/1_000_000] for row in raw_rows]
    else:
        values = [[row['label'], row['value'] / 1_000_000 if row['value'] is not None else None] for row in raw_rows]
        metric_name = (TARGET_METRICS if plan.metric in TARGET_METRICS else METRICS)[plan.metric][0]
        columns = ['分组', f'{metric_name}（万元）']
        if plan.metric in TARGET_METRICS:
            end_date = date(start_date.year + 1, 1, 1)
    comparison = None
    incomplete_baseline = False
    if plan.yoy and values:
        baseline_plan = plan.model_copy(update={'top':None,'min_wan':None,'max_wan':None})
        base_sql, base_args, _ = compile_plan(baseline_plan, source_ids, settings.query_max_rows, *prior_year_window(start_date, end_date))
        baseline = {row['label']:row['value'] for row in execute_plan(settings, base_sql, base_args, used)}
        for result_row, raw_row in zip(values, raw_rows):
            label = raw_row['label']
            if plan.group == 'month':
                label = f'{int(label[:4])-1}{label[4:]}'
            old = baseline.get(label)
            if old is None and label in baseline:
                incomplete_baseline = True
            current = raw_row['value']
            result_row.extend([old / 1_000_000 if old is not None else None,
                               round((current-old)/old*100, 2) if old and current is not None else None])
        columns.extend(['同期（万元）','同比（%）'])
        comparison = {'sql':base_sql,'parameters':base_args}
    if plan.share and values:
        if any(row[1] < 0 for row in values):
            return 'clarification', {'summary':'含负金额时的占比口径尚待确认。'}
        total = sum(row[1] for row in values)
        values = [row + [round(row[1]/total*100, 2) if total else None] for row in values]
        columns.append('占比（%）')
    execution = {'sql': sql, 'parameters': args, 'sources': [sources[key] for key in used],
                 'elapsed_ms': round((monotonic()-start)*1000), 'model':model.name, 'row_count':len(values),
                 'date_start':start_date.isoformat(),'date_end_exclusive':end_date.isoformat()}
    if comparison:
        execution['comparison'] = comparison
    if tokens is not None:
        execution['tokens'] = tokens
    result = shape_result(plan, columns, values, execution)
    if incomplete_sales:
        matched = sum(row['matched_count'] for row in raw_rows)
        known = sum(row['known_count'] for row in raw_rows)
        result['summary'] += f' 匹配的 {matched} 条业务记录中有 {matched-known} 条金额缺失，相关金额和完整合计不可计算。'
    if incomplete_baseline:
        result['summary'] += ' 同期有记录的金额缺失，相关同期金额及同比不可计算。'
    if values and load_preferences(settings).suggestions_enabled:
        if plan.metric.startswith('risk_'):
            suggestions = ['查看高风险项目明细','统计高风险项目总数','按经营单元统计高风险项目数量']
        elif plan.metric in TARGET_METRICS:
            metric_name = TARGET_METRICS[plan.metric][0]
            suggestions = [f'按经营单元查看{metric_name}', f'查看{metric_name}合计', f'用条形图展示{metric_name}']
        elif plan.metric.endswith('_rate'):
            metric_name = '商业完成率' if plan.metric == 'commercial_rate' else '商解完成率'
            suggestions = [f'查看{metric_name}的实际和目标', f'用条形图展示{metric_name}', f'用柱状图展示{metric_name}']
        else:
            metric_name = METRICS[plan.metric][0]
            suggestions = [f'按产品线查看{metric_name}，展示完整结果', f'按月查看{metric_name}趋势', f'比较{metric_name}与去年同期']
        result['suggestions'] = suggestions
    return ('ok' if values else 'empty'), result


@router.post('/sessions/{session_id}/queries')
def query(session_id: str, payload: QueryInput, settings: Settings = Depends(settings_for)):
    if len(payload.question) > settings.question_max_length:
        raise ApiError(422, 'question_too_long', '问题超出当前长度限制。')
    if not payload.source_ids:
        raise ApiError(422, 'sources_required', '请先选择至少一个数据源。')
    sources = {s['id']:s for s in catalog(settings)}
    source_ids = list(dict.fromkeys(payload.source_ids))
    if any(key not in sources or not sources[key]['available'] for key in source_ids):
        raise ApiError(422, 'source_unavailable', '所选数据源不存在或当前不可用。')
    turn_id = uuid4().hex
    now = utc_now().isoformat()
    question = payload.question
    with session_store(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        require_session(db, session_id)
        if expire_pending(db, settings, session_id):
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            require_session(db, session_id)
        existing = db.execute('SELECT * FROM turns WHERE session_id=? AND request_id=?', (session_id,payload.request_id)).fetchone()
        if existing:
            if payload.operation == 'resend' and payload.origin_id:
                original = db.execute('SELECT question FROM turns WHERE id=? AND session_id=?', (payload.origin_id,session_id)).fetchone()
                if original:
                    question = original['question']
            if (existing['operation'] != payload.operation or existing['question'] != question
                or json.loads(existing['source_ids']) != source_ids or existing['origin_id'] != payload.origin_id):
                raise ApiError(409, 'request_conflict', '该请求标识已用于其他提问。')
            staged_edit = existing['operation'] == 'edit' and existing['status'] in ('pending','failed','clarification')
            if not existing['active'] and not staged_edit:
                raise ApiError(409, 'query_obsolete', '此前的查询已失效。')
            return turn_json(existing)
        if db.execute("SELECT 1 FROM turns WHERE session_id=? AND status='pending'", (session_id,)).fetchone():
            raise ApiError(409, 'query_in_progress', '当前会话已有查询，请等待本次查询结束。')
        position = db.execute('SELECT COALESCE(MAX(position),0)+1 FROM turns WHERE session_id=?', (session_id,)).fetchone()[0]
        context_before = position
        if payload.operation != 'ask':
            original = db.execute('SELECT * FROM turns WHERE id=? AND session_id=? AND active=1', (payload.origin_id,session_id)).fetchone()
            if not original:
                raise ApiError(404, 'turn_not_found', '指定的会话消息不存在。')
            context_before = original['position']
            if payload.operation == 'edit':
                position = context_before
            else:
                question = original['question']
        context = db.execute("SELECT result,source_ids FROM turns WHERE session_id=? AND active=1 AND status='ok' AND position<? ORDER BY position DESC LIMIT 1", (session_id,context_before)).fetchone()
        prior = json.loads(context['result']).get('plan') if context and set(json.loads(context['source_ids'])) == set(source_ids) else None
        db.execute('''INSERT INTO turns (id,session_id,position,request_id,question,status,source_ids,created_at,origin_id,operation,active)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                   (turn_id,session_id,position,payload.request_id,question,'pending',json.dumps(source_ids),now,payload.origin_id,
                    payload.operation,payload.operation != 'edit'))
    try:
        status, result = answer(settings, question, source_ids, sources, prior)
    except ApiError as exc:
        status, result = 'failed', {'code':exc.code,'summary':exc.message}
    except Exception:
        logger.error('Unable to finish an admitted query.')
        status, result = 'failed', {'code':'query_unavailable','summary':'查询暂时无法完成，请稍后重试。'}
    with session_store(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        updated = db.execute("UPDATE turns SET status=?,result=? WHERE id=? AND status='pending'", (status,json.dumps(result,ensure_ascii=False),turn_id))
        if not updated.rowcount:
            raise ApiError(409, 'query_obsolete', '会话或问题已变更，此次结果未保存。')
        if payload.operation == 'edit' and status in ('ok','empty'):
            db.execute('UPDATE turns SET active=0 WHERE session_id=? AND position>=? AND active=1', (session_id,position))
            db.execute('UPDATE turns SET active=1 WHERE id=?', (turn_id,))
        row = db.execute('SELECT * FROM turns WHERE id=?', (turn_id,)).fetchone()
        if status == 'ok' and payload.operation == 'ask':
            record_question(db, question)
        db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (utc_now().isoformat(),session_id))
        return turn_json(row)
