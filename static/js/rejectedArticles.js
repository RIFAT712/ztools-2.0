import { formatBn, escapeHtml } from './utils.js';

export async function loadRejectedArticles(code, endpoints, ui) {
    try {
        ui.errorEl.classList.add('hidden');
        ui.progressWrap.style.display = 'block';
        ui.progressBar.style.width = '0%';
        const resp = await fetch(endpoints.fountainEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        ui.progressWrap.style.display = 'none';
        if (data.error) {
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = data.error;
            return;
        }

        const rejectedArticles = [];
        for (const articles of Object.values(data.articles)) {
            articles.forEach(a => {
                if (a.status === "গৃহীত হয়নি") rejectedArticles.push(a.name);
            });
        }

        if (rejectedArticles.length === 0) {
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'কোনো গৃহীত হয়নি নিবন্ধ পাওয়া যায়নি।';
            return;
        }

        // --- Create table ---
        const table = document.createElement('table');
        table.style.width = '100%';
        table.style.borderCollapse = 'collapse';
        table.innerHTML = `
            <thead>
                <tr>
                    <th style="border:1px solid #ccc;padding:5px;width:10%;">ক্রমিক</th>
                    <th style="border:1px solid #ccc;padding:5px;">নিবন্ধের নাম</th>
                </tr>
            </thead>
            <tbody>
                ${rejectedArticles.map((name, index) => `
                    <tr>
                        <td style="border:1px solid #ccc;padding:5px;text-align:center;">${formatBn(index + 1)}</td>
                        <td style="border:1px solid #ccc;padding:5px;">${escapeHtml(name)}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;

        ui.tableWrap.innerHTML = '';
        ui.tableWrap.appendChild(table);
        ui.resultCard.classList.remove('hidden');
        ui.summaryEl.textContent = `মোট গৃহীত হয়নি নিবন্ধ: ${formatBn(rejectedArticles.length)}`;

        // --- Create or reuse toolbar at the top ---
        let toolbar = ui.resultCard.querySelector('.copy-toolbar');
        if (!toolbar) {
            toolbar = document.createElement('div');
            toolbar.className = 'copy-toolbar';
            toolbar.style.marginBottom = '0.5em';
            ui.resultCard.insertBefore(toolbar, ui.resultCard.firstChild);
        } else {
            toolbar.innerHTML = ''; // clear previous buttons
        }

        // --- Create dynamic copy button ---
        const copyBtn = document.createElement('button');
        copyBtn.textContent = 'কপি করুন';
        copyBtn.className = 'copy-btn';
        toolbar.appendChild(copyBtn);

        copyBtn.onclick = () => {
            let wikiTable = `{| class="wikitable"\n! ক্রমিক !! নিবন্ধের নাম\n`;
            rejectedArticles.forEach((name, index) => {
                wikiTable += `|-\n| ${formatBn(index + 1)} || ${escapeHtml(name)}\n`;
            });
            wikiTable += `|}`;

            navigator.clipboard.writeText(wikiTable).then(() => {
                const originalText = copyBtn.textContent;
                copyBtn.textContent = '✓ কপি হয়েছে';
                setTimeout(() => copyBtn.textContent = originalText, 2000);
            }).catch(console.error);
        };

    } catch (err) {
        ui.progressWrap.style.display = 'none';
        ui.errorEl.classList.remove('hidden');
        ui.errorEl.textContent = 'সার্ভার থেকে তথ্য আনতে সমস্যা হয়েছে।';
        console.error(err);
    }
}
