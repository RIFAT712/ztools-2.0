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

const DailyProgress: React.FC<DailyProgressProps> = ({ data, code }) => {
  if (!data || data.length === 0) {
    return <div className="no-data">কোনো তথ্য পাওয়া যায়নি।</div>;
  }

  const formatYAxis = (value: number) => {
    if (value >= 10000000) {
      return toBengaliDigits((value / 10000000).toFixed(1)) + ' কোটি';
    }
    if (value >= 100000) {
      return toBengaliDigits((value / 100000).toFixed(1)) + ' লক্ষ';
    }
    if (value >= 1000) {
      return toBengaliDigits((value / 1000).toFixed(1)) + ' হাজার';
    }
    return toBengaliDigits(value);
  };
  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return toBengaliDigits(d.getDate()) + ' ' + d.toLocaleDateString('bn-BD', { month: 'short' });
  };

  const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000'
    : 'https://ztools.toolforge.org';

  return (
    <div className="daily-progress">
      <div className="charts-grid">
        <div className="chart-container card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="small">মোট শব্দসংখ্যা বৃদ্ধি</div>
            {code && (
              <a 
                href={`${API_BASE_URL}/api/daily_graph/${code}?metric=total_words&format=svg`} 
                className="icon-btn" 
                title="SVG ডাউনলোড করুন"
                download={`words_growth_${code}.svg`}
              >
                <Download size={14} />
              </a>
            )}
          </div>
          <div className="chart-body" style={{ height: '300px', width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ left: 20, right: 20, top: 10 }}>
                <defs>
                  <linearGradient id="colorWords" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2563eb" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#2563eb" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={formatDate} 
                  tick={{ fontSize: 14 }} 
                  minTickGap={30}
                />
                <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 14 }} width={80} />
                <Tooltip 
                  labelFormatter={(label) => {
                    const d = new Date(label);
                    return d.toLocaleDateString('bn-BD', { 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric',
                      weekday: 'long'
                    });
                  }}
                  formatter={(value: any) => [toBengaliDigits(value), 'মোট শব্দ']}
                  contentStyle={{ 
                    backgroundColor: 'var(--card)', 
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    color: 'var(--text)'
                  }}
                  itemStyle={{ color: 'var(--text)' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="total_words" 
                  stroke="#2563eb" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorWords)" 
                  name="মোট শব্দ"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-container card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="small">মোট নিবন্ধ সংখ্যা</div>
            {code && (
              <a 
                href={`${API_BASE_URL}/api/daily_graph/${code}?metric=total_count&format=svg`} 
                className="icon-btn" 
                title="SVG ডাউনলোড করুন"
                download={`articles_count_${code}.svg`}
              >
                <Download size={14} />
              </a>
            )}
          </div>
          <div className="chart-body" style={{ height: '300px', width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ left: 20, right: 20, top: 10 }}>
                <defs>
                  <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={formatDate} 
                  tick={{ fontSize: 14 }} 
                  minTickGap={30}
                />
                <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 14 }} width={80} />
                <Tooltip 
                  labelFormatter={(label) => {
                    const d = new Date(label);
                    return d.toLocaleDateString('bn-BD', { 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric',
                      weekday: 'long'
                    });
                  }}
                  formatter={(value: any) => [toBengaliDigits(value), 'মোট নিবন্ধ']}
                  contentStyle={{ 
                    backgroundColor: 'var(--card)', 
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    color: 'var(--text)'
                  }}
                  itemStyle={{ color: 'var(--text)' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="total_count" 
                  stroke="#10b981" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorCount)" 
                  name="মোট নিবন্ধ"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-container card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="small">প্রতিদিনের নিবন্ধ জমা</div>
            {code && (
              <a 
                href={`${API_BASE_URL}/api/daily_graph/${code}?metric=daily_count&format=svg`} 
                className="icon-btn" 
                title="SVG ডাউনলোড করুন"
                download={`daily_articles_${code}.svg`}
              >
                <Download size={14} />
              </a>
            )}
          </div>
          <div className="chart-body" style={{ height: '300px', width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ left: 20, right: 20, top: 10 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={formatDate} 
                  tick={{ fontSize: 14 }} 
                  minTickGap={30}
                />
                <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 14 }} width={80} />
                <Tooltip 
                  labelFormatter={(label) => {
                    const d = new Date(label);
                    return d.toLocaleDateString('bn-BD', { 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric',
                      weekday: 'long'
                    });
                  }}
                  formatter={(value: any) => [toBengaliDigits(value), 'নতুন নিবন্ধ']}
                  contentStyle={{ 
                    backgroundColor: 'var(--card)', 
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    color: 'var(--text)'
                  }}
                  itemStyle={{ color: 'var(--text)' }}
                />
                <Bar dataKey="daily_count" fill="#f59e0b" radius={[4, 4, 0, 0]} name="নতুন নিবন্ধ" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-container card">
          <div className="chart-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="small">প্রতিদিনের শব্দসংখ্যা</div>
            {code && (
              <a 
                href={`${API_BASE_URL}/api/daily_graph/${code}?metric=daily_words&format=svg`} 
                className="icon-btn" 
                title="SVG ডাউনলোড করুন"
                download={`daily_words_${code}.svg`}
              >
                <Download size={14} />
              </a>
            )}
          </div>
          <div className="chart-body" style={{ height: '300px', width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ left: 20, right: 20, top: 10 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={formatDate} 
                  tick={{ fontSize: 14 }} 
                  minTickGap={30}
                />
                <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 14 }} width={80} />
                <Tooltip 
                  labelFormatter={(label) => {
                    const d = new Date(label);
                    return d.toLocaleDateString('bn-BD', { 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric',
                      weekday: 'long'
                    });
                  }}
                  formatter={(value: any) => [toBengaliDigits(value), 'শব্দসংখ্যা']}
                  contentStyle={{ 
                    backgroundColor: 'var(--card)', 
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    color: 'var(--text)'
                  }}
                  itemStyle={{ color: 'var(--text)' }}
                />
                <Bar dataKey="daily_words" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="শব্দসংখ্যা" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
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
        }
        .chart-body {
          margin-top: 15px;
        }
        .no-data {
          padding: 40px;
          text-align: center;
          color: #666;
          background: white;
          border-radius: 8px;
          margin-top: 20px;
        }
      `}</style>
    </div>
  );
};

export default DailyProgress;
