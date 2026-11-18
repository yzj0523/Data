"""Compile constrained query plans into parameterized business SELECTs."""

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api import ApiError
from app.config import Settings
from app.sources import SOURCE_CATALOG


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric: Literal['revenue','gross_contract','net_contract','paid','commercial_rate','solution_rate',
                    'commercial_target','solution_target','risk_count','risk_details']
    year: int | Literal['this_year','last_year','this_month'] | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    yoy: bool = False
    division: str | None = Field(default=None, max_length=100)
    industry_group: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    product_line: str | None = Field(default=None, max_length=100)
    product_model: str | None = Field(default=None, max_length=100)
    group: Literal['division','region','industry_group','industry','product_line','product_model','month','total'] = 'division'
    chart: Literal['bar','horizontal','line','pie','none'] = 'bar'
    direction: Literal['ascending','descending'] = 'descending'
    min_wan: Decimal | None = Field(default=None, max_digits=14, decimal_places=6)
    max_wan: Decimal | None = Field(default=None, max_digits=14, decimal_places=6)
    top: int | None = Field(default=None, ge=1, le=1000)
    share: bool = False

    @model_validator(mode='after')
    def bounds(self):
        if isinstance(self.year, int) and not 1900 <= self.year <= 2200:
            raise ValueError('Invalid year')
        if self.min_wan is not None and self.max_wan is not None and self.min_wan > self.max_wan:
            raise ValueError('Minimum exceeds maximum')
        return self


class Interpretation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan: Plan | None = None
    changes: dict | None = None
    clarification: bool = False

    @model_validator(mode='after')
    def one_outcome(self):
        if sum((self.clarification, self.plan is not None, self.changes is not None)) != 1:
            raise ValueError('Expected exactly one outcome')
        return self


METRICS = {
    'revenue': ('确认收入','s.revenue_cents','s.period'),
    'paid': ('回款','s.paid_cents','s.period'),
    'gross_contract': ('含税签约额','c.gross_cents','c.signed_on'),
    'net_contract': ('不含税签约额','c.net_cents','c.signed_on'),
}
TARGET_METRICS = {
    'commercial_target': ('年度商业目标','commercial_cents'),
    'solution_target': ('年度商解目标','solution_cents'),
}
GROUPS = {'division':'d.name','region':'d.region','industry_group':'c.industry_group','industry':'c.industry',
          'product_line':'p.line','product_model':'p.model','total':"'合计'"}


def business_today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


def time_window(plan: Plan, as_of: str):
    today = business_today()
    year, month = plan.year, plan.month
    if year == 'last_year':
        year = today.year - 1
    elif year == 'this_month':
        year, month = today.year, today.month
    elif year is None or year == 'this_year':
        year = today.year
    start = date(year, month or 1, 1)
    end = date(year + (month is None or month == 12), 1 if not month or month == 12 else month + 1, 1)
    cutoff = min(date.fromisoformat(as_of), today)
    return start, max(start, min(end, cutoff + timedelta(days=1)))


def prior_year_window(start: date, end: date):
    prior_start = start.replace(year=start.year-1)
    try:
        prior_end = end.replace(year=end.year-1)
    except ValueError:
        # An exclusive February 29 cutoff includes February 28 in both years.
        prior_end = date(end.year-1, 3, 1)
    return prior_start, prior_end


def compile_plan(plan: Plan, sources: list[str], limit: int, start: date, end: date):
    if 'sales' not in sources:
        raise ApiError(422, 'source_scope', '所选数据源不包含此指标。')
    _, value, date = METRICS[plan.metric]
    group = f'substr({date},1,7)' if plan.group == 'month' else GROUPS[plan.group]
    args = [start.isoformat(), end.isoformat()]
    where = [f'{date} >= ?', f'{date} < ?']
    if plan.division:
        where.append('(d.name = ? OR d.region = ?)')
        args.extend([plan.division, plan.division])
    for field in ('industry_group','industry','product_line','product_model'):
        if (value_filter := getattr(plan, field)) is not None:
            where.append(f'{GROUPS[field]} = ?')
            args.append(value_filter)
    having = []
    for operator, bound in (('>=',plan.min_wan), ('<=',plan.max_wan)):
        if bound is not None:
            having.append(f'SUM({value}) {operator} ?')
            args.append(int(bound * 1_000_000))
    complete = f'COUNT({value})=COUNT(*)'
    # Keep incomplete groups visible so unknown values cannot silently pass ranking or range checks.
    group_filter = f' HAVING NOT ({complete}) OR ({" AND ".join(having)})' if having else ''
    join = 'JOIN monthly_sales s ON s.contract_id=c.id' if date == 's.period' else ''
    order = 'ASC' if plan.direction == 'ascending' else 'DESC'
    sort = 'label ASC' if plan.group == 'month' and plan.top is None else f'value {order},label'
    if plan.top:
        sort = f'value IS NOT NULL,{sort}'
    elif plan.group != 'month':
        sort = f'value IS NULL,{sort}'
    sql = f'''SELECT {group} AS label, CASE WHEN {complete} THEN SUM({value}) END AS value,
COUNT(*) AS matched_count, COUNT({value}) AS known_count
FROM contracts c {join} JOIN divisions d ON d.id=c.division_id JOIN products p ON p.id=c.product_id
WHERE {' AND '.join(where)} GROUP BY label{group_filter} ORDER BY {sort} LIMIT ?'''
    return sql, [*args, min(limit, plan.top or limit) + 1], ('sales',)


