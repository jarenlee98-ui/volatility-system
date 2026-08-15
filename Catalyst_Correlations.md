# Catalyst Correlations Database

This database maps extreme historical price swings (>= ±10% in 1 day or >= ±20% in 5 days) to their specific catalyst events.

| Ticker | Event Type | Specific Trigger/Metric | Resulting Price Swing | Catalyst Classification |
|--------|------------|-------------------------|-----------------------|-------------------------|
| NBIS | Earnings / Catalyst | Q2 earnings report featuring a 454% revenue jump, a shift to profitability with $236M in Adjusted EBITDA, and reaching $3 billion in Annual Recurring Revenue (ARR). | +19.67% (PRIMARY · 45% of +43.70% 4d move) | EBITDA Inflection |
| NBIS | Earnings / Catalyst | Securing four separate $1 billion+ AI cloud contracts, validating market demand and the company's aggressive growth strategy. | +10.93% (SECONDARY · 25% of +43.70% 4d move) | Mega-Contract Visibility |
| NBIS | Earnings / Catalyst | Unprecedented pricing power and $9 billion in customer prepayments that mitigated investor concerns regarding heavy cash burn and capital expenditures. | +6.56% (TERTIARY · 15% of +43.70% 4d move) | Hyper-Specific Narrative Validation |
| NBIS | Macro / Sector | Nvidia's $500 billion infrastructure funding initiative and strong competitor earnings creating a highly bullish market environment. | +6.56% (CONTRIBUTING · 15% of +43.70% 4d move) | Sector Macro Tailwind |
| NBIS | Earnings / Catalyst | Analyst reports debunked rumors of Meta selling excess compute, clarifying that Meta was actually a customer rather than a competitor. | +20.92% (PRIMARY · 40% of +52.30% 5d move) | Structural Short Squeeze |
| NBIS | Earnings / Catalyst | On July 29, Nebius officially scheduled its Q2 results for August 12. | +13.08% (SECONDARY · 25% of +52.30% 5d move) | Earnings Beat / Product Hype |
| NBIS | Corporate Action | The market digested a $775 million GPU debt facility secured against deployed hardware and contracted cash flow. | +10.46% (TERTIARY · 20% of +52.30% 5d move) | Hyper-Specific Narrative Validation |
| NBIS | Macro / Sector | Hyperscalers like Microsoft and Meta reaffirmed high-level capital expenditure guidance for AI infrastructure. | +7.85% (CONTRIBUTING · 15% of +52.30% 5d move) | Sector Macro Tailwind |
| NBIS | Earnings / Catalyst | Bloomberg reported Meta plans to monetize excess AI compute and sell infrastructure directly to external developers, threatening its position as Nebius's premier customer with $27B to $30B in commitments. | -14.66% (PRIMARY · 50% of -29.32% 5d move) | Mega-Contract Visibility |
| NBIS | Earnings / Catalyst | Nebius's high customer concentration in Microsoft and Meta exposed its premium valuation of 17x to 19x forward revenue to aggressive multiple compression. | -5.86% (SECONDARY · 20% of -29.32% 5d move) | Dividend Suspension / Capital Flight |
| NBIS | Corporate Action | Aggressive 2026 capital expenditure targets of $20B to $25B against full-year revenue guidance of $3.0B to $3.4B fueled cash burn and dilution fears. | -4.40% (TERTIARY · 15% of -29.32% 5d move) | Hyper-Specific Narrative Validation |
| NBIS | Macro / Sector | Sector-wide neocloud selloff, with peer CoreWeave falling 14%, alongside broader semiconductor and tech sector pullbacks in early July. | -4.40% (CONTRIBUTING · 15% of -29.32% 5d move) | Sector Sympathy Rally |

## System Correlation Rules
- **Standard Revenue Beat**: Yields moderate single-digit gains (e.g., +2% to +6%).
- **Extreme Gap Up (>= 15%)**: Must contain a **Forward Guidance Raise**, a **Structural Short Squeeze**, or **Hyper-Specific Narrative Validation**.
