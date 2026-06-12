import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Shield, UserMinus, UserCheck, Search, LogOut, AlertCircle, Loader2, ListTodo, X, Home } from 'lucide-react';

interface Participant {
  username: string;
  isBanned: boolean;
}

interface Editathon {
  code: string;
  name: string;
}

export const AdminPanel: React.FC = () => {
  const [editathons, setEditathons] = useState<Editathon[]>([]);
  const [selectedCode, setSelectedCode] = useState('');
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'participants' | 'management'>('management');
  const [allEditathons, setAllEditathons] = useState<any[]>([]);
  const [mgmtLoading, setMgmtLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Parallel requests for faster loading
        const [authRes, edRes] = await Promise.all([
          axios.get('/api/admin/check-auth'),
          axios.get('/api/editathons')
        ]);
        setEditathons(edRes.data.editathons);
      } catch (err) {
        navigate('/admin');
      }
    };
    checkAuth();
  }, [navigate]);

  useEffect(() => {
    if (activeTab === 'management') {
      loadAllEditathons();
    }
  }, [activeTab]);

  const loadAllEditathons = async () => {
    setMgmtLoading(true);
    try {
      const res = await axios.get('/api/admin/editathons/all');
      setAllEditathons(res.data.editathons);
    } catch {
      setError('এডিটাথন তালিকা লোড করতে সমস্যা হয়েছে।');
    } finally {
      setMgmtLoading(false);
    }
  };

  const toggleTracking = async (code: string, currentStatus: boolean) => {
    const newStatus = !currentStatus;
    
    // 1. Instant UI update (Optimistic)
    setAllEditathons(prev => prev.map(e => e.code === code ? { ...e, isEnabled: newStatus } : e));
    if (newStatus) {
      const target = allEditathons.find(e => e.code === code);
      if (target) {
        setEditathons(prev => [...prev, { ...target, isEnabled: true }].sort((a, b) => a.name.localeCompare(b.name)));
      }
    } else {
      setEditathons(prev => prev.filter(e => e.code !== code));
    }

    // 2. Background API call
    try {
      await axios.post('/api/admin/editathons/toggle', { code, isEnabled: newStatus });
    } catch (err) {
      // 3. Revert on failure
      alert('অ্যাকশনটি সফল হয়নি। স্টেট রিসেট করা হচ্ছে।');
      setAllEditathons(prev => prev.map(e => e.code === code ? { ...e, isEnabled: currentStatus } : e));
      const res = await axios.get('/api/editathons'); // Full refresh to be safe
      setEditathons(res.data.editathons);
    }
  };

  const fetchParticipants = async (code: string) => {
    if (!code) return;
    setLoading(true);
    setError('');
    try {
      const res = await axios.get(`/api/admin/participants/${code}`);
      setParticipants(res.data.participants);
    } catch (err: any) {
      setError('অংশগ্রহণকারীদের তথ্য পেতে সমস্যা হয়েছে।');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectEditathon = (code: string) => {
    setSelectedCode(code);
    fetchParticipants(code);
  };

  const handleBanAction = async (participant: string, isBanned: boolean) => {
    setActionLoading(participant);
    try {
      const endpoint = isBanned ? '/api/admin/unban' : '/api/admin/ban';
      await axios.post(endpoint, { code: selectedCode, username: participant });
      setParticipants(prev => prev.map(p => 
        p.username === participant ? { ...p, isBanned: !isBanned } : p
      ));
    } catch (err: any) {
      alert('অ্যাকশনটি সফল হয়নি।');
    } finally {
      setActionLoading(null);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post('/api/admin/logout');
      navigate('/admin');
    } catch (err) {
      navigate('/admin');
    }
  };

  const filteredParticipants = participants.filter(p => 
    p.username.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="admin-panel">
      <div className="admin-header">
        <div className="title">
          <Shield size={24} color="var(--primary)" />
          <h2>অ্যাডমিন ড্যাশবোর্ড</h2>
        </div>
        <div className="header-actions" style={{ display: 'flex', gap: '10px' }}>
          <button className="btn ghost outline" onClick={() => navigate('/')}>
            <Home size={16} /> হোম
          </button>
          <button className="btn secondary outline" onClick={handleLogout}>
            <LogOut size={16} /> লগআউট
          </button>
        </div>
      </div>

      <div className="admin-tabs card" style={{ padding: '4px', marginBottom: '24px', display: 'flex', gap: '4px' }}>
        <button 
          className={`btn ${activeTab === 'management' ? 'primary' : 'ghost'}`} 
          style={{ flex: 1 }}
          onClick={() => setActiveTab('management')}
        >
          <ListTodo size={16} /> এডিটাথন ম্যানেজমেন্ট
        </button>
        <button 
          className={`btn ${activeTab === 'participants' ? 'primary' : 'ghost'}`} 
          style={{ flex: 1 }}
          onClick={() => setActiveTab('participants')}
        >
          <Search size={16} /> অংশগ্রহণকারী ম্যানেজমেন্ট
        </button>
      </div>

      {activeTab === 'participants' && (
        <>
          <div className="admin-controls card">
            <div className="selector-group">
              <label>এডিটাথন নির্বাচন করুন</label>
              <div className="custom-select-wrapper">
                <ListTodo size={18} className="select-icon" />
                <select 
                  value={selectedCode} 
                  onChange={(e) => handleSelectEditathon(e.target.value)}
                  className="admin-select"
                >
                  <option value="">এডিটাথন নির্বাচন করুন...</option>
                  {editathons.map(ed => (
                    <option key={ed.code} value={ed.code}>{ed.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="search-group">
              <label>অংশগ্রহণকারী খুঁজুন</label>
              <div className="search-input-wrapper">
                <Search size={18} className="search-icon" />
                <input 
                  type="text" 
                  placeholder="ইউজারনেম দিয়ে খুঁজুন..." 
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  disabled={!selectedCode}
                />
                {searchTerm && (
                  <button className="clear-search" onClick={() => setSearchTerm('')}>
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {error && <div className="error-box"><AlertCircle size={18} /> {error}</div>}

          {!selectedCode ? (
            <div className="card empty-state-card">
              <div className="empty-state">
                <div className="empty-icon-circle">
                  <ListTodo size={32} />
                </div>
                <h3>এডিটাথন নির্বাচন করা হয়নি</h3>
                <p>অংশগ্রহণকারী তালিকা দেখতে প্রথমে উপর থেকে একটি এডিটাথন নির্বাচন করুন।</p>
              </div>
            </div>
          ) : (
            <div className="card participants-card">
              <div className="card-header" style={{ borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Shield size={18} color="var(--primary)" />
                  <h3 style={{ margin: 0 }}>অংশগ্রহণকারী তালিকা</h3>
                  <span className="count-badge">{filteredParticipants.length} জন</span>
                </div>
                {searchTerm && (
                  <div className="filter-info">
                    ফিল্টার করা হয়েছে: <strong>{searchTerm}</strong>
                  </div>
                )}
              </div>
              <div className="table-wrap">
                {loading ? (
                  <div className="loading-state">
                    <Loader2 className="spin" size={32} />
                    <p>অংশগ্রহণকারী লোড হচ্ছে...</p>
                  </div>
                ) : (
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>ব্যবহারকারী নাম</th>
                        <th>অবস্থা</th>
                        <th style={{ textAlign: 'right' }}>অ্যাকশন</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredParticipants.map(p => (
                        <tr key={p.username} className={p.isBanned ? 'banned-row' : ''}>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                              <div className="user-avatar-mini">
                                {p.username.charAt(0).toUpperCase()}
                              </div>
                              <span style={{ fontWeight: 600 }}>{p.username}</span>
                            </div>
                          </td>
                          <td>
                            {p.isBanned ? (
                              <div className="status-indicator danger">
                                <span className="dot"></span>
                                নিষিদ্ধ
                              </div>
                            ) : (
                              <div className="status-indicator success">
                                <span className="dot"></span>
                                সক্রিয়
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button 
                              className={`btn btn-sm ${p.isBanned ? 'success outline' : 'danger outline'}`}
                              onClick={() => handleBanAction(p.username, p.isBanned)}
                              disabled={actionLoading === p.username}
                              style={{ minWidth: '100px', justifyContent: 'center' }}
                            >
                              {actionLoading === p.username ? (
                                <Loader2 className="spin" size={14} />
                              ) : p.isBanned ? (
                                <><UserCheck size={14} /> আনব্যান</>
                              ) : (
                                <><UserMinus size={14} /> ব্যান</>
                              )}
                            </button>
                          </td>
                        </tr>
                      ))}
                      {filteredParticipants.length === 0 && (
                        <tr>
                          <td colSpan={3} style={{ textAlign: 'center', padding: '60px' }}>
                            <div className="no-results">
                              <Search size={32} style={{ marginBottom: '12px', opacity: 0.3 }} />
                              <p>কোনো অংশগ্রহণকারী পাওয়া যায়নি।</p>
                              {searchTerm && <button className="btn ghost btn-sm" onClick={() => setSearchTerm('')} style={{ marginTop: '10px' }}>সার্চ ক্লিয়ার করুন</button>}
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'management' && (
        <div className="card management-card">
          <div className="card-header">
            <h3>এডিটাথন ম্যানেজমেন্ট</h3>
            <p className="small-text">এখানে যে এডিটাথনগুলো অ্যালাউ করবেন শুধু সেগুলোই ট্র্যাকিং লিস্টে দেখাবে।</p>
          </div>
          <div className="table-wrap">
            {mgmtLoading ? (
              <div className="loading-state">
                <Loader2 className="spin" size={32} />
                <p>সব এডিটাথন লোড হচ্ছে...</p>
              </div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>নাম</th>
                    <th>কোড</th>
                    <th style={{ textAlign: 'right' }}>ট্র্যাকিং স্ট্যাটাস</th>
                  </tr>
                </thead>
                <tbody>
                  {allEditathons.map(ed => (
                    <tr key={ed.code}>
                      <td>{ed.name}</td>
                      <td><code>{ed.code}</code></td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '12px' }}>
                          <span className={`status-badge ${ed.isEnabled ? 'success' : 'danger'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                            {ed.isEnabled ? 'ট্র্যাকিং চলছে' : 'ট্র্যাকিং বন্ধ'}
                          </span>
                          <button 
                            className={`switch-toggle ${ed.isEnabled ? 'on' : 'off'}`}
                            onClick={() => toggleTracking(ed.code, ed.isEnabled)}
                            title={ed.isEnabled ? 'ট্র্যাকিং বন্ধ করুন' : 'ট্র্যাকিং চালু করুন'}
                          >
                            <div className="switch-handle"></div>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      <style>{`
        .admin-panel {
          max-width: 1000px;
          margin: 0 auto;
          padding: 10px;
          padding-bottom: 40px;
        }
        .admin-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }
        .admin-header .title {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .admin-tabs {
          display: flex;
          gap: 4px;
          padding: 4px;
          margin-bottom: 24px;
        }
        .admin-controls {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-bottom: 24px;
          padding: 20px;
        }
        @media (max-width: 600px) {
          .admin-controls { grid-template-columns: 1fr; }
        }
        .selector-group, .search-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .selector-group label, .search-group label {
          font-weight: 500;
          font-size: 14px;
        }
        .admin-select {
          padding: 10px;
          border: 1px solid var(--border);
          border-radius: 6px;
          background: var(--card);
          color: var(--text);
          font-size: 15px;
        }
        .search-input-wrapper {
          position: relative;
          display: flex;
          align-items: center;
        }
        .search-input-wrapper svg {
          position: absolute;
          left: 12px;
          color: var(--muted);
        }
        .search-input-wrapper input {
          width: 100%;
          padding: 10px 10px 10px 40px;
          border: 1px solid var(--border);
          border-radius: 6px;
          background: var(--card);
          color: var(--text);
          font-size: 15px;
        }
        .table-wrap {
          width: 100%;
          overflow-x: auto;
          -webkit-overflow-scrolling: touch;
          border-radius: 8px;
        }
        .admin-table {
          width: 100%;
          min-width: 600px;
          border-collapse: collapse;
        }
        .admin-table th {
          background: var(--glass);
        }
        .card {
          overflow: hidden;
          margin-bottom: 20px;
        }
        .banned-row {
          background: var(--banned-bg);
          color: var(--banned-text);
        }
        .loading-state {
          padding: 60px;
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          color: var(--muted);
        }
        .spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .ghost {
          background: transparent;
          color: var(--text);
        }
        .ghost:hover {
          background: var(--glass);
        }
        .switch-toggle {
          flex-shrink: 0;
          width: 60px;
          height: 30px;
          border-radius: 15px;
          border: none;
          position: relative;
          cursor: pointer;
          transition: all 0.3s ease;
          padding: 0;
          display: flex;
          align-items: center;
          box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
        }
        .switch-toggle.on {
          background-color: #22c55e;
        }
        .switch-toggle.off {
          background-color: #ef4444;
        }
        .switch-handle {
          width: 24px;
          height: 24px;
          background-color: white;
          border-radius: 50%;
          position: absolute;
          left: 3px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .switch-toggle.on .switch-handle {
          left: 33px;
        }
        .custom-select-wrapper {
          position: relative;
          display: flex;
          align-items: center;
        }
        .select-icon {
          position: absolute;
          left: 12px;
          color: var(--muted);
          pointer-events: none;
        }
        .admin-select {
          width: 100%;
          padding-left: 40px;
        }
        .clear-search {
          position: absolute;
          right: 10px;
          background: var(--glass);
          border: 1px solid var(--border);
          border-radius: 4px;
          color: var(--muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 4px;
          transition: all 0.2s;
        }
        .clear-search:hover {
          color: var(--text);
          background: var(--btn-hover);
        }
        .empty-state {
          padding: 60px 20px;
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }
        .empty-icon-circle {
          width: 80px;
          height: 80px;
          background: var(--glass);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--muted);
          margin-bottom: 8px;
        }
        .empty-state h3 {
          margin: 0;
          font-size: 20px;
        }
        .empty-state p {
          color: var(--muted);
          max-width: 300px;
          margin: 0;
        }
        .count-badge {
          background: var(--glass);
          border: 1px solid var(--border);
          padding: 2px 10px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 700;
          color: var(--primary);
        }
        .filter-info {
          font-size: 13px;
          color: var(--muted);
        }
        .user-avatar-mini {
          width: 30px;
          height: 30px;
          background: var(--primary);
          color: white;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 14px;
          flex-shrink: 0;
        }
        .status-indicator {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          font-weight: 600;
        }
        .status-indicator.success { color: var(--success); }
        .status-indicator.danger { color: var(--danger); }
        .status-indicator .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .status-indicator.success .dot { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-indicator.danger .dot { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
        .no-results {
          display: flex;
          flex-direction: column;
          align-items: center;
          color: var(--muted);
        }
      `}</style>
    </div>
  );
};
