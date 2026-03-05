// ── State ──
let campaigns = [];

// ── Tab Switching ──
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab + '-tab').classList.add('active');
    });
});

// ── Auto-calculate royalty ──
document.getElementById('bookPrice').addEventListener('input', calcRoyalty);
document.getElementById('printCost').addEventListener('input', calcRoyalty);
document.getElementById('royaltyRate').addEventListener('input', calcRoyalty);
calcRoyalty();

function calcRoyalty() {
    const price = parseFloat(document.getElementById('bookPrice').value) || 0;
    const printCost = parseFloat(document.getElementById('printCost').value) || 0;
    const rate = parseFloat(document.getElementById('royaltyRate').value) || 60;
    const royalty = (price * rate / 100) - printCost;
    document.getElementById('royaltyPerSale').value = royalty.toFixed(2);
}

function getRoyalty() {
    return parseFloat(document.getElementById('royaltyPerSale').value) || 0;
}

function getTargetAcos() {
    return parseFloat(document.getElementById('targetAcos').value) || 35;
}

// ── CSV Parsing ──
function parseCSV() {
    const raw = document.getElementById('csvInput').value.trim();
    if (!raw) return;

    const lines = raw.split('\n').map(l => l.trim()).filter(l => l);
    if (lines.length < 2) return;

    // Detect delimiter
    const delimiter = lines[0].includes('\t') ? '\t' : ',';

    const headers = lines[0].split(delimiter).map(h => h.trim().toLowerCase());

    // Map headers flexibly
    const colMap = findColumns(headers);

    const parsed = [];
    for (let i = 1; i < lines.length; i++) {
        const cols = splitCSVLine(lines[i], delimiter);
        if (cols.length < 3) continue;

        const row = {
            name: cols[colMap.name] || 'Campaign ' + i,
            impressions: parseNum(cols[colMap.impressions]),
            clicks: parseNum(cols[colMap.clicks]),
            spend: parseNum(cols[colMap.spend]),
            orders: parseNum(cols[colMap.orders]),
            sales: parseNum(cols[colMap.sales])
        };
        if (row.impressions > 0 || row.clicks > 0 || row.spend > 0) {
            parsed.push(row);
        }
    }

    if (parsed.length === 0) return;
    campaigns = parsed;
    recalculate();
}

function splitCSVLine(line, delimiter) {
    if (delimiter === '\t') return line.split('\t').map(c => c.trim());

    const result = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
            inQuotes = !inQuotes;
        } else if (ch === ',' && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += ch;
        }
    }
    result.push(current.trim());
    return result;
}

function findColumns(headers) {
    const map = { name: 0, impressions: 1, clicks: 2, spend: 3, orders: 4, sales: 5 };
    const patterns = {
        name: /campaign|name|ad\s*group|keyword/i,
        impressions: /impress/i,
        clicks: /click/i,
        spend: /spend|cost/i,
        orders: /order|purchase|conversion/i,
        sales: /sale|revenue/i
    };

    for (const [key, regex] of Object.entries(patterns)) {
        const idx = headers.findIndex(h => regex.test(h));
        if (idx !== -1) map[key] = idx;
    }
    return map;
}

function parseNum(val) {
    if (val === undefined || val === null) return 0;
    return parseFloat(String(val).replace(/[$,%]/g, '')) || 0;
}

// ── Manual Entry ──
function addManualCampaign() {
    const name = document.getElementById('campaignName').value.trim();
    if (!name) return;

    campaigns.push({
        name,
        impressions: parseFloat(document.getElementById('impressions').value) || 0,
        clicks: parseFloat(document.getElementById('clicks').value) || 0,
        spend: parseFloat(document.getElementById('spend').value) || 0,
        orders: parseFloat(document.getElementById('orders').value) || 0,
        sales: parseFloat(document.getElementById('sales').value) || 0
    });

    // Reset form
    document.getElementById('campaignName').value = '';
    document.getElementById('impressions').value = '';
    document.getElementById('clicks').value = '';
    document.getElementById('spend').value = '';
    document.getElementById('orders').value = '';
    document.getElementById('sales').value = '';

    recalculate();
}

