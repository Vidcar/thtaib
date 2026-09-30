import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { tokenLabel } from "./ModelControls";
import { labChartSeries } from "./labPresentation";
import type { LabRun } from "./labTypes";

const colors = ["var(--accent)", "var(--ok)", "var(--warn)", "var(--danger)", "#67bec9", "#b5baf6"];
const seriesColor = (id: string) => colors[Array.from(id).reduce((hash, character) => (hash * 31 + character.charCodeAt(0)) >>> 0, 0) % colors.length];
export function LabCharts({ runs }: { runs: LabRun[] }) {
  const legend = labChartSeries(runs, "prefill").filter(series => series.points.length);
  return <><div className="lab-charts">{(["prefill", "generation"] as const).map(metric => {
    const series = labChartSeries(runs, metric);
    const populated = series.some(item => item.points.length);
    const title = metric === "prefill" ? "Prefill" : "Generation";
    return <section className="card lab-chart" key={metric} aria-label={`${title} chart`}><div className="section-heading"><h3>{title}</h3><span className="hint">tokens / second</span></div><div className="lab-chart-plot">
      {populated ? <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 400, height: 220 }}><LineChart margin={{ top: 12, right: 12, bottom: 2, left: 2 }} accessibilityLayer>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis type="number" dataKey="x" domain={[0, "auto"]} tickFormatter={tokenLabel} stroke="var(--muted)" tick={{ fontSize: 11 }} />
        <YAxis type="number" dataKey="speed" domain={[0, "auto"]} width={48} stroke="var(--muted)" tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={{ background: "var(--bg-panel)", borderColor: "var(--border)", color: "var(--text)", fontSize: 11 }} labelFormatter={value => `${Number(value).toLocaleString()} tokens`} formatter={(value, name) => [`${Number(value).toFixed(1)} t/s`, name]} />
        {series.map(item => <Line key={item.id} name={item.name} data={item.points} dataKey="speed" type="linear" stroke={seriesColor(item.id)} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} isAnimationActive={false} />)}
      </LineChart></ResponsiveContainer> : <div className="lab-chart-empty">Measurements appear here</div>}
    </div><p className="lab-chart-axis">Reported {metric === "prefill" ? "prompt" : "context"} length (tokens)</p></section>;
  })}</div>{legend.length ? <div className="lab-chart-legend" aria-label="Chart series">{legend.map(series => <span key={series.id}><i style={{ background: seriesColor(series.id) }} />{series.name}</span>)}</div> : null}</>;
}
