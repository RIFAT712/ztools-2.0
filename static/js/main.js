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
    const select = document.getElementById("editathon-select");

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
            ui.errorEl.textContent = 'দয়া করে একটি ইভেন্ট নির্বাচন করুন।';
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
            const resp = await fetch("/editathons");
            if (!resp.ok) throw new Error("Network response was not ok");

            const data = await resp.json();

            // Clear existing options except the first placeholder
            select.innerHTML = '<option value="">ইভেন্ট নির্বাচন করুন</option>';

            data.editathons.forEach(e => {
                const option = document.createElement("option");
                option.value = e.code;
                option.textContent = e.name;
                select.appendChild(option);
            });
        } catch (err) {
            console.error("Failed to load editathons:", err);
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'এডিটথন তালিকা লোড করতে ব্যর্থ হয়েছে।';
        }
    }

    // --- Event Listeners ---

    // Update the variable whenever the dropdown changes
    select.addEventListener('change', (e) => {
        activeFountainCode = e.target.value;
        ui.errorEl.classList.add('hidden');
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