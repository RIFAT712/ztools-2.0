import { toBn, escapeHtml } from './utils.js';

export async function loadJuryStats(code, endpoints, ui) {
    const { juryEndpoint } = endpoints;
    const { countBtn, juryBtn, progressWrap, progressBar, juryCard, juryParsedWrap, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    progressWrap.style.display = 'block';
    progressBar.style.width = '0%';
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
        progressWrap.style.display = 'none';

        if (juries.length === 0) {
            juryCard.classList.add('hidden');
            return;
        }

        juryCard.classList.remove('hidden');
        juries.sort((a, b) => b[1].total - a[1].total);

        let html = '<table><thead><tr><th>#</th><th class="left">পর্যালোচক</th><th>মোট</th><th>গৃহীত</th><th>বাতিল</th></tr></thead><tbody>';
        let wikitable = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n';

        let tTot = 0, tAcc = 0, tRej = 0;
        juries.forEach(([j, s], i) => {
            const idx = i + 1;
            html += `<tr><td>${toBn(idx)}</td><td class="left">${escapeHtml(j)}</td><td>${toBn(s.total)}</td><td>${toBn(s.accepted)}</td><td>${toBn(s.rejected)}</td></tr>`;
            wikitable += `|-\n| ${toBn(idx)} || ${j} || ${toBn(s.total)} || ${toBn(s.accepted)} || ${toBn(s.rejected)}\n`;
            tTot += s.total; tAcc += s.accepted; tRej += s.rejected;
        });

        html += `<tr class="total-row"><td></td><td class="left">মোট</td><td>${toBn(tTot)}</td><td>${toBn(tAcc)}</td><td>${toBn(tRej)}</td></tr></tbody></table>`;
        wikitable += `|-\n! মোট ||  || ${toBn(tTot)} || ${toBn(tAcc)} || ${toBn(tRej)}\n|}`;

        juryParsedWrap.innerHTML = html;

        // Refresh copy button
        let headerDiv = juryCard.querySelector('div');
        let existingCopyBtn = headerDiv.querySelector('.copy-btn');
        if (existingCopyBtn) existingCopyBtn.remove();

        const copyJuryBtn = document.createElement('button');
        copyJuryBtn.className = 'copy-btn';
        copyJuryBtn.textContent = 'উইকিটেবিল কপি করুন';
        headerDiv.appendChild(copyJuryBtn);

        copyJuryBtn.onclick = () => {
            navigator.clipboard.writeText(wikitable).then(() => {
                copyJuryBtn.textContent = '✓ কপি হয়েছে';
                setTimeout(() => copyJuryBtn.textContent = 'উইকিটেবিল কপি করুন', 1400);
            });
        };

    } catch (e) {
        progressWrap.style.display = 'none';
        errorEl.textContent = 'ডেটা আনতে ব্যর্থ: ' + e.message;
        errorEl.classList.remove('hidden');
        juryCard.classList.add('hidden');
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
    }
}
