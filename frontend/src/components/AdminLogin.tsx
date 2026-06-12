import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Lock, User, AlertCircle, Loader2 } from 'lucide-react';

export const AdminLogin: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    try {
      await axios.post('/api/admin/login', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      navigate('/admin/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'লগইন করতে সমস্যা হয়েছে।');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="card login-card">
        <div className="card-header">
          <div className="small">অ্যাডমিন অ্যাক্সেস</div>
          <h2>লগইন</h2>
        </div>
        <form onSubmit={handleLogin} className="login-form">
          {error && (
            <div className="error-box">
              <AlertCircle size={18} /> {error}
            </div>
          )}
          <div className="input-group">
            <label className="input-label" htmlFor="username">
              <User size={14} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> ব্যবহারকারী নাম
            </label>
            <input
              id="username"
              className="mini-search-input"
              style={{ width: '100%', height: '48px', fontSize: '1rem' }}
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              placeholder="ইউজারনেম"
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="password">
              <Lock size={14} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> পাসওয়ার্ড
            </label>
            <input
              id="password"
              className="mini-search-input"
              style={{ width: '100%', height: '48px', fontSize: '1rem' }}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="পাসওয়ার্ড"
            />
          </div>
          <button type="submit" className="btn primary" style={{ marginTop: '10px' }} disabled={loading}>
            {loading ? <Loader2 className="spin" size={18} /> : 'লগইন করুন'}
          </button>
        </form>
      </div>
      <style>{`
        .login-container {
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 70vh;
        }
        .login-card {
          width: 100%;
          max-width: 420px;
          padding: 10px;
        }
        .login-form {
          display: flex;
          flex-direction: column;
          gap: 20px;
          padding: 24px;
        }
        .input-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
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
