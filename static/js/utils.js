// Utility functions for Bengali text processing and formatting
export const toBn = n => String(n).replace(/\d/g, d => "০১২৩৪৫৬৭৮৯"[d]);
export const formatBn = n => { try { return Number(n).toLocaleString('bn-BD'); } catch { return toBn(n); } };
export const escapeHtml = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
