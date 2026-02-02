import { formatBn, escapeHtml } from './utils.js';

export async function loadRejectedArticles(code, endpoints, ui) {
    const { countBtn, juryBtn, progressWrap, progressBar, resultCard, tableWrap, summaryEl, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    errorEl.classList.add('hidden');
    progressWrap.style.display = 'block';
    progressBar.style.width = '0%';

    try {
        const resp = await fetch(endpoints.fountainEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        progressWrap.style.display = 'none';

        if (data.error) throw new Error(data.error);

        const rejectedArticles = [];
        Object.values(data.articles || {}).forEach(userArticles => {
            userArticles.forEach(a => {
                if (a.status === "গৃহীত হয়নি") rejectedArticles.push(a.name);
            });
        });

        if (rejectedArticles.length === 0) {
            errorEl.classList.remove('hidden');
            errorEl.textContent = 'কোনো গৃহীত হয়নি নিবন্ধ পাওয়া যায়নি।';
            resultCard.classList.add('hidden');
            return;
        }

        resultCard.classList.remove('hidden');
        summaryEl.textContent = `মোট গৃহীত হয়নি নিবন্ধ: ${formatBn(rejectedArticles.length)}`;

        // Refresh toolbar
        let toolbar = resultCard.querySelector('.copy-toolbar');
        if (toolbar) toolbar.remove();
        toolbar = document.createElement('div');
        toolbar.className = 'copy-toolbar';
        toolbar.style.marginBottom = '0.5em';
        resultCard.prepend(toolbar);

        const copyBtn = document.createElement('button');
        copyBtn.textContent = 'কপি করুন';
        copyBtn.className = 'copy-btn';
        toolbar.appendChild(copyBtn);

        copyBtn.onclick = () => {
            let wikiTable = `{| class="wikitable sortable"
! ক্রমিক !! নিবন্ধের নাম
`;
            rejectedArticles.forEach((name, index) => {
                wikiTable += `|-
| ${formatBn(index + 1)} || ${name}
`;
            });
            wikiTable += `|}`;

            navigator.clipboard.writeText(wikiTable).then(() => {
                copyBtn.textContent = '✓ কপি হয়েছে';
                setTimeout(() => copyBtn.textContent = 'কপি করুন', 2000);
            });
        };

        // Render Table
        let html = '<table><thead><tr><th style="width:10%;">ক্রমিক</th><th class="left">নিবন্ধের নাম</th></tr></thead><tbody>';
        rejectedArticles.forEach((name, index) => {
            html += `<tr><td>${formatBn(index + 1)}</td><td class="left">${escapeHtml(name)}</td></tr>`;
        });
        html += '</tbody></table>';
        tableWrap.innerHTML = html;

    } catch (err) {
        progressWrap.style.display = 'none';
        errorEl.classList.remove('hidden');
        errorEl.textContent = 'সার্ভার থেকে তথ্য আনতে সমস্যা হয়েছে: ' + err.message;
        resultCard.classList.add('hidden');
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
    }
}