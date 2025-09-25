// shows jury stats in a table and allows copying as wikitable format
import { toBn, escapeHtml } from './utils.js';

export async function loadJuryStats(code, endpoints, ui) {
    const { juryEndpoint } = endpoints;
    const { countBtn, juryBtn, progressWrap, progressBar, juryCard, juryParsedWrap, copyJuryBtn, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    progressWrap.style.display = 'block';
    progressBar.style.width = '0%';

    try {
        const resp = await fetch(juryEndpoint, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({code})
        });
        const data = await resp.json();
        if(data.error) throw new Error(data.error);

        const juries = data.raw || [];
        progressWrap.style.display = 'none';
        if(juries.length === 0){ juryCard.classList.add('hidden'); return; }

        juryCard.classList.remove('hidden');
        juries.sort((a,b)=>b[1].total - a[1].total);

        let html = '<table><thead><tr><th>#</th><th class="left">পর্যালোচক</th><th>মোট</th><th>গৃহীত</th><th>বাতিল</th></tr></thead><tbody>';
        let wikitable = '{| class="wikitable sortable"\n! # !! পর্যালোচক !! মোট !! গৃহীত !! বাতিল\n';

        let gi=1, tTot=0, tAcc=0, tRej=0;
        for(const [j,s] of juries){
            html += `<tr><td>${toBn(gi)}</td><td class="left">${escapeHtml(j)}</td><td>${toBn(s.total)}</td><td>${toBn(s.accepted)}</td><td>${toBn(s.rejected)}</td></tr>`;
            wikitable += `|-\n| ${toBn(gi)} || ${j} || ${toBn(s.total)} || ${toBn(s.accepted)} || ${toBn(s.rejected)}\n`;
            tTot += s.total; tAcc += s.accepted; tRej += s.rejected; gi++;
        }

        html += `<tr class="total-row"><td></td><td class="left">মোট</td><td>${toBn(tTot)}</td><td>${toBn(tAcc)}</td><td>${toBn(tRej)}</td></tr></tbody></table>`;
        wikitable += `|-\n! মোট ||  || ${toBn(tTot)} || ${toBn(tAcc)} || ${toBn(tRej)}\n|}`;

        juryParsedWrap.innerHTML = html;

        copyJuryBtn.onclick = () => {
            navigator.clipboard.writeText(wikitable).then(() => {
                copyJuryBtn.textContent = '✓ কপি হয়েছে';
                setTimeout(() => copyJuryBtn.textContent = '📋 উইকিটেবিল কপি করুন', 1400);
            });
        };

    } catch(e){
        progressWrap.style.display = 'none';
        errorEl.textContent = 'ডেটা আনতে ব্যর্থ: '+e.message;
        errorEl.classList.remove('hidden');
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
    }
}