// ── Demo Data ──
function loadDemoData() {
    campaigns = [
        { name: 'Notebook Lined - Exact', impressions: 18500, clicks: 120, spend: 42.00, orders: 8, sales: 55.92 },
        { name: 'Notebook Lined - Broad', impressions: 45000, clicks: 310, spend: 124.00, orders: 9, sales: 62.91 },
        { name: 'Journal Gratitude - Exact', impressions: 9200, clicks: 75, spend: 22.50, orders: 6, sales: 41.94 },
        { name: 'Journal Gratitude - Phrase', impressions: 22000, clicks: 180, spend: 72.00, orders: 5, sales: 34.95 },
        { name: 'Planner Weekly - Exact', impressions: 14000, clicks: 95, spend: 38.00, orders: 7, sales: 62.93 },
        { name: 'Planner Weekly - Broad', impressions: 52000, clicks: 420, spend: 189.00, orders: 10, sales: 89.90 },
        { name: 'Sketchbook Kids - Auto', impressions: 31000, clicks: 250, spend: 87.50, orders: 12, sales: 83.88 },
        { name: 'Coloring Book Adult - Exact', impressions: 8000, clicks: 55, spend: 19.25, orders: 5, sales: 49.95 },
        { name: 'Password Log - Broad', impressions: 38000, clicks: 290, spend: 130.50, orders: 4, sales: 27.96 },
        { name: 'Dot Grid Notebook - Phrase', impressions: 16000, clicks: 110, spend: 44.00, orders: 3, sales: 20.97 },
    ];
    recalculate();
}

// ── Core Analysis ──
function enrichCampaign(c) {
    const royalty = getRoyalty();
    const ctr = c.impressions > 0 ? (c.clicks / c.impressions) * 100 : 0;
    const cpc = c.clicks > 0 ? c.spend / c.clicks : 0;
    const convRate = c.clicks > 0 ? (c.orders / c.clicks) * 100 : 0;
    const acos = c.sales > 0 ? (c.spend / c.sales) * 100 : (c.spend > 0 ? 999 : 0);
    const roas = c.spend > 0 ? c.sales / c.spend : 0;
    const grossProfit = (c.orders * royalty) - c.spend;
    const costPerOrder = c.orders > 0 ? c.spend / c.orders : c.spend;

    return { ...c, ctr, cpc, convRate, acos, roas, grossProfit, costPerOrder, royalty };
}

function getAction(e) {
    const targetAcos = getTargetAcos();
    const breakEvenAcos = e.royalty > 0 ? (e.royalty / (parseFloat(document.getElementById('bookPrice').value) || 6.99)) * 100 : 50;

    if (e.orders === 0 && e.spend > 10) return { label: 'Pause', cls: 'action-pause' };
    if (e.orders === 0 && e.clicks < 20) return { label: 'Monitor', cls: 'action-monitor' };
    if (e.acos <= targetAcos && e.orders >= 3) return { label: 'Scale', cls: 'action-scale' };
    if (e.acos <= breakEvenAcos) return { label: 'Optimize', cls: 'action-optimize' };
    if (e.acos > breakEvenAcos && e.orders > 0) return { label: 'Lower Bid', cls: 'action-pause' };
    if (e.acos > 100) return { label: 'Pause', cls: 'action-pause' };
    return { label: 'Monitor', cls: 'action-monitor' };
}

function getSuggestedBid(e) {
    const targetAcos = getTargetAcos() / 100;
    const avgSalePrice = e.orders > 0 ? e.sales / e.orders : parseFloat(document.getElementById('bookPrice').value) || 6.99;
    const conversionRate = e.clicks > 0 ? e.orders / e.clicks : 0;

    if (conversionRate === 0) return null;

    // Target CPC = target ACoS * avg sale price * conversion rate
    const targetCPC = targetAcos * avgSalePrice * conversionRate;
    return { current: e.cpc, suggested: targetCPC };
}

