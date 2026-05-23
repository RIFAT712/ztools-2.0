import React, { useState, useEffect, useRef } from 'react';

interface Editathon {
  code: string;
  name: string;
}

interface Props {
  editathons: Editathon[];
  loading: boolean;
  onSelect: (code: string) => void;
  selected?: string;
}

export const EditathonSelector: React.FC<Props> = ({ editathons, loading, onSelect, selected }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedName, setSelectedName] = useState('একটি এডিটাথন নির্বাচন করুন');
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selected && editathons.length > 0) {
      const found = editathons.find(e => e.code === selected);
      if (found) setSelectedName(found.name);
    }
  }, [selected, editathons]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (code: string, name: string) => {
    setSelectedName(name);
    onSelect(code);
    setIsOpen(false);
  };

  return (
    <div className="controls">
      <label className="input-label">একটি এডিটাথন নির্বাচন করুন:</label>
      <div className="custom-dropdown" ref={dropdownRef}>
        <button 
          className="dropdown-trigger" 
          onClick={() => !loading && setIsOpen(!isOpen)} 
          disabled={loading}
        >
          {loading ? 'এডিটাথন লোড হচ্ছে...' : selectedName}
        </button>
        {isOpen && (
          <div className="dropdown-list">
            {editathons.map((e) => (
              <div 
                key={e.code} 
                className="dropdown-item" 
                onClick={() => handleSelect(e.code, e.name)}
              >
                {e.name}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
