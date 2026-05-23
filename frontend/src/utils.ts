export const toBengaliDigits = (num: number | string): string => {
  if (num === undefined || num === null) return '';
  const n = typeof num === 'string' ? parseFloat(num) : num;
  if (isNaN(n)) return num.toString();
  
  // Format with South Asian grouping (2,2,3) using en-IN
  const formatted = n.toLocaleString('en-IN');
  
  // Convert digits to Bengali
  const bengaliDigits = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];
  return formatted.replace(/\d/g, (digit) => bengaliDigits[parseInt(digit)]);
};
