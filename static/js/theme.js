// Theme toggle functionality
// toggles between light and dark modes and saves preference in localStorage
export function initThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    const userPref = localStorage.getItem('theme');

    if(userPref === 'light') document.body.classList.add('light');
    updateToggleText();

    themeToggle.onclick = () => {
        document.body.classList.toggle('light');
        localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
        updateToggleText();
    };

    function updateToggleText() {
        themeToggle.textContent = document.body.classList.contains('light') ? '🌙' : '☀️';
    }
}
