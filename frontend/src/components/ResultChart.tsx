import { useEffect, useRef } from 'react'
import { init, use, type ComposeOption } from 'echarts/core'
import { BarChart, LineChart, PieChart, type BarSeriesOption, type LineSeriesOption, type PieSeriesOption } from 'echarts/charts'
import { GridComponent, TooltipComponent, type GridComponentOption, type TooltipComponentOption } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

import type { ChartData } from '../api'

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, CanvasRenderer])
type Options = ComposeOption<BarSeriesOption | LineSeriesOption | PieSeriesOption | GridComponentOption | TooltipComponentOption>
const names = { bar: '柱状图', horizontal: '条形图', line: '折线图', pie: '饼图' }

export default function ResultChart({ data }: { data: ChartData }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const node = host.current
    if (!node) return
    const chart = init(node)
    const common: Options = { animation: false, tooltip: { renderMode:'richText', confine:true }, color: ['#2f54eb','#37a7aa','#996cd9','#df973f','#428acc'] }
    if (data.type === 'pie') {
      chart.setOption<Options>({ ...common, series: [{ type:'pie', radius:'66%', data:data.points.map((point) => ({ name:point.label,value:point.value ?? undefined })) }] })
    } else {
      const category = { type:'category' as const, data:data.points.map((point) => point.label), axisLabel:{ width:100, overflow:'truncate' as const } }
      const value = { type:'value' as const, name:data.unit }
      const horizontal = data.type === 'horizontal'
      chart.setOption<Options>({ ...common, tooltip:{trigger:'axis',renderMode:'richText',confine:true}, grid:{left:horizontal ? 112 : 55,right:26,top:30,bottom:56},
        xAxis:horizontal ? value : category, yAxis:horizontal ? category : value,
        series:[{ type:data.type === 'line' ? 'line' : 'bar', name:data.metric, data:data.points.map((point) => point.value ?? '-') }] })
    }
    const resize = new ResizeObserver(() => chart.resize())
    resize.observe(node)
    return () => { resize.disconnect(); chart.dispose() }
  }, [data])
  return <figure className="result-figure"><figcaption>{names[data.type]} · {data.dimension} · {data.metric}</figcaption>
    <div className="result-chart" ref={host} role="img" aria-label={`${names[data.type]}，${data.metric}，详细数据见表格`} />
  </figure>
}
