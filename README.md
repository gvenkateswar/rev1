# KDP Ads Optimizer

A local, privacy-first tool to analyze and optimize Amazon Sponsored Product ads for low content KDP books (notebooks, journals, planners, coloring books, etc.).

## Why This Exists

Amazon's ad console gives you raw numbers but doesn't tell you:
- Which campaigns are actually **profitable** after print costs and royalty splits
- What your **bids should be** to hit a target ACoS
- Which campaigns to **scale, optimize, or pause**

This tool fills those gaps.

## Features

- **Profitability analysis** — factors in your book price, print cost, and royalty rate to show true profit per campaign
- **CSV import** — paste your Amazon Ads bulk export directly
- **Manual entry** — add campaigns one at a time
- **Optimization recommendations** — prioritized, actionable advice (pause losers, scale winners, lower bids)
- **Bid calculator** — suggested CPC based on your target ACoS and actual conversion rates
- **Color-coded dashboard** — instantly see which campaigns make money and which don't
- **100% local** — no data is sent anywhere; everything runs in your browser

## How to Use

1. Open `index.html` in your browser
2. Set your book's price, print cost, and royalty rate at the top
3. Paste your Amazon Ads CSV export **or** add campaigns manually
4. Review the dashboard: summary metrics, campaign table, recommendations, and bid suggestions
5. Adjust your target ACoS to see how bid suggestions change

### Getting Your CSV from Amazon

1. Go to **Amazon Ads** > **Campaigns**
2. Click **Export** (top right)
3. Select date range and download
4. Open the file, copy the rows, and paste into the tool

## Files

- `index.html` — Dashboard layout
- `styles.css` — Styling
- `script.js` — Analysis engine and rendering
