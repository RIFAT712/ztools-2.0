export const toBengaliDigits = (num: number | string, useGrouping = true): string => {
  if (num === undefined || num === null) return '';
  const n = typeof num === 'string' ? parseFloat(num) : num;
  if (isNaN(n)) return num.toString();
  
  // Format with grouping if requested
  const formatted = useGrouping 
    ? n.toLocaleString('en-IN') 
    : n.toString();
  
  // Convert digits to Bengali
  const bengaliDigits = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];
  return formatted.replace(/\d/g, (digit) => bengaliDigits[parseInt(digit)]);
};
