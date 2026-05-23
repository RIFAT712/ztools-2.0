import React from 'react';

interface Props {
  visible: boolean;
  progress: number;
}

export const ProgressBar: React.FC<Props> = ({ visible, progress }) => {
  if (!visible) return null;

  return (
    <div className="progress-wrap" style={{ display: 'block' }}>
      <div 
        className="progress loading-animation" 
        style={{ width: `${progress}%` }}
      ></div>
    </div>
  );
};
