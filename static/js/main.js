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
    const dropdownTrigger = document.getElementById("dropdown-trigger");
    const dropdownList = document.getElementById("dropdown-list");
    const selectedCodeInput = document.getElementById("selected-editathon-code");

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
        const code = selectedCodeInput.value.trim();

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
            dropdownTrigger.disabled = true;
            dropdownTrigger.textContent = "এডিটাথন লোড হচ্ছে...";
            const resp = await fetch("/editathons");
            if (!resp.ok) throw new Error("Network response was not ok");

            const data = await resp.json();
            allEditathons = data.editathons;
            
            // Populate list
            renderDropdownItems();
            
            dropdownTrigger.textContent = "একটি এডিটাথন নির্বাচন করুন";
            dropdownTrigger.disabled = false;
        } catch (err) {
            console.error("Failed to load editathons:", err);
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'এডিটাথন তালিকা লোড করতে ব্যর্থ হয়েছে।';
        }
    }

    function renderDropdownItems() {
        dropdownList.innerHTML = allEditathons.map(e => `
            <div class="dropdown-item" data-code="${e.code}">
                ${e.name}
            </div>
        `).join('');
    }

    // --- Event Listeners ---

    // Generic Dropdown Toggle
    document.addEventListener('click', (e) => {
        const trigger = e.target.closest('.dropdown-trigger');
        const item = e.target.closest('.dropdown-item');
        const container = e.target.closest('.custom-dropdown');
        
        // Close all dropdowns except the one being toggled
        document.querySelectorAll('.dropdown-list').forEach(list => {
            if (!container || list !== container.querySelector('.dropdown-list') || item) {
                list.classList.add('hidden');
            }
        });

        if (trigger && container && !item) {
            const list = container.querySelector('.dropdown-list');
            if (list) list.classList.toggle('hidden');
        }
    });

    dropdownList.addEventListener('click', (e) => {
        const item = e.target.closest('.dropdown-item');
        if (item) {
            const code = item.dataset.code;
            const name = item.textContent.trim();
            
            selectedCodeInput.value = code;
            dropdownTrigger.textContent = name;
            
            ui.errorEl.classList.add('hidden');
            
            // Highlight selected item
            dropdownList.querySelectorAll('.dropdown-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');
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