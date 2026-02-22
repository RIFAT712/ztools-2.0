import { toBn, escapeHtml } from './utils.js';

function handleJuryDownload(type, juries, wikitable) {
    if (type === 'csv') {
        let csv = 'Jury,Total,Accepted,Rejected\n';
        juries.forEach(([j, s]) => {
            csv += `"${j}",${s.total},${s.accepted},${s.rejected}\n`;
        });
        downloadFile(csv, 'ztools_jury_stats.csv', 'text/csv');
    } else if (type === 'json') {
        const json = JSON.stringify(juries, null, 2);
        downloadFile(json, 'ztools_jury_stats.json', 'application/json');
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

export async function loadJuryStats(code, endpoints, ui) {
    const { juryEndpoint } = endpoints;
    const { countBtn, juryBtn, progressWrap, progressBar, juryCard, juryParsedWrap, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    progressWrap.style.display = 'block';
    progressBar.style.width = '100%';
    progressBar.classList.add('loading-animation');
    errorEl.classList.add('hidden');

    try {
        const resp = await fetch(juryEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        const juries = data.raw || [];
        const wikitable = data.wikitable || "";
        progressWrap.style.display = 'none';

        if (juries.length === 0) {
            juryCard.classList.add('hidden');
            return;
        }

        juryCard.classList.remove('hidden');

        let html = '<table><thead><tr><th>#</th><th class="left">পর্যালোচক</th><th>মোট</th><th>গৃহীত</th><th>বাতিল</th></tr></thead><tbody>';

        let tTot = 0, tAcc = 0, tRej = 0;
        juries.forEach(([j, s], i) => {
            const idx = i + 1;
            html += `<tr><td>${toBn(idx)}</td><td class="left">${escapeHtml(j)}</td><td>${toBn(s.total)}</td><td>${toBn(s.accepted)}</td><td>${toBn(s.rejected)}</td></tr>`;
            tTot += s.total; tAcc += s.accepted; tRej += s.rejected;
        });

        html += `<tr class="total-row"><td></td><td class="left">মোট</td><td>${toBn(tTot)}</td><td>${toBn(tAcc)}</td><td>${toBn(tRej)}</td></tr></tbody></table>`;

        juryParsedWrap.innerHTML = html;

        // Hook up download dropdown
        const downloadDropdown = juryCard.querySelector('#jury-download-dropdown');
        if (downloadDropdown) {
            downloadDropdown.querySelectorAll('.dropdown-item').forEach(item => {
                item.onclick = (e) => {
                    e.stopPropagation();
                    handleJuryDownload(item.dataset.type, juries, wikitable);
                    downloadDropdown.querySelector('.dropdown-list').classList.add('hidden');
                };
            });
        }

    } catch (e) {
        progressWrap.style.display = 'none';
        errorEl.textContent = 'ডেটা আনতে ব্যর্থ: ' + e.message;
        errorEl.classList.remove('hidden');
        juryCard.classList.add('hidden');
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
        progressWrap.style.display = 'none';
        progressBar.classList.remove('loading-animation');
    }
}
