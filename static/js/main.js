// manages main app logic, event listeners, and UI interactions
import { initThemeToggle } from './theme.js';
import { loadArticleWordCounts } from './wordCount.js';
import { loadJuryStats } from './juryStats.js';

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();

    const fountainInput = document.getElementById('fountainCode');
    const countBtn = document.getElementById('countBtn');
    const juryBtn  = document.getElementById('juryBtn');

    const ui = {
        countBtn, juryBtn,
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

    // --- Word Count Button ---
    countBtn.addEventListener('click', () => {
        const code = fountainInput.value.trim();
        if(!code){
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'দয়া করে ফাউন্টেন কোড লিখুন।';
            return;
        }

        // hide both cards before loading
        ui.resultCard.classList.add('hidden');
        ui.juryCard.classList.add('hidden');

        loadArticleWordCounts(code, endpoints, ui);
    });

    // --- Jury Stats Button ---
    juryBtn.addEventListener('click', () => {
        const code = fountainInput.value.trim();
        if(!code){
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'দয়া করে ফাউন্টেন কোড লিখুন।';
            return;
        }

        // hide both cards before loading
        ui.resultCard.classList.add('hidden');
        ui.juryCard.classList.add('hidden');

        loadJuryStats(code, endpoints, ui);
    });
});
