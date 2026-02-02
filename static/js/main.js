import { initThemeToggle } from './theme.js';
import { loadArticleWordCounts } from './wordCount.js';
import { loadJuryStats } from './juryStats.js';
import { loadRejectedArticles } from './rejectedArticles.js';

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();

    // Variable to store the selected Fountain code
    let activeFountainCode = "";

    const countBtn = document.getElementById('countBtn');
    const juryBtn = document.getElementById('juryBtn');
    const rejectedBtn = document.getElementById('rejectedBtn');
    const searchInput = document.getElementById("editathon-search");
    const suggestionList = document.getElementById("suggestion-list");

    let allEditathons = [];

    const ui = {
        countBtn,
        juryBtn,
        rejectedBtn,
        progressWrap: document.getElementById('progressWrap'),
        progressBar: document.getElementById('progressBar'),
        resultCard: document.getElementById('resultCard'),
        tableWrap: document.getElementById('tableWrap'),
        summaryEl: document.getElementById('summary'),
        copyWikiBtn: document.getElementById('copyWikiBtn'),
        juryCard: document.getElementById('juryCard'),
        juryParsedWrap: document.getElementById('juryParsedWrap'),
        copyJuryBtn: document.getElementById('copyJuryBtn'),
        errorEl: document.getElementById('error')
    };

    const endpoints = {
        fountainEndpoint: '/fetch_articles',
        juryEndpoint: '/jury_stats'
    };

    /**
     * Helper to validate selection and clear UI before running a task
     */
    function executeAction(actionFunc) {
        const code = activeFountainCode.trim();

        if (!code) {
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'দয়া করে একটি এডিটাথন নির্বাচন করুন।';
            return;
        }

        // Reset UI state
        ui.errorEl.classList.add('hidden');
        ui.resultCard.classList.add('hidden');
        ui.juryCard.classList.add('hidden');

        // Execute the specific module function
        actionFunc(code, endpoints, ui);
    }

    async function loadEditathons() {
        try {
            searchInput.disabled = true;
            searchInput.placeholder = "এডিটাথন লোড হচ্ছে...";
            const resp = await fetch("/editathons");
            if (!resp.ok) throw new Error("Network response was not ok");

            const data = await resp.json();
            allEditathons = data.editathons;
            searchInput.disabled = false;
            searchInput.placeholder = "এডিটাথন খুঁজুন...";
        } catch (err) {
            console.error("Failed to load editathons:", err);
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'এডিটাথন তালিকা লোড করতে ব্যর্থ হয়েছে।';
        }
    }

    function renderSuggestions(filter = "") {
        const filtered = allEditathons.filter(e =>
            e.name.toLowerCase().includes(filter.toLowerCase()) ||
            e.code.toLowerCase().includes(filter.toLowerCase())
        );

        if (filtered.length === 0) {
            suggestionList.classList.add('hidden');
            return;
        }

        suggestionList.innerHTML = filtered.map(e => `
            <div class="suggestion-item ${e.code === activeFountainCode ? 'active' : ''}" data-code="${e.code}">
                ${e.name}
            </div>
        `).join('');
        suggestionList.classList.remove('hidden');
    }

    // --- Event Listeners ---

    searchInput.addEventListener('input', (e) => {
        renderSuggestions(e.target.value);
    });

    searchInput.addEventListener('focus', () => {
        renderSuggestions(searchInput.value);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            suggestionList.classList.add('hidden');
        }
    });

    suggestionList.addEventListener('click', (e) => {
        const item = e.target.closest('.suggestion-item');
        if (item) {
            activeFountainCode = item.dataset.code;
            searchInput.value = item.textContent.trim();
            suggestionList.classList.add('hidden');
            ui.errorEl.classList.add('hidden');
        }
    });

    countBtn.addEventListener('click', () => {
        executeAction(loadArticleWordCounts);
    });

    juryBtn.addEventListener('click', () => {
        executeAction(loadJuryStats);
    });

    rejectedBtn.addEventListener('click', () => {
        executeAction(loadRejectedArticles);
    });

    // Initialize the dropdown on page load
    loadEditathons();
});