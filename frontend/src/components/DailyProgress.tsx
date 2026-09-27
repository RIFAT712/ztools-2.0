import React from 'react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area
} from 'recharts';
import { toBengaliDigits } from '../utils';
import { Download } from 'lucide-react';

interface DailyStats {
  date: string;
  daily_count: number;
  daily_words: number;
  total_count: number;
  total_words: number;
}

interface DailyProgressProps {
  data: DailyStats[];
  code?: string;
}

const MONTHS = ['জানুয়ারি', 'ফেব্রুয়ারি', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টেম্বর', 'অক্টোবর', 'নভেম্বর', 'ডিসেম্বর'];
const WEEKDAYS = ['রবিবার', 'সোমবার', 'মঙ্গলবার', 'বুধবার', 'বৃহস্পতিবার', 'শুক্রবার', 'শনিবার'];

const CHARTS = [
  { key: 'total_words', title: 'মোট শব্দসংখ্যা বৃদ্ধি', name: 'মোট শব্দ', color: '#2563eb', area: true, file: 'শব্দ_বৃদ্ধি' },
  { key: 'total_count', title: 'মোট নিবন্ধ সংখ্যা', name: 'মোট নিবন্ধ', color: '#10b981', area: true, file: 'নিবন্ধ_সংখ্যা' },
  { key: 'daily_count', title: 'প্রতিদিনের নিবন্ধ জমা', name: 'নতুন নিবন্ধ', color: '#f59e0b', area: false, file: 'প্রতিদিনের_নিবন্ধ' },
  { key: 'daily_words', title: 'প্রতিদিনের শব্দসংখ্যা', name: 'শব্দসংখ্যা', color: '#8b5cf6', area: false, file: 'প্রতিদিনের_শব্দ' },
];

const formatYAxis = (value: number) => {
  const format = (v: number, unit: string) => {
    const rounded = Math.round(v * 10) / 10;
    const str = rounded % 1 === 0 ? rounded.toString() : rounded.toFixed(1);
    return toBengaliDigits(str) + ' ' + unit;
  };

  if (value >= 10000000) return format(value / 10000000, 'কোটি');
  if (value >= 100000) return format(value / 100000, 'লক্ষ');
  if (value >= 1000) return format(value / 1000, 'হাজার');
  return toBengaliDigits(value);
};

const formatDate = (dateStr: string) => {
  const d = new Date(dateStr);
  return toBengaliDigits(d.getDate()) + ' ' + MONTHS[d.getMonth()] + ' ' + toBengaliDigits(d.getFullYear(), false);
};

// Serialize the chart recharts already rendered into a standalone .svg file.
const downloadSvg = (btn: HTMLElement, filename: string) => {
  const svg = btn.closest('.chart-container')?.querySelector('svg.recharts-surface');
  if (!svg) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' }));
  a.download = filename;
  a.click();
};

const DailyProgress: React.FC<DailyProgressProps> = ({ data, code }) => {
  if (!data || data.length === 0) {
    return <div className="no-data">কোনো তথ্য পাওয়া যায়নি।</div>;
  }

  return (
    <div className="daily-progress">
      <div className="charts-grid">
        {CHARTS.map(c => {
          const Chart = c.area ? AreaChart : BarChart;
          return (
            <div key={c.key} className="chart-container card">
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="small">{c.title}</div>
                {code && (
                  <button className="icon-btn" title="SVG ডাউনলোড করুন" onClick={e => downloadSvg(e.currentTarget, `${c.file}_${code}.svg`)}>
                    <Download size={14} />
                  </button>
                )}
              </div>
              <div className="chart-body" style={{ height: '300px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <Chart data={data} margin={{ left: 20, right: 20, top: 10 }}>
                    <defs>
                      <linearGradient id={`grad_${c.key}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={c.color} stopOpacity={0.1}/>
                        <stop offset="95%" stopColor={c.color} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--chart-grid)" />
                    <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fontSize: 14 }} minTickGap={30} />
                    <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 14 }} width={80} />
                    <Tooltip
                      labelFormatter={(label) => {
                        const d = new Date(label);
                        return WEEKDAYS[d.getDay()] + ', ' + formatDate(label);
                      }}
                      formatter={(value: any) => [toBengaliDigits(value), c.name]}
                      contentStyle={{
                        backgroundColor: 'var(--card)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--text)'
                      }}
                      itemStyle={{ color: 'var(--text)' }}
                    />
                    {c.area
                      ? <Area type="monotone" dataKey={c.key} stroke={c.color} strokeWidth={2} fillOpacity={1} fill={`url(#grad_${c.key})`} name={c.name} />
                      : <Bar dataKey={c.key} fill={c.color} radius={[4, 4, 0, 0]} name={c.name} />}
                  </Chart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>


      <style>{`
        .charts-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
          gap: 20px;
          margin-top: 20px;
        }
        @media (max-width: 600px) {
          .charts-grid {
            grid-template-columns: 1fr;
          }
        }
        .chart-container {
          padding: 15px;
          outline: none;
        }
        .chart-container *:focus {
          outline: none;
        }
        .chart-body {
          margin-top: 15px;
        }
        .no-data {
          padding: 40px;
          text-align: center;
          color: #666;
          background: var(--card);
          border-radius: 8px;
          margin-top: 20px;
        }
      `}</style>
    </div>
  );
};

export default DailyProgress;
