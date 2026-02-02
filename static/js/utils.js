// Utility functions for Bengali text processing and formatting
const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
export const toBn = n => String(n).replace(/\d/g, d => BN_DIGITS[d]);

export const formatBn = n => {
    try {
        return Number(n).toLocaleString('bn-BD');
    } catch {
        return toBn(n);
    }
};

const ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const escapeHtml = s => String(s || '').replace(/[&<>"']/g, c => ESCAPE_MAP[c]);
