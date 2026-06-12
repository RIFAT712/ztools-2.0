import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Shield, UserMinus, UserCheck, Search, LogOut, AlertCircle, Loader2 } from 'lucide-react';

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

      <style>{`
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
      `}</style>
    </div>
  );
};
