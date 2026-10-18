# Dashboard design notes (for frontend-dev)

**Reference:** `trustvest-dashboard.png` (Dribbble, "TrustVest FinTech Dashboard Animation" by Alamin Hossen).
**Use it for style and layout only.** Do NOT copy the TrustVest name, logo, illustrations or any finance-specific content. Our product has its own name and data.

---

## 1. Visual style to match

| Element | What the reference does | Our rule |
|---|---|---|
| Theme | Light. White cards on a very light grey page | Page `#F6F7F9`-ish, cards `#FFFFFF` |
| Cards | Thin 1px light-grey border, ~12–14px rounded corners, almost no shadow, generous padding (~20–24px) | Same |
| Primary colour | Deep emerald green for charts | Emerald (~`#1E7A5A`) as the main data colour |
| Call-to-action | Bright lime-green button ("Send Money") | Lime (~`#A6E07A`) for the main action, e.g. **Start batch** |
| Soft accent | Pale mint fill behind highlighted chart column and pill buttons | Mint (~`#E6F6EE`) for highlights and selected states |
| Status chips | Small pill with a coloured dot: green "Active", red "Inactive" | Same pattern for row statuses (see §3) |
| Big numbers | Large bold figure with the decimals in faded grey (`$34,680.05`) | Large KPI numbers; secondary part (like "/ 1,000") in faded grey |
| Typography | Clean geometric sans-serif, medium weights, small grey labels | A geometric Google font (e.g. Outfit, Urbanist or Plus Jakarta Sans) + **Noto Sans Devanagari** for Hindi names |
| Icons | Thin outline icons (1.5px stroke) | Same style (e.g. Lucide icons) |
| Chart | Stepped area/bar chart, emerald bars with a fine diagonal hatch pattern, value labels above each column, dashed vertical separators, one highlighted column | Same look for "Videos generated" |
| Dividers | Hairline separators, lots of white space | Same |
| Motion (from the Dribbble animation) | Numbers count up, bars grow in, smooth hovers | Same, but respect "reduce motion" settings |

## 2. Layout

```
┌──────────────┬──────────────────────────────────────────────────────┐
│ Logo  [≡]    │ Page title                      [+ New batch] (avatar)│
│ Search  ⌘K   ├──────────────────────────────────────────────────────┤
│ MENU         │ [KPI] [KPI] [KPI] [KPI] [KPI] [KPI]                  │
│  Overview    ├───────────────────────────────────┬──────────────────┤
│  Batches     │ Videos generated (chart)          │ Current batch    │
│   ├ Running  │  This week ▾       +12% vs last   │ progress ring    │
│   ├ Completed│  ▇▇ stepped hatched bars          │ ETA, counts      │
│   └ Failed   │                                   │ [Pause][Retry]   │
│  Templates   │                                   │ [ Start batch ]  │
│  History     ├───────────────────────────────────┴──────────────────┤
│  Security    │ Rows table: search · status filter                   │
│ GENERAL      │ Name | ID | Status | Reason | Time | ⋮               │
│  Settings    │                                                      │
│  Help        │                                                      │
└──────────────┴──────────────────────────────────────────────────────┘
```

## 3. Mapping the reference to our screens

| Reference element | Our version |
|---|---|
| Currency cards (USD, EUR, BDT, GBP) + dashed "+" card | **KPI cards**: Total rows · Completed · Processing · Queued · Failed · Skipped. Each has a status chip. The dashed "+" card becomes **New batch** |
| "Payment Overview" chart + "Total Balance" | **Videos generated** over time (day / week), total count as the big number, "+X% vs last week" pill |
| Column labels ("Payment Initiatives $10,120") | Per-period counts ("Mon · 1,240 videos") |
| "Transfer Calculator" side panel | **Current batch** panel: progress ring, ETA, completed/failed counts, Pause / Resume / Retry failed, main lime button |
| "Transactions History" table | **Rows table**: Name (Devanagari OK), ID, Status chip, Failure reason in plain words, render time, actions (preview, download, retry) |
| Received / Send chips | Completed (green) · Processing (blue) · Queued (grey) · Failed (red) · Skipped (amber) |
| "This Month ▾" dropdowns | Period filter and status filter |
| "Try ai Agent" / "Earn $50" pills | Not needed. Use one **+ New batch** pill instead |
| Sidebar MENU / GENERAL | MENU: Overview, Batches (Running, Completed, Failed), Templates, History, Security (audit log). GENERAL: Settings, Help |

## 4. Our-product additions (not in the reference)

- The **AI-label / consent status** badge on each template card (consent ✓ / missing).
- A **security alert** banner when the audit log has a `SECURITY_LOGIN_THROTTLED` event.
- The **4-step New batch wizard** (upload → map columns & validate → mark slot & preview → output folder & start), in the same card style.
- Every screen has loading, empty and error states in the same visual language.
- Hindi text must render correctly anywhere a name appears.
