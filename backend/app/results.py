"""Produce display data and explanations from the executed result."""

from app.query_plan import METRICS, TARGET_METRICS

GROUP_NAMES = {
    'division':'经营单元','region':'地区','industry_group':'行业大类','industry':'行业',
    'product_line':'产品线','product_model':'产品型号','month':'月份','total':'统计范围',
}
RATE_DEFINITIONS = {
    'commercial_rate':'不含税签约额 ÷ 年度商业目标',
    'solution_rate':'商解合同不含税确认收入 ÷ 年度商解目标',
}


def shape_result(plan, columns, rows, execution):
    if plan.metric != 'risk_details':
        columns[0] = GROUP_NAMES[plan.group]
    unit = '个' if plan.metric.startswith('risk_') else '%' if plan.metric in RATE_DEFINITIONS else '万元'
    values = [row[1] for row in rows if type(row[1]) in (int,float)]
    incomplete_targets = plan.metric in TARGET_METRICS and len(values) < len(rows)
    incomplete_sales = plan.metric in METRICS and len(values) < len(rows)
    incomplete_amounts = incomplete_targets or incomplete_sales
    statistics = {'row_count':len(rows), 'unit':unit}
    if values and not incomplete_sales:
        statistics.update(average=round(sum(values)/len(values),6), maximum=max(values), minimum=min(values))
        if plan.metric not in RATE_DEFINITIONS and not incomplete_amounts:
            statistics['total'] = round(sum(values),6)
    if not rows:
        summary = '所选数据中没有符合条件的记录。'
    elif not values:
        summary = f'共查到 {len(rows)} 条记录。' if plan.metric == 'risk_details' else '查到了记录，但没有可计算的指标。'
    elif incomplete_targets:
        summary = f'查到 {len(rows)} 条结果，其中 {len(values)} 条目标金额可用。'
    elif incomplete_sales:
        summary = f'查到 {len(rows)} 条结果，其中 {len(values)} 条金额可计算。'
    elif 'total' in statistics:
        summary = f'{columns[1]}共 {statistics["total"]:g} {unit}，对应 {len(rows)} 条结果。'
    else:
        summary = f'查到 {len(rows)} 条结果，其中 {len(values)} 条完成率可计算。'
    if plan.metric in RATE_DEFINITIONS and len(values) < len(rows):
        summary += ' 部分实际金额缺失，相关实际金额及完成率无法计算。'
    if incomplete_targets:
        summary += ' 部分目标金额缺失，无法计算完整合计。'
    chart = None
    chart_reason = None
    if plan.chart != 'none':
        if plan.metric == 'risk_details' or not values:
            chart_reason = '没有适合绘图的数值。'
        elif plan.chart == 'pie' and (not all(value >= 0 for value in values) or sum(values) <= 0 or plan.metric in RATE_DEFINITIONS or plan.top or incomplete_amounts):
            chart_reason = '当前指标或结果范围不适合绘制占比。'
        else:
            chart_rows = sorted(rows, key=lambda row: row[0]) if plan.group == 'month' and plan.chart == 'line' else rows
            chart = {'type':plan.chart, 'dimension':columns[0], 'metric':columns[1], 'unit':unit,
                     'points':[{'label':row[0],'value':row[1]} for row in chart_rows]}
    if plan.metric in METRICS:
        metric, _, date_column = METRICS[plan.metric]
        definition = f'{metric}按{"统计月份" if date_column == "s.period" else "合同签订日期"}汇总'
    elif plan.metric in TARGET_METRICS:
        definition = '按目标年份汇总整体目标台账'
    elif plan.metric in RATE_DEFINITIONS:
        definition = RATE_DEFINITIONS[plan.metric]
    else:
        definition = '按项目风险等级筛选高风险，以项目编号去重'
        if plan.year is not None or plan.month is not None:
            definition += '；时间按落地日期筛选，落地日期缺失的项目不计入'
        else:
            execution.pop('date_start')
            execution.pop('date_end_exclusive')
    execution['definition'] = definition
    execution['filters'] = plan.model_dump(mode='json', exclude_none=True)
    return {'columns':columns,'rows':rows,'plan':plan.model_dump(mode='json'),'summary':summary,
            'statistics':statistics,'chart':chart,'chart_reason':chart_reason,'execution':execution}
