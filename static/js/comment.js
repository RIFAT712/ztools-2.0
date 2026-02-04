import { initThemeToggle } from './theme.js';

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();

    let activeFountainCode = "";
    let activeFountainName = "";
    const fetchReviewsBtn = document.getElementById('fetchReviewsBtn');
    const select = document.getElementById("editathon-select");

    const ui = {
        fetchReviewsBtn,
        progressWrap: document.getElementById('progressWrap'),
        progressBar: document.getElementById('progressBar'),
        resultCard: document.getElementById('resultCard'),
        tableWrap: document.getElementById('tableWrap'),
        errorEl: document.getElementById('error')
    };

    async function loadEditathons() {
        try {
            select.disabled = true;
            select.placeholder = "এডিটাথন লোড হচ্ছে...";
            const resp = await fetch("/jury_editathons");
            if (!resp.ok) throw new Error("Network response was not ok");
            const data = await resp.json();
            select.innerHTML = '<option value="">এডিটাথন নির্বাচন করুন</option>';
            data.editathons.forEach(e => {
                const option = document.createElement("option");
                option.value = e.code;
                option.textContent = e.name;
                select.appendChild(option);
            });
            select.disabled = false;
        } catch (err) {
            console.error("Failed to load editathons:", err);
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'এডিটাথন তালিকা লোড করতে ব্যর্থ হয়েছে।';
        }
    }

    async function fetchReviews() {
        const code = activeFountainCode.trim();
        if (!code) {
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = 'দয়া করে একটি এডিটাথন নির্বাচন করুন।';
            return;
        }

        ui.errorEl.classList.add('hidden');
        ui.resultCard.classList.add('hidden');
        ui.progressWrap.style.display = 'block';
        ui.progressBar.style.width = '30%';

        try {
            // Fetch reviews and logs in parallel
            const [resp, logsResp] = await Promise.all([
                fetch("/user_reviews", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ code })
                }),
                fetch("/get_sent_logs")
            ]);

            ui.progressBar.style.width = '70%';

            if (resp.status === 401) {
                throw new Error("দয়া করে লগ-ইন করুন।");
            }
            if (!resp.ok) throw new Error("সার্ভার থেকে তথ্য আনতে সমস্যা হয়েছে।");

            const data = await resp.json();
            const logs = await logsResp.json();

            ui.progressBar.style.width = '100%';

            setTimeout(() => {
                ui.progressWrap.style.display = 'none';
                renderReviews(data.reviews, data.site_url, logs);
            }, 300);

        } catch (err) {
            ui.progressWrap.style.display = 'none';
            ui.errorEl.classList.remove('hidden');
            ui.errorEl.textContent = err.message;
        }
    }

    function renderReviews(reviews, siteUrl, logs) {
        if (!reviews || reviews.length === 0) {
            ui.tableWrap.innerHTML = '<p style="text-align:center; padding:20px;">কোনো পর্যালোচনা পাওয়া যায়নি।</p>';
        } else {
            const accepted = reviews.filter(r => r.decision === 'accepted');
            const rejected = reviews.filter(r => r.decision === 'rejected');

            // Build Tab Navigation
            let html = `
                <div class="tab-nav">
                    <button class="tab-btn active" data-tab="accepted">গৃহীত নিবন্ধ (${accepted.length})</button>
                    <button class="tab-btn" data-tab="rejected">বাতিলকৃত নিবন্ধ (${rejected.length})</button>
                </div>
            `;

            // Accepted Content
            html += `<div id="accepted-content" class="tab-content active">`;
            if (accepted.length > 0) {
                html += renderTable(accepted, siteUrl, logs);
            } else {
                html += '<p style="text-align:center; padding:20px; color:var(--muted);">কোনো গৃহীত নিবন্ধ নেই।</p>';
            }
            html += `</div>`;

            // Rejected Content
            html += `<div id="rejected-content" class="tab-content hidden">`;
            if (rejected.length > 0) {
                html += renderTable(rejected, siteUrl, logs);
            } else {
                html += '<p style="text-align:center; padding:20px; color:var(--muted);">কোনো প্রত্যাখ্যাত নিবন্ধ নেই।</p>';
            }
            html += `</div>`;

            ui.tableWrap.innerHTML = html;

            // Add Tab Event Listeners
            const tabs = ui.tableWrap.querySelectorAll('.tab-btn');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    // Remove active class from all tabs
                    tabs.forEach(t => t.classList.remove('active'));
                    // Add active class to clicked tab
                    tab.classList.add('active');

                    // Hide all content
                    ui.tableWrap.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
                    // Show target content
                    const targetId = tab.dataset.tab + '-content';
                    document.getElementById(targetId).classList.remove('hidden');
                });
            });

            // Add event listeners for talk buttons
            ui.tableWrap.querySelectorAll('.talk-btn').forEach(btn => {
                btn.onclick = () => openTalkModal(btn.dataset);
            });
        }
        ui.resultCard.classList.remove('hidden');
    }

    function renderTable(reviews, siteUrl, logs) {
        const sentForThisEditathon = logs[activeFountainCode] || {};

        let html = `
            <table style="margin-bottom: 24px;">
                <thead>
                    <tr>
                        <th class="left">নিবন্ধ</th>
                        <th>জমাদানকারী</th>
                        <th class="left">আপনার মন্তব্য</th>
                        <th>অ্যাকশন</th>
                    </tr>
                </thead>
                <tbody>
        `;

        reviews.forEach(r => {
            const articleUrl = `https://${siteUrl}/wiki/${encodeURIComponent(r.name)}`;
            // const userUrl = `https://${siteUrl}/wiki/User:${encodeURIComponent(r.submitter)}`;
            const userUrl = `https://${siteUrl}/wiki/User:R1F4T/${encodeURIComponent(r.submitter)}`;
            const isSent = sentForThisEditathon[r.name];

            html += `
                <tr>
                    <td class="left"><a href="${articleUrl}" target="_blank" style="color:inherit; text-decoration:none; font-weight:700;">${r.name}</a></td>
                    <td><a href="${userUrl}" target="_blank" style="color:var(--muted); text-decoration:none;">${r.submitter}</a></td>
                    <td class="left">${r.comment || '<span style="color:var(--muted); font-style: italic;">কোনো মন্তব্য নেই</span>'}</td>
                    <td>
                        <button class="copy-btn talk-btn ${isSent ? 'sent' : ''}" 
                            data-name="${r.name}" 
                            data-user="${r.submitter}" 
                            data-decision="${r.decision}"
                            data-comment="${r.comment || ''}">${isSent ? '✓ পাঠানো হয়েছে' : 'বার্তা পাঠান'}</button>
                    </td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        return html;
    }

    function openTalkModal(data) {
        const isAccepted = data.decision === 'accepted';
        const modal = document.createElement('div');
        modal.className = 'modal';

        let contentHtml = `
            <div class="modal-content">
                <h2 style="margin-top:0;">ব্যবহারকারীকে বার্তা পাঠান</h2>
                <p style="color:var(--muted); font-size:0.9rem;">নিবন্ধ: <strong>${data.name}</strong></p>
                
                ${!isAccepted ? `
                <div class="reason-options">
                    <label class="reason-item"><input type="checkbox" value="অসম্পূর্ণ অনুবাদ"> অসম্পূর্ণ অনুবাদ</label>
                    <label class="reason-item"><input type="checkbox" value="যান্ত্রিক অনুবাদ"> যান্ত্রিক অনুবাদ</label>
                    <label class="reason-item"><input type="checkbox" value="এআই অনুবাদ"> এআই অনুবাদ</label>
                    <label class="reason-item"><input type="checkbox" value="শৈলী ঠিক নেই"> শৈলী ঠিক নেই</label>
                    <label class="reason-item"><input type="checkbox" value="অন্যান্য"> অন্যান্য</label>
                </div>
                ` : ''}
                
                <textarea class="custom-comment" placeholder="${isAccepted ? 'অতিরিক্ত মন্তব্য (ঐচ্ছিক)' : 'অতিরিক্ত বর্ণনা (ঐচ্ছিক)'}" rows="3"></textarea>
                
                <div style="display:flex; gap:12px; margin-top:24px;">
                    <button class="btn" id="sendMsgBtn" style="background:var(--text); color:var(--bg);">পাঠান</button>
                    <button class="btn" id="cancelMsgBtn" style="background:transparent;">বাতিল</button>
                </div>
            </div>
        `;

        modal.innerHTML = contentHtml;
        document.body.appendChild(modal);

        modal.querySelector('#cancelMsgBtn').onclick = () => modal.remove();

        modal.querySelector('#sendMsgBtn').onclick = async () => {
            const btn = modal.querySelector('#sendMsgBtn');
            btn.disabled = true;
            btn.textContent = 'পাঠানো হচ্ছে...';

            const custom = modal.querySelector('.custom-comment').value;
            let subject, message;

            if (isAccepted) {
                subject = `${activeFountainName}: [[${data.name}]] গৃহীত হয়েছে`;
                message = `সুপ্রিয় [[User:${data.user}|${data.user}]], আপনার জমাদানকৃত [[${data.name}]] নিবন্ধটি গৃহীত হয়েছে।\n\n${custom ? custom + '\n\n' : ''}${activeFountainName}-এ অংশগ্রহণের জন্য আপনাকে অসংখ্য ধন্যবাদ। ~~~~`;
            } else {
                const selectedReasons = Array.from(modal.querySelectorAll('input:checked')).map(i => i.value);
                let reasonsText = "";
                if (selectedReasons.length > 0) {
                    reasonsText = "\n# " + selectedReasons.join("\n# ");
                } else {
                    reasonsText = " বিভিন্ন সমস্যা";
                }

                subject = `${activeFountainName}: [[${data.name}]] গৃহীত হয়নি`;
                message = `সুপ্রিয় [[User:${data.user}|${data.user}]], আপনার জমাদানকৃত [[${data.name}]] নিবন্ধটি গৃহীত হয়নি। কারণ: ${reasonsText}\n\n${custom ? custom + '\n\n' : ''}সমস্যাগুলো সমাধান করে আমাকে জানানোর অনুরোধ করছি। ${activeFountainName}-এ অংশগ্রহণ করার জন্য আপনাকে অসংখ্য ধন্যবাদ। ~~~~`;
            }

            try {
                const resp = await fetch('/post_talk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user: data.user,
                        subject: subject,
                        message: message,
                        editathon: activeFountainCode,
                        article: data.name
                    })
                });
                const result = await resp.json();

                if (result.edit && result.edit.result === 'Success') {
                    alert('বার্তা সফলভাবে পাঠানো হয়েছে!');
                    modal.remove();
                } else {
                    throw new Error(JSON.stringify(result));
                }
            } catch (err) {
                alert('বার্তা পাঠাতে ব্যর্থ হয়েছে: ' + err.message);
                btn.disabled = false;
                btn.textContent = 'পাঠান';
            }
        };
    }

    select.addEventListener('change', (e) => {
        activeFountainCode = e.target.value;
        activeFountainName = e.target.options[e.target.selectedIndex].text;
        ui.errorEl.classList.add('hidden');
    });

    fetchReviewsBtn.addEventListener('click', fetchReviews);

    loadEditathons();
});