// ── Recalculate Everything ──
function recalculate() {
    if (campaigns.length === 0) return;

    document.getElementById('results-section').classList.remove('hidden');

    const enriched = campaigns.map(enrichCampaign);

    renderSummary(enriched);
    renderTable(enriched);
    renderRecommendations(enriched);
    renderBidSuggestions(enriched);
}

// ── Render Summary ──
function renderSummary(data) {
    const totals = data.reduce((acc, c) => {
        acc.impressions += c.impressions;
        acc.clicks += c.clicks;
        acc.spend += c.spend;
        acc.orders += c.orders;
        acc.sales += c.sales;
        return acc;
    }, { impressions: 0, clicks: 0, spend: 0, orders: 0, sales: 0 });

    const royalty = getRoyalty();
    const totalProfit = (totals.orders * royalty) - totals.spend;
    const overallAcos = totals.sales > 0 ? (totals.spend / totals.sales) * 100 : 0;
    const overallCPC = totals.clicks > 0 ? totals.spend / totals.clicks : 0;
    const overallConv = totals.clicks > 0 ? (totals.orders / totals.clicks) * 100 : 0;
    const costPerSale = totals.orders > 0 ? totals.spend / totals.orders : 0;
    const targetAcos = getTargetAcos();

    const metrics = [
        { label: 'Total Spend', value: '$' + totals.spend.toFixed(2), status: 'neutral' },
        { label: 'Total Orders', value: totals.orders, status: 'neutral' },
        { label: 'Cost / Sale', value: '$' + costPerSale.toFixed(2), status: costPerSale > royalty ? 'bad' : costPerSale > royalty * 0.7 ? 'warning' : 'good' },
        { label: 'Overall ACoS', value: overallAcos.toFixed(1) + '%', status: overallAcos > targetAcos * 1.5 ? 'bad' : overallAcos > targetAcos ? 'warning' : 'good' },
        { label: 'Avg CPC', value: '$' + overallCPC.toFixed(2), status: 'neutral' },
        { label: 'Conv Rate', value: overallConv.toFixed(1) + '%', status: overallConv < 2 ? 'bad' : overallConv < 5 ? 'warning' : 'good' },
        { label: 'Net Profit', value: '$' + totalProfit.toFixed(2), status: totalProfit < 0 ? 'bad' : totalProfit < 20 ? 'warning' : 'good' },
        { label: 'Campaigns', value: data.length, status: 'neutral' },
    ];

    document.getElementById('summaryMetrics').innerHTML = metrics.map(m =>
        `<div class="metric-card ${m.status}">
            <div class="metric-value">${m.value}</div>
            <div class="metric-label">${m.label}</div>
        </div>`
    ).join('');
}

// ── Render Table ──
function renderTable(data) {
    const enriched = data || campaigns.map(enrichCampaign);
    const sortKey = document.getElementById('sortSelect').value;

    const sorted = [...enriched].sort((a, b) => {
        switch (sortKey) {
            case 'acos': return b.acos - a.acos;
            case 'spend': return b.spend - a.spend;
            case 'profit': return a.grossProfit - b.grossProfit;
            case 'cpc': return b.cpc - a.cpc;
            case 'convRate': return a.convRate - b.convRate;
            default: return 0;
        }
    });

    const targetAcos = getTargetAcos();

    document.getElementById('campaignTableBody').innerHTML = sorted.map(e => {
        const action = getAction(e);
        const rowClass = e.grossProfit > 0 ? 'row-good' : e.grossProfit > -10 ? 'row-warning' : 'row-bad';
        return `<tr class="${rowClass}">
            <td title="${e.name}">${e.name}</td>
            <td>${e.impressions.toLocaleString()}</td>
            <td>${e.clicks.toLocaleString()}</td>
            <td>${e.ctr.toFixed(2)}%</td>
            <td>$${e.cpc.toFixed(2)}</td>
            <td>$${e.spend.toFixed(2)}</td>
            <td>${e.orders}</td>
            <td>${e.convRate.toFixed(1)}%</td>
            <td>${e.acos < 900 ? e.acos.toFixed(1) + '%' : 'N/A'}</td>
            <td>${e.roas.toFixed(2)}</td>
            <td class="${e.grossProfit >= 0 ? '' : 'bad'}">$${e.grossProfit.toFixed(2)}</td>
            <td><span class="action-badge ${action.cls}">${action.label}</span></td>
        </tr>`;
    }).join('');
}

