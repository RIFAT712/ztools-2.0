import { toBn, formatBn, escapeHtml } from './utils.js';

const parser = new DOMParser();

export async function loadArticleWordCounts(code, endpoints, ui) {
    const { fountainEndpoint } = endpoints;
    const { countBtn, juryBtn, progressWrap, progressBar, resultCard, tableWrap, summaryEl, errorEl } = ui;

    countBtn.disabled = juryBtn.disabled = true;
    progressWrap.style.display = 'block';
    progressBar.style.width = '0%';
    errorEl.classList.add('hidden');

    try {
        const resp = await fetch(fountainEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const body = await resp.json();
        if (body.error) throw new Error(body.error);

        const rawArticles = body.articles || {};
        const siteUrl = body.site_url || 'bn.wikipedia.org';
        const tasks = [];

        for (const user in rawArticles) {
            for (const a of rawArticles[user]) {
                const title = a.name || '';
                const status = a.status || 'অপর্যালোচিত';
                const reviews = a.reviews || 0;
                if (title) tasks.push({ user, title, status, reviews });
            }
        }

        if (tasks.length === 0) {
            showError('কোনো নিবন্ধ পাওয়া যায়নি।');
            progressWrap.style.display = 'none';
            return;
        }

        await countArticleWords(tasks, siteUrl, ui);

    } catch (e) {
        showError('ডেটা আনতে ব্যর্থ: ' + e.message);
    } finally {
        countBtn.disabled = juryBtn.disabled = false;
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
        resultCard.classList.add('hidden');
    }
}

async function countArticleWords(tasks, siteUrl, ui) {
    const { progressBar, progressWrap } = ui;
    const MAX_CONCURRENT = 100;

    const totals = {};
    for (const t of tasks) {
        if (!totals[t.user]) totals[t.user] = { accepted: 0, unreviewed: 0, rejected: 0, total: 0, articles: [] };
    }

    let idx = 0, done = 0;
    progressBar.style.width = '0%';

    async function fetchOne() {
        if (idx >= tasks.length) return;
        const task = tasks[idx++];

        try {
            const url = `https://${siteUrl}/w/api.php?action=parse&page=${encodeURIComponent(task.title)}&format=json&prop=text&redirects=true&origin=*`;
            const res = await fetch(url);
            const data = await res.json();
            if (data.error) throw new Error('Page not found');

            const actualTitle = data.parse.title;
            const doc = parser.parseFromString(data.parse.text['*'] || '', 'text/html');

            const unwanted = [
                '.mw-empty-elt', '.mw-editsection', '.reference', '.references', '.reflist',
                '.mbox-small', '.ambox', '.navbox', '.catlinks', '.noprint', '.metadata', '.portal', 'style', 'script', '.thumbinner', '.listing-lastedit'
            ].join(',');
            doc.querySelectorAll(unwanted).forEach(e => e.remove());

            const content = doc.body.textContent || '';
            const words = siteUrl.startsWith('bn.')
                ? (content.match(/[ঀ-৿]+/g) || []).length
                : content.split(/\s+/).filter(w => w.length > 0).length;

            const userStats = totals[task.user];
            userStats.total += words;
            if (task.status === 'গৃহীত হয়েছে') userStats.accepted += words;
            else if (task.status === 'গৃহীত হয়নি') userStats.rejected += words;
            else userStats.unreviewed += words;

            userStats.articles.push({
                title: task.title,
                actualTitle: actualTitle !== task.title ? actualTitle : '',
                status: task.status,
                words: words,
                isRedirect: actualTitle !== task.title
            });

        } catch (e) {
            // Silently fail for individual pages
        } finally {
            done++;
            progressBar.style.width = `${Math.round((done / tasks.length) * 100)}%`;
        }
    }

    const workers = Array.from({ length: Math.min(MAX_CONCURRENT, tasks.length) }, async () => {
        while (idx < tasks.length) {
            await fetchOne();
        }
    });

    await Promise.all(workers);
    progressWrap.style.display = 'none';

    renderArticleTable(totals, ui);
}

function renderArticleTable(totals, ui) {
    const { tableWrap, summaryEl, resultCard } = ui;
    const keys = Object.keys(totals);
    if (keys.length === 0) { resultCard.classList.add('hidden'); return; }

    resultCard.classList.remove('hidden');

    const rows = Object.entries(totals)
        .map(([user, v]) => ({ user, ...v }))
        .sort((a, b) => b.accepted - a.accepted);

    // Refresh toolbar
    let toolbar = resultCard.querySelector('.copy-toolbar');
    if (toolbar) toolbar.remove();
    toolbar = document.createElement('div');
    toolbar.className = 'copy-toolbar';
    toolbar.style.marginBottom = '0.5em';
    resultCard.prepend(toolbar);

    const createBtn = (text, onClick) => {
        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.textContent = text;
        btn.onclick = onClick;
        toolbar.appendChild(btn);
        return btn;
    };

    const copyWikiBtn = createBtn('সকল ব্যবহারকারী', () => {
        let wikitable = '{| class="wikitable sortable"\n! ব্যবহারকারী !! গৃহীত !! অপর্যালোচিত !! বাতিল !! মোট শব্দ !! মোট নিবন্ধ\n';
        rows.forEach(r => {
            wikitable += `|-\n| ${r.user} || ${toBn(r.accepted)} || ${toBn(r.unreviewed)} || ${toBn(r.rejected)} || ${toBn(r.total)} || ${toBn(r.articles.length)}\n`;
        });
        wikitable += `|-\n! মোট || ${toBn(gA)} || ${toBn(gU)} || ${toBn(gR)} || ${toBn(gT)} || ${toBn(gArticles)}\n|}`;

        navigator.clipboard.writeText(wikitable).then(() => {
            copyWikiBtn.textContent = '✓ কপি হয়েছে';
            setTimeout(() => copyWikiBtn.textContent = 'সকল ব্যবহারকারী', 1400);
        });
    });

    const copyArticlesBtn = createBtn('ব্যবহারকারী অনুযায়ী', () => {
        let allText = '';
        rows.forEach(r => {
            const acceptedArticles = r.articles.filter(a => a.status === 'গৃহীত হয়েছে');
            if (acceptedArticles.length === 0) return;

            allText += `=== [[User:${r.user}|${r.user}]] ===\n`;
            allText += `{| class="wikitable sortable"\n! নিবন্ধ !! শব্দ\n`;
            let userTotal = 0;
            acceptedArticles.forEach(a => {
                const displayTitle = a.actualTitle ? `${a.title} (${a.actualTitle})` : a.title;
                allText += `|-\n| ${displayTitle} || ${toBn(a.words)}\n`;
                userTotal += a.words;
            });
            allText += `|-\n| মোট শব্দ || ${toBn(userTotal)}\n`;
            allText += `|}\n\n`;
        });

        navigator.clipboard.writeText(allText).then(() => {
            copyArticlesBtn.textContent = '✓ কপি হয়েছে';
            setTimeout(() => copyArticlesBtn.textContent = 'ব্যবহারকারী অনুযায়ী', 1400);
        });
    });

    let html = '<table><thead><tr><th>#</th><th class="left">ব্যবহারকারী</th><th>গৃহীত</th><th>অপর্যালোচিত</th><th>বাতিল</th><th>মোট শব্দ</th><th>মোট নিবন্ধ</th></tr></thead><tbody>';
    let gA = 0, gU = 0, gR = 0, gT = 0, gArticles = 0;

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
            html += `<tr class="${a.isRedirect ? 'redirect' : ''}">
                <td>${formatBn(j + 1)}</td>
                <td class="left">
                  <span style="display:flex; align-items:center; justify-content:flex-start;">
                    <span>${escapeHtml(a.title)}</span>
                    ${a.actualTitle ? `<span style="font-size:0.7em; opacity:0.6; margin-left:5px;">(${escapeHtml(a.actualTitle)})</span>` : ''}
                  </span>
                </td>
                <td>${formatBn(a.words)}</td>
                <td>${escapeHtml(a.status)}</td>
            </tr>`;
        });

        html += `<tr style="font-weight:bold;"><td colspan="2">মোট শব্দ</td><td>${formatBn(r.total)}</td><td></td></tr></tbody></table></td></tr>`;

        gA += r.accepted; gU += r.unreviewed; gR += r.rejected; gT += r.total; gArticles += r.articles.length;
    });

    html += `<tr class="total-row"><td></td><td class="left">মোট</td><td>${formatBn(gA)}</td><td>${formatBn(gU)}</td><td>${formatBn(gR)}</td><td>${formatBn(gT)}</td><td>${formatBn(gArticles)}</td></tr></tbody></table>`;
    tableWrap.innerHTML = html;

    summaryEl.textContent = `সারাংশ — মোট গৃহীত: ${formatBn(gA)} | মোট অপর্যালোচিত: ${formatBn(gU)} | মোট বাতিল: ${formatBn(gR)} | মোট শব্দ: ${formatBn(gT)} | মোট নিবন্ধ: ${formatBn(gArticles)}`;

    tableWrap.querySelectorAll('.user-row').forEach(row => {
        row.addEventListener('click', () => {
            const user = row.dataset.user;
            const subRow = tableWrap.querySelector(`.articles-row[data-user="${user}"]`);
            if (subRow) subRow.classList.toggle('hidden');
        });
    });
}