def compile_special(plan: Plan, sources: list[str], limit: int, start: date, end: date):
    division = [plan.division, plan.division] if plan.division else []
    filter_division = ' AND (d.name=? OR d.region=?)' if division else ''
    if any((plan.industry_group,plan.industry,plan.product_line,plan.product_model,plan.top,plan.share,plan.yoy,
            plan.min_wan is not None,plan.max_wan is not None)):
        raise ApiError(422, 'unsupported_query', '该指标暂不支持这些筛选或比较条件。')
    if plan.metric in ('risk_count','risk_details'):
        if 'projects' not in sources:
            raise ApiError(422, 'source_scope', '请选中 PPL 明细台账。')
        where = "p.risk='高风险'" + filter_division
        if plan.month is not None or plan.year is not None:
            where += ' AND p.landed_on>=? AND p.landed_on<?'
            division.extend([start.isoformat(),end.isoformat()])
        base = f'FROM projects p JOIN divisions d ON d.id=p.division_id WHERE {where}'
        if plan.metric == 'risk_details':
            return (f'SELECT p.id,p.name,d.name AS division,p.stage,p.landed_on {base} ORDER BY p.id LIMIT ?',
                    [*division,limit+1],('projects',))
        if plan.group not in ('division','total'):
            raise ApiError(422, 'unsupported_query', '项目数量可查询合计或按经营单元分组。')
        group = 'd.name' if plan.group == 'division' else "'合计'"
        group_by = 'GROUP BY d.name' if plan.group == 'division' else ''
        return (f'SELECT {group} AS label, COUNT(DISTINCT p.id) AS value {base} {group_by} ORDER BY value DESC,label LIMIT ?',
                [*division,limit+1],('projects',))
    if plan.group not in ('division','total') or plan.month or plan.year == 'this_month':
        raise ApiError(422, 'unsupported_query', '目标金额和完成率支持年度查询，按经营单元或合计。')
    if plan.metric in TARGET_METRICS:
        if 'targets' not in sources:
            raise ApiError(422, 'source_scope', '请选中整体目标台账。')
        _, target = TARGET_METRICS[plan.metric]
        label = "'合计'" if plan.group == 'total' else 'd.name'
        sql = f'''SELECT {label} AS label,
CASE WHEN COUNT(t.{target})=COUNT(*) THEN SUM(t.{target}) END AS value
FROM annual_targets t JOIN divisions d ON d.id=t.division_id
WHERE t.year=?{filter_division} GROUP BY label ORDER BY label LIMIT ?'''
        return sql, [start.year,*division,limit+1], ('targets',)
    if not {'sales','targets'} <= set(sources):
        raise ApiError(422, 'source_scope', '完成率需要同时选择商业市场台账与整体目标台账。')
    commercial = plan.metric == 'commercial_rate'
    fact_date = 'c.signed_on' if commercial else 's.period'
    actual = 'c.net_cents' if commercial else 's.net_revenue_cents'
    join = '' if commercial else 'JOIN monthly_sales s ON s.contract_id=c.id'
    filter_solution = '' if commercial else ' AND c.is_solution=1'
    target = 'commercial_cents' if commercial else 'solution_cents'
    sql = f'''WITH actual AS (
SELECT c.division_id, CASE WHEN COUNT({actual})=COUNT(*) THEN SUM({actual}) END AS actual_cents
FROM contracts c {join}
WHERE {fact_date}>=? AND {fact_date}<?{filter_solution} GROUP BY c.division_id
)
SELECT d.name AS label, a.actual_cents, t.{target} AS target_cents
FROM divisions d LEFT JOIN actual a ON a.division_id=d.id
LEFT JOIN annual_targets t ON t.division_id=d.id AND t.year=?
WHERE (t.division_id IS NOT NULL OR a.division_id IS NOT NULL){filter_division}
ORDER BY d.name LIMIT ?'''
    return sql, [start.isoformat(),end.isoformat(),start.year,*division,limit+1], ('sales','targets')


READABLE_FIELDS = {
    'contracts': {'id','division_id','product_id','signed_on','industry_group','industry','gross_cents','net_cents','is_solution'},
    'monthly_sales': {'contract_id','period','revenue_cents','net_revenue_cents','paid_cents'},
    'divisions': {'id','name','region'},
    'products': {'id','line','model'},
    'annual_targets': {'division_id','year','commercial_cents','solution_cents'},
    'projects': {'id','division_id','name','stage','landed_on','risk'},
}


def execute_plan(settings: Settings, sql: str, parameters: list, source_ids: tuple[str, ...], *, allow_top_boundary=False):
    allowed = {table for key in source_ids for table in SOURCE_CATALOG[key][3]}
    deadline = monotonic() + settings.query_timeout_seconds

    def authorize(action, table, column, database, origin):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and column in {'sum','count','substr'}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and database == 'main' and table in allowed:
            if not column or column in READABLE_FIELDS.get(table, ()):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    db = None
    try:
        db = sqlite3.connect(Path(settings.database_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=settings.query_timeout_seconds)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only = ON')
        db.set_authorizer(authorize)
        db.set_progress_handler(lambda: int(monotonic() > deadline), 500)
        rows = [dict(row) for row in db.execute(sql, parameters)]
    except sqlite3.Error as exc:
        if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_INTERRUPT:
            raise ApiError(504, 'query_timeout', '查询超时，请缩小查询范围。') from None
        raise ApiError(503, 'query_unavailable', '无法读取经营数据。') from None
    finally:
        if db is not None:
            db.close()
    if len(rows) > settings.query_max_rows and not allow_top_boundary:
        raise ApiError(422, 'query_row_limit', '查询结果超过当前限制，请缩小范围。')
    return rows