// ── Render Recommendations ──
function renderRecommendations(data) {
    const recs = [];
    const royalty = getRoyalty();
    const targetAcos = getTargetAcos();

    // Identify money-draining campaigns
    const losers = data.filter(c => c.grossProfit < -5).sort((a, b) => a.grossProfit - b.grossProfit);
    if (losers.length > 0) {
        const totalLoss = losers.reduce((s, c) => s + c.grossProfit, 0);
        recs.push({
            priority: 'high',
            title: `${losers.length} campaign(s) losing money (-$${Math.abs(totalLoss).toFixed(2)} total)`,
            detail: `These campaigns cost more in ad spend than they earn in royalties: ${losers.map(c => c.name).join(', ')}. Consider lowering bids by 20-30% or pausing the worst performers.`
        });
    }

    // High spend, no orders
    const noOrders = data.filter(c => c.orders === 0 && c.spend > 5);
    if (noOrders.length > 0) {
        const wastedSpend = noOrders.reduce((s, c) => s + c.spend, 0);
        recs.push({
            priority: 'high',
            title: `$${wastedSpend.toFixed(2)} spent with zero orders across ${noOrders.length} campaign(s)`,
            detail: `${noOrders.map(c => c.name).join(', ')} have clicks but no conversions. Pause these or add negative keywords from the search term report.`
        });
    }

    // Broad match overspending
    const broadCampaigns = data.filter(c => /broad|auto/i.test(c.name));
    const exactCampaigns = data.filter(c => /exact/i.test(c.name));
    if (broadCampaigns.length > 0 && exactCampaigns.length > 0) {
        const broadAvgAcos = broadCampaigns.reduce((s, c) => s + c.acos, 0) / broadCampaigns.length;
        const exactAvgAcos = exactCampaigns.reduce((s, c) => s + c.acos, 0) / exactCampaigns.length;
        if (broadAvgAcos > exactAvgAcos * 1.3) {
            recs.push({
                priority: 'medium',
                title: 'Broad/Auto campaigns have significantly higher ACoS than Exact',
                detail: `Broad/Auto avg ACoS: ${broadAvgAcos.toFixed(1)}% vs Exact avg ACoS: ${exactAvgAcos.toFixed(1)}%. Mine your search term reports for converting keywords and move them to exact match campaigns with lower bids.`
            });
        }
    }

    // Low CTR
    const lowCTR = data.filter(c => c.ctr < 0.2 && c.impressions > 5000);
    if (lowCTR.length > 0) {
        recs.push({
            priority: 'medium',
            title: `${lowCTR.length} campaign(s) with very low CTR (<0.2%)`,
            detail: `Low CTR usually means poor keyword-to-product relevance or weak cover/title. Review: ${lowCTR.map(c => `${c.name} (${c.ctr.toFixed(2)}%)`).join(', ')}.`
        });
    }

    // High CPC for low content books
    const highCPC = data.filter(c => c.cpc > 0.50 && c.clicks > 10);
    if (highCPC.length > 0) {
        recs.push({
            priority: 'medium',
            title: `${highCPC.length} campaign(s) with CPC above $0.50`,
            detail: `For low content books with slim margins, CPC above $0.50 makes profitability difficult. Lower bids on: ${highCPC.map(c => `${c.name} ($${c.cpc.toFixed(2)})`).join(', ')}.`
        });
    }

    // Good performers to scale
    const winners = data.filter(c => c.grossProfit > 0 && c.acos < targetAcos && c.orders >= 3);
    if (winners.length > 0) {
        recs.push({
            priority: 'low',
            title: `${winners.length} profitable campaign(s) ready to scale`,
            detail: `These are performing below your target ACoS and generating profit: ${winners.map(c => `${c.name} (ACoS: ${c.acos.toFixed(1)}%, Profit: $${c.grossProfit.toFixed(2)})`).join(', ')}. Consider increasing bids by 10-15% to capture more impressions.`
        });
    }

    // Cost per sale vs royalty
    const overallCostPerSale = data.reduce((s, c) => s + c.spend, 0) / Math.max(data.reduce((s, c) => s + c.orders, 0), 1);
    if (overallCostPerSale > royalty) {
        recs.push({
            priority: 'high',
            title: `Cost per sale ($${overallCostPerSale.toFixed(2)}) exceeds royalty ($${royalty.toFixed(2)})`,
            detail: `You are losing money on every sale on average. Your max profitable CPC depends on your conversion rate. Focus on improving conversion rate through better targeting and listing optimization, and lower bids across the board.`
        });
    }

    // General tip if few recs
    if (recs.length < 2) {
        recs.push({
            priority: 'info',
            title: 'Tip: Review search term reports weekly',
            detail: 'Download your search term report from Amazon Ads and add irrelevant terms as negative keywords. For low content books, negate terms that indicate buyers want digital/ebook versions.'
        });
    }

    const priorityMap = { high: 'rec-high', medium: 'rec-medium', low: 'rec-low', info: 'rec-info' };
    const priorityOrder = { high: 0, medium: 1, low: 2, info: 3 };
    recs.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

    document.getElementById('recommendationsList').innerHTML = recs.map(r =>
        `<div class="rec-card ${priorityMap[r.priority]}">
            <strong>${r.title}</strong>
            ${r.detail}
        </div>`
    ).join('');
}

