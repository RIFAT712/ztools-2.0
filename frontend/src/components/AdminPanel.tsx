import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Shield, UserMinus, UserCheck, Search, LogOut, AlertCircle, Loader2, ListTodo } from 'lucide-react';

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
        await axios.get('/api/admin/check-auth');
        const edRes = await axios.get('/api/editathons');
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
    setActionLoading(code);
    try {
      await axios.post('/api/admin/editathons/toggle', { code, isEnabled: !currentStatus });
      setAllEditathons(prev => prev.map(e => e.code === code ? { ...e, isEnabled: !currentStatus } : e));
      // Refresh active list
      const edRes = await axios.get('/api/editathons');
      setEditathons(edRes.data.editathons);
    } catch {
      alert('অ্যাকশনটি সফল হয়নি।');
    } finally {
      setActionLoading(null);
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
        <button className="btn secondary outline" onClick={handleLogout}>
          <LogOut size={16} /> লগআউট
        </button>
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
              <select 
                value={selectedCode} 
                onChange={(e) => handleSelectEditathon(e.target.value)}
                className="admin-select"
              >
                <option value="">নির্বাচন করুন...</option>
                {editathons.map(ed => (
                  <option key={ed.code} value={ed.code}>{ed.name}</option>
                ))}
              </select>
            </div>

            {selectedCode && (
              <div className="search-group">
                <label>অংশগ্রহণকারী খুঁজুন</label>
                <div className="search-input-wrapper">
                  <Search size={18} />
                  <input 
                    type="text" 
                    placeholder="ইউজারনেম..." 
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          {error && <div className="error-box"><AlertCircle size={18} /> {error}</div>}

          {selectedCode && (
            <div className="card participants-card">
              <div className="card-header">
                <h3>অংশগ্রহণকারী তালিকা ({participants.length})</h3>
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
                          <td>{p.username}</td>
                          <td>
                            {p.isBanned ? (
                              <span className="status-badge danger">নিষিদ্ধ ব্যবহারকারী</span>
                            ) : (
                              <span className="status-badge success">সক্রিয়</span>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button 
                              className={`btn btn-sm ${p.isBanned ? 'success outline' : 'danger outline'}`}
                              onClick={() => handleBanAction(p.username, p.isBanned)}
                              disabled={actionLoading === p.username}
                            >
                              {actionLoading === p.username ? (
                                <Loader2 className="spin" size={14} />
                              ) : p.isBanned ? (
                                <><UserCheck size={14} /> আনব্যান</>
                              ) : (
                                <><UserMinus size={14} /> ব্যান করুন</>
                              )}
                            </button>
                          </td>
                        </tr>
                      ))}
                      {filteredParticipants.length === 0 && (
                        <tr>
                          <td colSpan={3} style={{ textAlign: 'center', padding: '40px' }}>
                            কোনো অংশগ্রহণকারী পাওয়া যায়নি।
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
                            disabled={actionLoading === ed.code}
                            title={ed.isEnabled ? 'ট্র্যাকিং বন্ধ করুন' : 'ট্র্যাকিং চালু করুন'}
                          >
                            <div className="switch-handle">
                              {actionLoading === ed.code && <Loader2 className="spin" size={12} />}
                            </div>
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
        /* ... previous styles ... */
        .switch-toggle {
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
          background-color: #22c55e; /* Green */
        }
        .switch-toggle.off {
          background-color: #ef4444; /* Red */
        }
        .switch-toggle:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .switch-handle {
          width: 24px;
          height: 24px;
          background-color: white;
          border-radius: 50%;
          position: absolute;
          left: 3px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .switch-toggle.on .switch-handle {
          left: 33px;
        }
        .admin-panel {
          max-width: 900px;
          margin: 0 auto;
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
        .admin-table th {
          background: var(--glass);
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
      `}</style>
    </div>
  );
};
