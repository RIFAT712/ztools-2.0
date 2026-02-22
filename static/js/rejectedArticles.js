import { formatBn, escapeHtml } from './utils.js';

function handleRejectedDownload(type, articles, wikitable) {
    if (type === 'csv') {
        let csv = 'Article Name\n';
        articles.forEach(name => {
            csv += `"${name}"\n`;
        });
        downloadFile(csv, 'ztools_rejected_articles.csv', 'text/csv');
    } else if (type === 'json') {
        const json = JSON.stringify(articles, null, 2);
        downloadFile(json, 'ztools_rejected_articles.json', 'application/json');
    } else if (type === 'wikitable') {
        navigator.clipboard.writeText(wikitable).then(() => {
            alert('উইকিটেবিল ক্লিপবোর্ডে কপি করা হয়েছে!');
        });
    }
}

function downloadFile(content, fileName, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
}

export async function loadRejectedArticles(code, endpoints, ui) {
    const { countBtn, juryBtn, progressWrap, progressBar, resultCard, tableWrap, summaryEl, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    errorEl.classList.add('hidden');
    progressWrap.style.display = 'block';
    progressBar.style.width = '100%';
    progressBar.classList.add('loading-animation');

    try {
        const resp = await fetch('/rejected_articles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        progressWrap.style.display = 'none';

        if (data.error) throw new Error(data.error);

        const rejectedArticles = data.rejected_articles || [];
        const wikitable = data.wikitable || "";

        if (rejectedArticles.length === 0) {
            errorEl.classList.remove('hidden');
            errorEl.textContent = 'কোনো গৃহীত হয়নি নিবন্ধ পাওয়া যায়নি।';
            resultCard.classList.add('hidden');
            return;
        }

        resultCard.classList.remove('hidden');
        summaryEl.textContent = `মোট গৃহীত হয়নি নিবন্ধ: ${formatBn(rejectedArticles.length)}`;

        // Hook up download dropdown
        const downloadDropdown = resultCard.querySelector('#download-dropdown-container');
        if (downloadDropdown) {
            downloadDropdown.querySelectorAll('.dropdown-item').forEach(item => {
                item.onclick = (e) => {
                    e.stopPropagation();
                    handleRejectedDownload(item.dataset.type, rejectedArticles, wikitable);
                    downloadDropdown.querySelector('.dropdown-list').classList.add('hidden');
                };
            });
        }

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
        progressBar.classList.remove('loading-animation');
    }
}