// ── Render Bid Suggestions ──
function renderBidSuggestions(data) {
    const enriched = data || campaigns.map(enrichCampaign);
    const suggestions = enriched
        .filter(c => c.clicks >= 10)
        .map(c => {
            const bid = getSuggestedBid(c);
            if (!bid) return null;
            return { name: c.name, ...bid };
        })
        .filter(Boolean)
        .sort((a, b) => (a.suggested - a.current) - (b.suggested - b.current));

    if (suggestions.length === 0) {
        document.getElementById('bidList').innerHTML = '<p class="section-desc">Need at least 10 clicks per campaign to suggest bid adjustments.</p>';
        return;
    }

    document.getElementById('bidList').innerHTML = suggestions.map(s => {
        const diff = s.suggested - s.current;
        const arrow = diff < -0.01 ? '&#8595;' : diff > 0.01 ? '&#8593;' : '&#8596;';
        const arrowCls = diff < -0.01 ? 'bid-down' : diff > 0.01 ? 'bid-up' : '';
        return `<div class="bid-card">
            <span class="bid-campaign">${s.name}</span>
            <div class="bid-values">
                <div class="bid-current">
                    <div class="bid-label">Current CPC</div>
                    <div class="bid-amount">$${s.current.toFixed(2)}</div>
                </div>
                <span class="bid-arrow ${arrowCls}">${arrow}</span>
                <div class="bid-suggested">
                    <div class="bid-label">Suggested CPC</div>
                    <div class="bid-amount">$${s.suggested.toFixed(2)}</div>
                </div>
            </div>
        </div>`;
    }).join('');
}
