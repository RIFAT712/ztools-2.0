export const toBengaliDigits = (num: number | string): string => {
  if (num === undefined || num === null) return '';
  const n = typeof num === 'string' ? parseFloat(num) : num;
  if (isNaN(n)) return num.toString();
  return n.toLocaleString('bn-BD');
};
