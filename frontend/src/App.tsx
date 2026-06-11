import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { useParams, useNavigate, Routes, Route } from 'react-router-dom';
import { Header } from './components/Header';
import { EditathonSelector } from './components/EditathonSelector';
import { ProgressBar } from './components/ProgressBar';
import DailyProgress from './components/DailyProgress';
import { toBengaliDigits } from './utils';
import { Download, Copy, Award, AlertCircle } from 'lucide-react';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : '';
axios.defaults.baseURL = API_BASE_URL;
axios.defaults.withCredentials = true;

interface Editathon {
  code: string;
  name: string;
}

interface Article {
  title: string;
  actualTitle: string;
  status: string;
  words: number;
  isRedirect: boolean;
  hasConflict?: boolean;
  multiJuror?: boolean;
  jurors?: string;
}

interface UserData {
  accepted: number;
  unreviewed: number;
  rejected: number;
  total: number;
  conflicts: number;
  articles: Article[];
}

type SortConfig = {
  key: string;
  direction: 'asc' | 'desc';
} | null;

const AppContent: React.FC = () => {
  const { code, tab } = useParams();
  const navigate = useNavigate();
  const [editathons, setEditathons] = useState<Editathon[]>([]);
  const [selectedCode, setSelectedCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [progressVisible, setProgressVisible] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [wordCountData, setWordCountData] = useState<Record<string, UserData>>();
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [juryStats, setJuryStats] = useState<any>();
  const [jurySubTab, setJurySubTab] = useState<'stats' | 'conflicts'>('stats');
  const [rejectedArticles, setRejectedArticles] = useState<any>();
  const [dailyStats, setDailyStats] = useState<any[]>();
  const [activeTab, setActiveTab] = useState<'wordcount' | 'jury' | 'rejected' | 'daily'>('wordcount');
  const [siteUrl, setSiteUrl] = useState('');
  const [sortConfig, setSortConfig] = useState<SortConfig>(null);
  const [conflictSearch, setConflictSearch] = useState('');

  useEffect(() => {
    const init = async () => {
      try {
        const edRes = await axios.get('/api/editathons');
        setEditathons(edRes.data.editathons);
      } catch (err) {
        console.error('Init error', err);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleWordCount = useCallback(async (targetCode: string) => {
    if (!targetCode) return;
    setError(''); setWordCountData(undefined); setJuryStats(undefined); setRejectedArticles(undefined);
    setProgressVisible(true); setProgress(5); setExpandedUser(null);
    setSortConfig({ key: 'accepted', direction: 'desc' });

    try {
      const response = await fetch(`${API_BASE_URL}/api/count_words`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: targetCode })
      });
      if (!response.ok) throw new Error('Network response was not ok');
      const reader = response.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const chunk = JSON.parse(line);
          if (chunk.type === 'info') setSiteUrl(chunk.site_url);
          else if (chunk.type === 'cache') {
            setWordCountData(chunk.data[0]); setSiteUrl(chunk.data[1]);
          } else if (chunk.type === 'update') {
            setProgress(prev => Math.min(prev + 1, 95));
            setWordCountData(prev => {
              if (!prev) return prev;
              const next = { ...prev };
              chunk.articles.forEach((art: any) => {
                const user = art.user;
                if (!next[user]) {
                  next[user] = { accepted: 0, unreviewed: 0, rejected: 0, total: 0, conflicts: 0, articles: [] };
                }
                const userObj = { ...next[user], articles: [...next[user].articles] };
                const existingIdx = userObj.articles.findIndex((a: any) => a.title === art.title);

                if (existingIdx > -1) {
                  const old = userObj.articles[existingIdx];
                  userObj.total -= old.words;
                  if (old.status === 'গৃহীত হয়েছে') userObj.accepted -= old.words;
                  else if (old.status === 'গৃহীত হয়নি') userObj.rejected -= old.words;
                  else userObj.unreviewed -= old.words;
                  userObj.articles[existingIdx] = art;
                } else {
                  userObj.articles.push(art);
                }

                userObj.total += art.words;
                if (art.status === 'গৃহীত হয়েছে') userObj.accepted += art.words;
                else if (art.status === 'গৃহীত হয়নি') userObj.rejected += art.words;
                else userObj.unreviewed += art.words;

                next[user] = userObj;
              });
              return next;
            });
          } else if (chunk.type === 'complete') {
            setWordCountData(chunk.data[0]); setSiteUrl(chunk.data[1]);
            setProgress(100); setTimeout(() => setProgressVisible(false), 500);
          } else if (chunk.type === 'error') { setError(chunk.message); setProgressVisible(false); }
        }
      }
    } catch (err: any) { setError(err.message); setProgressVisible(false); }
  }, []);

  const handleJuryStats = useCallback(async (targetCode: string) => {
    if (!targetCode) return;
    setError(''); setWordCountData(undefined); setJuryStats(undefined); setRejectedArticles(undefined);
    setJurySubTab('stats'); setSortConfig({ key: 'total', direction: 'desc' });
    try {
      const res = await axios.post('/api/jury_stats', { code: targetCode });
      setJuryStats(res.data);
    } catch (err: any) { setError(err.message); }
  }, []);

  const handleRejectedArticles = useCallback(async (targetCode: string) => {
    if (!targetCode) return;
    setError(''); setWordCountData(undefined); setJuryStats(undefined); setRejectedArticles(undefined);
    setSortConfig(null);
    try {
      const res = await axios.post('/api/rejected_articles', { code: targetCode });
      setRejectedArticles(res.data);
    } catch (err: any) { setError(err.message); }
  }, []);

  const handleDailyStats = useCallback(async (targetCode: string) => {
    if (!targetCode) return;
    setError(''); setWordCountData(undefined); setJuryStats(undefined); setRejectedArticles(undefined);
    setDailyStats(undefined);
    try {
      const res = await axios.post('/api/daily_stats', { code: targetCode });
      setDailyStats(res.data);
    } catch (err: any) { setError(err.message); }
  }, []);

  useEffect(() => {
    if (code) {
      setSelectedCode(code);
      if (!tab) {
        navigate(`/${code}/wordcount`, { replace: true });
        return;
      }
    }
    if (tab) setActiveTab(tab as any);
    
    if (code && tab) {
      if (tab === 'wordcount') handleWordCount(code);
      else if (tab === 'jury') handleJuryStats(code);
      else if (tab === 'rejected') handleRejectedArticles(code);
      else if (tab === 'daily') handleDailyStats(code);
    }
  }, [code, tab, navigate, handleWordCount, handleJuryStats, handleRejectedArticles, handleDailyStats]);

  const onSelectEditathon = (newCode: string) => {
    setSelectedCode(newCode);
    navigate(`/${newCode}/${activeTab}`);
  };

  const onTabChange = (newTab: string) => {
    setActiveTab(newTab as any);
    if (selectedCode) {
      navigate(`/${selectedCode}/${newTab}`);
    }
  };

  const toggleUser = (user: string) => {
    setExpandedUser(expandedUser === user ? null : user);
  };

  const effectiveSort = useMemo(() => {
    return sortConfig || { key: 'accepted', direction: 'desc' as const };
  }, [sortConfig]);

  const sortedWordCountData = useMemo(() => {
    if (!wordCountData) return [];
    let items = Object.entries(wordCountData).map(([user, data]) => ({ user, ...data }));
    items.sort((a, b) => {
      const aVal = (a as any)[effectiveSort.key];
      const bVal = (b as any)[effectiveSort.key];
      if (aVal < bVal) return effectiveSort.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return effectiveSort.direction === 'asc' ? 1 : -1;
      return 0;
    });
    return items;
  }, [wordCountData, effectiveSort]);

  const sortedJuryStats = useMemo(() => {
    if (!juryStats || !juryStats.raw.stats) return [];
    let items = juryStats.raw.stats.map(([user, s]: any) => ({ user, ...s }));
    items.sort((a: any, b: any) => {
      const aVal = a[effectiveSort.key === 'accepted' ? 'total' : effectiveSort.key] || 0;
      const bVal = b[effectiveSort.key === 'accepted' ? 'total' : effectiveSort.key] || 0;
      if (aVal < bVal) return effectiveSort.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return effectiveSort.direction === 'asc' ? 1 : -1;
      return 0;
    });
    return items;
  }, [juryStats, effectiveSort]);

  const sortedConflicts = useMemo(() => {
    if (!juryStats || !juryStats.raw.conflicts) return [];
    let items = [...juryStats.raw.conflicts];

    if (conflictSearch) {
      const s = conflictSearch.toLowerCase();
      items = items.filter((c: any) => c.title.toLowerCase().includes(s));
    }

    if (sortConfig && (sortConfig.key === 'title' || sortConfig.key === 'hasConflict')) {
      const { key, direction } = sortConfig;
      items.sort((a: any, b: any) => {
        const aVal = a[key];
        const bVal = b[key];
        if (aVal < bVal) return direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return items;
  }, [juryStats, sortConfig, conflictSearch]);

  const requestSort = (key: string) => {
    let direction: 'asc' | 'desc' | null = 'desc';
    if (sortConfig && sortConfig.key === key) {
      if (sortConfig.direction === 'desc') direction = 'asc';
      else if (sortConfig.direction === 'asc') direction = null;
    }
    if (direction === null) setSortConfig(null);
    else setSortConfig({ key, direction });
  };

  const getSortIcon = (key: string) => {
    const isActive = effectiveSort.key === key;
    const direction = effectiveSort.direction;
    return (
      <span className="sort-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="m7 9 5-5 5 5" style={{ opacity: isActive && direction === 'asc' ? 1 : 0.2 }} />
          <path d="m7 15 5 5 5-5" style={{ opacity: isActive && direction === 'desc' ? 1 : 0.2 }} />
        </svg>
      </span>
    );
  };

  const topPerformers = useMemo(() => {
    if (!wordCountData) return { gold: '', silver: '', bronze: '' };
    const sorted = Object.entries(wordCountData)
      .map(([user, data]) => ({ user, accepted: data.accepted }))
      .sort((a, b) => b.accepted - a.accepted);
    return {
      gold: sorted[0]?.user || '',
      silver: sorted[1]?.user || '',
      bronze: sorted[2]?.user || ''
    };
  }, [wordCountData]);

  const renderBadge = (user: string) => {
    if (user === topPerformers.gold) return <Award size={18} color="#ffd700" fill="#ffd70033" />;
    if (user === topPerformers.silver) return <Award size={18} color="#c0c0c0" fill="#c0c0c033" />;
    if (user === topPerformers.bronze) return <Award size={18} color="#cd7f32" fill="#cd7f3233" />;
    return null;
  };

  const getBengaliOrdinal = (n: number) => {
    const ordinals: Record<number, string> = {
      1: '১ম', 2: '২য়', 3: '৩য়', 4: '৪র্থ', 5: '৫ম',
      6: '৬ষ্ঠ', 7: '৭ম', 8: '৮ম', 9: '৯ম', 10: '১০ম'
    };
    return ordinals[n] || '';
  };

  const copyWikitable = () => {
    if (!wordCountData) return;
    let wt = '{| class="wikitable sortable"\n! # !! ব্যবহারকারী !! গৃহীত শব্দসংখ্যা !! অবস্থান\n';
    
    sortedWordCountData.forEach((d, i) => {
      const rank = i + 1;
      const ordinal = getBengaliOrdinal(rank);
      const rowStyle = rank <= 10 ? ' style="background:#f9f9f9;"' : '';
      
      if (rank === 11) {
        wt += '|- class="sortbottom" style="background:#eeeeee; height:2px;"\n| colspan="4" |\n';
      }
      
      wt += `|-${rowStyle}\n| ${toBengaliDigits(rank)} || [[উইকিপিডিয়া:অমর_একুশে_নিবন্ধ_প্রতিযোগিতা_২০২৬/ফলাফল#${d.user}|${d.user}]] || ${toBengaliDigits(d.accepted)} || ${ordinal}\n`;
    });
    wt += '|}';
    navigator.clipboard.writeText(wt);
    alert('মূল উইকি টেবিল ক্লিপবোর্ডে কপি করা হয়েছে!');
  };

  const copyDetailedStats = () => {
    if (!wordCountData) return;
    let wt = '';
    
    // Sort by accepted words desc
    const sorted = Object.entries(wordCountData)
      .map(([user, data]) => ({ user, ...data }))
      .sort((a, b) => b.accepted - a.accepted);

    sorted.forEach(d => {
      // Only include if they have at least one accepted article
      const acceptedArticles = d.articles.filter(a => a.status === 'গৃহীত হয়েছে');
      if (acceptedArticles.length === 0) return;

      wt += `=== [[User:${d.user}|${d.user}]] ===\n`;
      wt += '{| class="wikitable sortable"\n! নিবন্ধের নাম !! শব্দসংখ্যা\n';
      
      acceptedArticles.forEach(art => {
        wt += `|-\n| [[${art.title}]] || ${toBengaliDigits(art.words)}\n`;
      });
      
      wt += `|-\n| '''মোট শব্দ''' || '''${toBengaliDigits(d.accepted)}'''\n`;
      wt += '|}\n\n';
    });

    navigator.clipboard.writeText(wt);
    alert('বিস্তারিত পরিসংখ্যান ক্লিপবোর্ডে কপি করা হয়েছে!');
  };

  const downloadDetailedStats = () => {
    if (!wordCountData) return;
    let wt = '';
    const sorted = Object.entries(wordCountData)
      .map(([user, data]) => ({ user, ...data }))
      .sort((a, b) => b.accepted - a.accepted);

    sorted.forEach(d => {
      const acceptedArticles = d.articles.filter(a => a.status === 'গৃহীত হয়েছে');
      if (acceptedArticles.length === 0) return;
      wt += `=== [[User:${d.user}|${d.user}]] ===\n`;
      wt += '{| class="wikitable sortable"\n! নিবন্ধের নাম !! শব্দসংখ্যা\n';
      acceptedArticles.forEach(art => {
        wt += `|-\n| [[${art.title}]] || ${toBengaliDigits(art.words)}\n`;
      });
      wt += `|-\n| '''মোট শব্দ''' || '''${toBengaliDigits(d.accepted)}'''\n`;
      wt += '|}\n\n';
    });

    const blob = new Blob([wt], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `detailed_stats_${selectedCode}.txt`;
    a.click();
  };

  const copyJuryWikitable = () => {
    if (!juryStats || !juryStats.raw.stats) return;
    let wt = '{| class="wikitable sortable"\n! ক্রমিক !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n';
    sortedJuryStats.forEach((s: any, i: number) => {
      wt += `|-\n| ${toBengaliDigits(i + 1)} || ${s.user} || ${toBengaliDigits(s.total)} || ${toBengaliDigits(s.accepted)} || ${toBengaliDigits(s.rejected)}\n`;
    });
    wt += '|}';
    navigator.clipboard.writeText(wt);
    alert('পর্যালোচনা পরিসংখ্যান কপি করা হয়েছে!');
  };

  const downloadCSV = () => {
    if (!wordCountData) return;
    let csv = 'Rank,User,Accepted,Unreviewed,Rejected,Total Words\n';
    sortedWordCountData.forEach((d, i) => {
      csv += `${i + 1},${d.user},${d.accepted},${d.unreviewed},${d.rejected},${d.total}\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stats_${selectedCode}.csv`;
    a.click();
  };

  return (
    <div className="app-wrapper">
      <div className="container">
        <Header />
        <EditathonSelector editathons={editathons} loading={loading} onSelect={onSelectEditathon} selected={selectedCode} />
        <div className="controls">
          <div className="buttons main-actions">
            <button className={`btn ${activeTab === 'wordcount' ? 'primary' : 'secondary'}`} onClick={() => onTabChange('wordcount')}>শব্দসংখ্যা পরিসংখ্যান</button>
            <button className={`btn ${activeTab === 'jury' ? 'primary' : 'secondary'}`} onClick={() => onTabChange('jury')}>পর্যালোচনা পরিসংখ্যান</button>
            <button className={`btn ${activeTab === 'daily' ? 'primary' : 'secondary'}`} onClick={() => onTabChange('daily')}>প্রতিদিনের অগ্রগতি</button>
            <button className={`btn ${activeTab === 'rejected' ? 'primary' : 'secondary'}`} onClick={() => onTabChange('rejected')}>বাতিলকৃত নিবন্ধ</button>
          </div>
        </div>
        {error && <div className="error-box"><AlertCircle size={18} /> {error}</div>}
        <ProgressBar visible={progressVisible} progress={progress} />
        {wordCountData && activeTab === 'wordcount' && (
          <div className="card">
            <div className="card-header">
              <div className="small">ফলাফল</div>
              <div className="card-actions">
                <button className="btn btn-sm secondary" onClick={copyDetailedStats} title="বিস্তারিত পরিসংখ্যান কপি করুন"><Copy size={14} /> বিস্তারিত কপি</button>
                <button className="btn btn-sm secondary" onClick={downloadDetailedStats} title="বিস্তারিত ডাউনলোড করুন"><Download size={14} /> বিস্তারিত ডাউনলোড</button>
                <button className="icon-btn" onClick={copyWikitable} title="মূল উইকি টেবিল কপি করুন"><Copy size={16} /></button>
                <button className="icon-btn" onClick={downloadCSV} title="CSV ডাউনলোড করুন"><Download size={16} /></button>
              </div>
            </div>
            <div className="table-wrap">
              <table className="wordcount-table">
                <thead>
                  <tr>
                    <th>ক্রমিক</th>
                    <th onClick={() => requestSort('user')} style={{ cursor: 'pointer' }}>ব্যবহারকারী{getSortIcon('user')}</th>
                    <th onClick={() => requestSort('accepted')} style={{ cursor: 'pointer' }}>গৃহীত{getSortIcon('accepted')}</th>
                    <th onClick={() => requestSort('unreviewed')} style={{ cursor: 'pointer' }}>অপর্যালোচিত{getSortIcon('unreviewed')}</th>
                    <th onClick={() => requestSort('rejected')} style={{ cursor: 'pointer' }}>বাতিল{getSortIcon('rejected')}</th>
                    <th onClick={() => requestSort('total')} style={{ cursor: 'pointer' }}>মোট শব্দ{getSortIcon('total')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedWordCountData.map((data, index) => (
                    <React.Fragment key={data.user}>
                      <tr 
                        className={`user-row ${expandedUser === data.user ? 'active' : ''}`} 
                        onClick={() => toggleUser(data.user)}
                      >
                        <td>{toBengaliDigits(index + 1)}</td>
                        <td className="user-td">
                          <span className="badge-wrap">{renderBadge(data.user)}</span> 
                          {data.user}
                        </td>
                        <td className="num-td">{toBengaliDigits(data.accepted)}</td>
                        <td className="num-td">{toBengaliDigits(data.unreviewed)}</td>
                        <td className="num-td">{toBengaliDigits(data.rejected)}</td>
                        <td className="num-td strong highlight">{toBengaliDigits(data.total)}</td>
                      </tr>
                      {expandedUser === data.user && (
                        <tr className="articles-row">
                          <td colSpan={6}>
                            <div className="inner-table-container">
                              <table className="inner-table">
                                <thead>
                                  <tr>
                                    <th style={{ width: '40%' }}>নিবন্ধের নাম</th>
                                    <th style={{ width: '20%' }}>অবস্থা</th>
                                    <th style={{ width: '25%' }}>পর্যালোচক</th>
                                    <th style={{ width: '15%' }}>শব্দসংখ্যা</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {data.articles.map((art, i) => (
                                    <tr key={i} className={art.multiJuror ? 'multi-juror-row' : ''}>
                                      <td className="left"><div className="article-link-cell">
                                        <a href={`https://${siteUrl}/wiki/${encodeURIComponent(art.title)}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{art.title} {art.isRedirect && <span className="small-text">(পুনর্নির্দেশ)</span>}</a>
                                      </div></td>
                                      <td><span className={`status-badge ${art.status === 'গৃহীত হয়েছে' ? 'success' : art.status === 'গৃহীত হয়নি' ? 'danger' : 'neutral'}`}>{art.status}</span></td>
                                      <td><span className="jurors-text">{art.jurors || 'N/A'}</span></td>
                                      <td className="num-td">{toBengaliDigits(art.words)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {juryStats && activeTab === 'jury' && (
          <div className="card">
            <div className="card-header">
              <div className="sub-tabs-container" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <div className="sub-tabs">
                  <button className={`sub-tab ${jurySubTab === 'stats' ? 'active' : ''}`} onClick={() => setJurySubTab('stats')}>পরিসংখ্যান</button>
                  <button className={`sub-tab ${jurySubTab === 'conflicts' ? 'active' : ''}`} onClick={() => setJurySubTab('conflicts')}>একাধিক পর্যালোচক ({toBengaliDigits(juryStats.raw?.conflicts?.length || 0)})</button>
                </div>
                {jurySubTab === 'conflicts' && (
                  <div className="search-box-mini">
                    <input 
                      type="text" 
                      placeholder="নিবন্ধ খুঁজুন..." 
                      value={conflictSearch} 
                      onChange={(e) => setConflictSearch(e.target.value)}
                      className="mini-search-input"
                    />
                  </div>
                )}
              </div>
              <div className="card-actions">
                <button className="icon-btn" onClick={copyJuryWikitable} title="উইকি টেবিল কপি করুন"><Copy size={16} /></button>
              </div>
            </div>
            <div className="table-wrap">
              {jurySubTab === 'stats' ? (
                <table>
                  <thead><tr><th>#</th><th onClick={() => requestSort('user')} style={{ cursor: 'pointer' }}>পর্যালোচক{getSortIcon('user')}</th><th onClick={() => requestSort('total')} style={{ cursor: 'pointer' }}>মোট{getSortIcon('total')}</th><th onClick={() => requestSort('accepted')} style={{ cursor: 'pointer' }}>গৃহীত{getSortIcon('accepted')}</th><th onClick={() => requestSort('rejected')} style={{ cursor: 'pointer' }}>বাতিল{getSortIcon('rejected')}</th></tr></thead>
                  <tbody>{sortedJuryStats.map((s: any, i: number) => (<tr key={s.user}><td>{toBengaliDigits(i + 1)}</td><td>{s.user}</td><td className="num-td">{toBengaliDigits(s.total)}</td><td className="num-td">{toBengaliDigits(s.accepted)}</td><td className="num-td">{toBengaliDigits(s.rejected)}</td></tr>))}</tbody>
                </table>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '80px' }}>ক্রমিক</th>
                      <th onClick={() => requestSort('title')} style={{ cursor: 'pointer' }}>নিবন্ধের নাম{getSortIcon('title')}</th>
                      <th>পর্যালোচকদের সিদ্ধান্ত</th>
                      <th onClick={() => requestSort('hasConflict')} style={{ cursor: 'pointer', width: '120px' }}>অবস্থা{getSortIcon('hasConflict')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedConflicts.length > 0 ? (
                      sortedConflicts.map((c: any, i: number) => (
                        <tr key={i} className={c.hasConflict ? 'conflict-row' : ''}>
                          <td>{toBengaliDigits(i + 1)}</td>
                          <td className="left text-wrap">{c.title}</td>
                          <td className="left">
                            <div className="conflict-jurors">
                              {Array.isArray(c.jurors) ? c.jurors.map((j: any, idx: number) => (
                                <span key={idx} className={`juror-badge ${j.status}`}>
                                  {j.user} {j.isFirst && <span className="first-badge">১ম</span>}
                                </span>
                              )) : <span className="small-text">{c.jurors}</span>}
                            </div>
                          </td>
                          <td>
                            {c.hasConflict ? (
                                <span className="status-badge danger">দ্বিমত</span>
                            ) : (
                                <span className="status-badge success">ঐকমত্য</span>
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={4}>কোনো নিবন্ধ পাওয়া যায়নি।</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
        {rejectedArticles && activeTab === 'rejected' && (
          <div className="card">
            <div className="card-header"><div className="small">বাতিলকৃত নিবন্ধ</div></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>ক্রমিক</th><th>নিবন্ধের নাম</th></tr></thead>
                <tbody>{rejectedArticles.rejected_articles.map((name: string, i: number) => (<tr key={name}><td>{toBengaliDigits(i + 1)}</td><td className="left">{name}</td></tr>))}</tbody>
              </table>
            </div>
          </div>
        )}
        {dailyStats && activeTab === 'daily' && (
          <DailyProgress data={dailyStats} code={selectedCode} />
        )}
      </div>
      <footer className="footer"><div className="footer-content"><div className="footer-section"><p className="copyright">© ২০২৬ | উইকি এডিটাথন টুলস</p><p className="small-text">উইকিপিডিয়া এডিটাথন পরিচালনার একটি উন্মুক্ত টুল।</p></div><div className="footer-links"><a href="https://github.com/shafayet/ztools" target="_blank" rel="noreferrer" className="footer-link">GitHub</a></div></div></footer>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<AppContent />} />
      <Route path="/:code" element={<AppContent />} />
      <Route path="/:code/:tab" element={<AppContent />} />
    </Routes>
  );
};

export default App;
