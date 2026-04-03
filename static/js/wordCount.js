import { toBn, formatBn, escapeHtml } from './utils.js';

export async function loadArticleWordCounts(code, endpoints, ui) {
    const { countBtn, juryBtn, progressWrap, progressBar, resultCard, tableWrap, summaryEl, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    progressWrap.style.display = 'block';
    progressBar.style.width = '10%';
    progressBar.classList.add('loading-animation');
    errorEl.classList.add('hidden');

    // Local state to accumulate live updates
    let totals = {};
    let siteUrl = "";

    try {
        const resp = await fetch('/count_words', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });

        if (!resp.ok) throw new Error("Network response was not ok");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (!line.trim()) continue;
                const chunk = JSON.parse(line);

                if (chunk.error) throw new Error(chunk.error);

                if (chunk.type === "info") {
                    siteUrl = chunk.site_url;
                } else if (chunk.type === "update") {
                    updateTotals(totals, chunk.articles);
                    renderArticleTable(totals, ui);
                } else if (chunk.type === "complete") {
                    // Instant load from memory cache
                    totals = chunk.data[0];
                    siteUrl = chunk.data[1];
                    renderArticleTable(totals, ui);
                    progressBar.style.width = '100%';
                } else if (chunk.type === "done") {
                    progressBar.style.width = '100%';
                }
            }
            
            // Increment progress bar slightly per chunk if not done
            let currentWidth = parseFloat(progressBar.style.width);
            if (currentWidth < 95) {
                progressBar.style.width = (currentWidth + 1) + "%";
            }
        }

        setTimeout(() => {
            progressWrap.style.display = 'none';
        }, 500);

    } catch (e) {
        showError('ডেটা আনতে ব্যর্থ: ' + e.message);
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
        progressBar.classList.remove('loading-animation');
    }

    function updateTotals(acc, articles) {
        articles.forEach(a => {
            const user = a.user;
            if (!acc[user]) {
                acc[user] = { accepted: 0, unreviewed: 0, rejected: 0, total: 0, articles: [] };
            }
            
            const stats = acc[user];
            stats.total += a.words;
            if (a.status === "গৃহীত হয়েছে") stats.accepted += a.words;
            else if (a.status === "গৃহীত হয়নি") stats.rejected += a.words;
            else stats.unreviewed += a.words;

            stats.articles.push({
                title: a.title,
                actualTitle: a.actual_title !== a.title ? a.actual_title : "",
                status: a.status,
                words: a.words,
                isRedirect: a.is_redirect
            });
        });
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
        resultCard.classList.add('hidden');
        progressWrap.style.display = 'none';
    }
}

function handleDownload(type, rows) {
    if (type === 'csv') {
        let csv = 'User,Accepted,Unreviewed,Rejected,Total Words,Articles\n';
        rows.forEach(r => {
            csv += `"${r.user}",${r.accepted},${r.unreviewed},${r.rejected},${r.total},${r.articles.length}\n`;
        });
        downloadFile(csv, 'ztools_wordcounts.csv', 'text/csv');
    } else if (type === 'json') {
        const json = JSON.stringify(rows, null, 2);
        downloadFile(json, 'ztools_wordcounts.json', 'application/json');
    } else if (type === 'wikitable') {
        let wt = '{| class="wikitable sortable"\n! # !! ব্যবহারকারী !! গৃহীত !! অপর্যালোচিত !! বাতিল !! মোট শব্দ !! নিবন্ধ\n';
        rows.forEach((r, i) => {
            wt += `|-\n| ${i + 1} || ${r.user} || ${r.accepted} || ${r.unreviewed} || ${r.rejected} || ${r.total} || ${r.articles.length}\n`;
        });
        wt += '|}';
        navigator.clipboard.writeText(wt).then(() => {
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

// Reuse your original renderArticleTable function below...
function renderArticleTable(totals, ui) {
    const { tableWrap, summaryEl, resultCard } = ui;
    const rows = Object.entries(totals)
        .map(([user, v]) => ({ user, ...v }))
        .sort((a, b) => b.accepted - a.accepted);

    resultCard.classList.remove('hidden');

    // Hook up download dropdown items
    const downloadDropdown = resultCard.querySelector('#download-dropdown-container');
    if (downloadDropdown) {
        downloadDropdown.querySelectorAll('.dropdown-item').forEach(item => {
            item.onclick = (e) => {
                e.stopPropagation();
                handleDownload(item.dataset.type, rows);
                downloadDropdown.querySelector('.dropdown-list').classList.add('hidden');
            };
        });
    }

    let gA = 0, gU = 0, gR = 0, gT = 0, gArticles = 0;
    let html = '<table><thead><tr><th>#</th><th class="left">ব্যবহারকারী</th><th>গৃহীত</th><th>অপর্যালোচিত</th><th>বাতিল</th><th>মোট শব্দ</th><th>মোট নিবন্ধ</th></tr></thead><tbody>';

    rows.forEach((r, i) => {
        html += `<tr class="user-row" data-user="${escapeHtml(r.user)}" style="cursor:pointer;">
            <td>${formatBn(i + 1)}</td>
            <td class="left">${escapeHtml(r.user)}</td>
            <td>${formatBn(r.accepted)}</td>
            <td>${formatBn(r.unreviewed)}</td>
            <td>${formatBn(r.rejected)}</td>
            <td>${formatBn(r.total)}</td>
            <td>${formatBn(r.articles.length)}</td>
        </tr>`;

        html += `<tr class="articles-row hidden" data-user="${escapeHtml(r.user)}"><td colspan="7">
            <table class="inner-table">
                <thead><tr><th>#</th><th class="left">নিবন্ধ</th><th>শব্দ</th><th>অবস্থা</th></tr></thead>
                <tbody>`;

        r.articles.forEach((a, j) => {
            html += `<tr>
                <td>${formatBn(j + 1)}</td>
                <td class="left">${escapeHtml(a.title)} ${a.actualTitle ? `<small>(${escapeHtml(a.actualTitle)})</small>` : ''}</td>
                <td>${formatBn(a.words)}</td>
                <td>${escapeHtml(a.status)}</td>
            </tr>`;
        });
        html += `</tbody></table></td></tr>`;

        gA += r.accepted; gU += r.unreviewed; gR += r.rejected; gT += r.total; gArticles += r.articles.length;
    });

    html += `</tbody></table>`;
    tableWrap.innerHTML = html;
    summaryEl.textContent = `সারাংশ — নিবন্ধ: ${formatBn(gArticles)} | মোট শব্দ: ${formatBn(gT)}`;

    tableWrap.querySelectorAll('.user-row').forEach(row => {
        row.onclick = () => {
            const subRow = tableWrap.querySelector(`.articles-row[data-user="${row.dataset.user}"]`);
            subRow.classList.toggle('hidden');
        };
    });
}