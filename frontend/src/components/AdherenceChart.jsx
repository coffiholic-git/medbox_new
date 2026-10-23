import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function rateColor(rate) {
  if (rate >= 90) return "#c9b8ff";
  if (rate >= 60) return "#f472b6";
  return "#ff8a65";
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-xl border border-line bg-navy-900 px-3.5 py-2.5 text-xs shadow-lg">
      <p className="font-mono uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-bold text-ink">
        {d.taken} of {d.scheduled} doses taken
      </p>
      <p className="text-mint">{d.rate}% adherence</p>
    </div>
  );
}

export default function AdherenceChart({ data }) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 6" stroke="rgba(196,181,253,0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#a79bc9", fontSize: 12, fontFamily: "DM Mono, monospace" }}
            axisLine={{ stroke: "rgba(196,181,253,0.16)" }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "#a79bc9", fontSize: 11, fontFamily: "DM Mono, monospace" }}
            axisLine={false}
            tickLine={false}
            width={34}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(139,92,246,0.08)" }} />
          <Bar dataKey="rate" radius={[8, 8, 8, 8]} maxBarSize={28}>
            {data.map((entry, index) => (
              <Cell key={index} fill={rateColor(entry.rate)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
