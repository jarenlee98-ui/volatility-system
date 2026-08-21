import streamlit as st
import pandas as pd
import os
import json
import re
import datetime
import requests
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from supabase_store import (
    load_watchlist, save_watchlist,
    load_upcoming_events, save_upcoming_events,
)

try:
    from volatility_system import EventDrivenVolatilitySystem, CatalystDatabase, EventParser, PredictiveEngine, CatalystRecord, LiveDataFetcher
except ImportError:
    from volatility_system import EventDrivenVolatilitySystem, CatalystDatabase, EventParser, PredictiveEngine, CatalystRecord, LiveDataFetcher

st.set_page_config(
    page_title="Event-Driven Volatility Predictive System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

WATCHLIST_FILE = "watchlist.json"
EVENTS_FILE = "upcoming_events.json"
DB_FILE_PATH = "Catalyst_Correlations.md"

if "db_path" not in st.session_state:
    st.session_state.db_path = DB_FILE_PATH

if "system" not in st.session_state:
    st.session_state.system = EventDrivenVolatilitySystem(db_path=st.session_state.db_path)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

if "upcoming_events" not in st.session_state:
    st.session_state.upcoming_events = load_upcoming_events()

system = st.session_state.system

st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .metric-card { background-color: #1f2937; padding: 20px; border-radius: 10px; border: 1px solid #374151; margin-bottom: 15px; }
    .metric-title { color: #9ca3af; font-size: 0.85rem; text-transform: uppercase; font-weight: bold; margin-bottom: 5px; }
    .metric-value { font-size: 1.8rem; font-weight: bold; color: #34d399; }
    .metric-value-down { font-size: 1.8rem; font-weight: bold; color: #f87171; }
    .directive-card { background-color: #1e3a8a; padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 15px; }
    .actionable-card { background-color: #064e3b; padding: 15px; border-radius: 8px; border-left: 5px solid #10b981; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("📈 Volatility Dashboard")
st.sidebar.subheader("Watchlist Manager")

watchlist_str = st.sidebar.text_area(
    "Active Watchlist Tickers", 
    value=", ".join(st.session_state.watchlist),
    help="Add or remove tickers (comma separated, e.g. NOW, MSFT, AAPL)."
)

if st.sidebar.button("Save Watchlist Tickers"):
    updated_watchlist = [t.strip().upper() for t in watchlist_str.split(",") if t.strip()]
    st.session_state.watchlist = updated_watchlist
    save_watchlist(updated_watchlist)
    st.sidebar.success("Watchlist saved successfully!")
    st.rerun()

st.sidebar.subheader("Configuration")
db_file = st.sidebar.text_input("Database File Path", value=st.session_state.db_path)
if db_file != st.session_state.db_path:
    st.session_state.db_path = db_file
    st.session_state.system = EventDrivenVolatilitySystem(db_path=db_file)
    st.rerun()

st.sidebar.info("""
**System Architecture:**
This system implements a transition from continuous mathematical volatility models to **discrete event classification**. It matches real-time headlines against a historical correlation database to capture high-probability arbitrage windows.
""")

st.title("Event-Driven Volatility Correlation & Predictive Alert System")
st.caption("Discrete Event Classification & Quantitative Arbitrage Matching Engine")

tab_predict, tab_schedule, tab_database, tab_memory = st.tabs([
    "🎯 Prediction Engine",
    "📅 Scheduler & Watchlist", 
    "🗄️ Correlation Database Editor",
    "🧠 Memory Bank"
])

# ==========================================
# TAB 1: REAL-TIME PREDICTION ENGINE
# ==========================================
with tab_predict:
    st.markdown("""
    <div style='margin-bottom:6px'>
        <span style='color:#60a5fa;font-size:1.45rem;font-weight:800;letter-spacing:-0.01em;'>🎯 Real-Time Prediction Engine</span>
        <span style='color:#6b7280;font-size:0.88rem;margin-left:10px;'>Paste a live news drop → AI identifies all catalysts → forecasts price swing from historical DB matches</span>
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    # ── session state ──────────────────────────────────────────────────────────
    if "pe_classifications" not in st.session_state:
        st.session_state.pe_classifications = None
    if "pe_forecast" not in st.session_state:
        st.session_state.pe_forecast = None
    if "pe_ticker" not in st.session_state:
        st.session_state.pe_ticker = ""
    if "pe_price" not in st.session_state:
        st.session_state.pe_price = 0.0
    if "pe_logged" not in st.session_state:
        st.session_state.pe_logged = False

    def _gemini_classify_realtime(ticker: str, news_text: str) -> list:
        """
        Uses Gemini to classify all catalysts in a live news drop.
        Returns list of classification dicts with weight_pct.
        No swing_pct known yet — weights used to rank DB matches.
        """
        api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            st.error("No GEMINI_API_KEY found in secrets.")
            return []

        prompt = f"""You are a quantitative event-driven analyst reviewing a live news drop for {ticker}.

News:
---
{news_text}
---

Identify ALL distinct catalysts present. Return ONLY a valid JSON array (no markdown, no preamble):

[
  {{
    "rank": 1,
    "event_type": "<Earnings / Catalyst | Macro / Sector | Clinical Data / Regulatory | Corporate Action | Guidance Cut>",
    "trigger_metric": "<1-2 sentence description of this specific catalyst with key numbers>",
    "classification": "<Forward Guidance Hike | Structural Short Squeeze | Hyper-Specific Narrative Validation | Sector Sympathy Rally | Supply Chain Failure | Dividend Suspension / Capital Flight | Earnings Beat | Earnings Miss | Earnings Beat / Product Hype | Binary Pipeline Success | Mega-Contract Visibility | EBITDA Inflection | Sector Macro Tailwind>",
    "weight_pct": <integer, all must sum to 100>,
    "direction": "<bullish | bearish>",
    "confidence": "<High | Medium | Low>",
    "rationale": "<1 sentence why this catalyst matters>"
  }}
]

Rules: 1-5 catalysts only. Each must have a unique classification. weight_pct must sum to 100."""

        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            if isinstance(result, dict):
                result = [result]
            # Normalise weights
            total_w = sum(item.get("weight_pct", 0) for item in result)
            if total_w != 100 and total_w > 0:
                for item in result:
                    item["weight_pct"] = round(item.get("weight_pct", 0) * 100 / total_w)
                diff = 100 - sum(item["weight_pct"] for item in result)
                result[0]["weight_pct"] += diff
            return sorted(result, key=lambda x: x.get("rank", 99))
        except Exception as e:
            st.error(f"Gemini classification failed: {e}")
            return []

    def _build_forecast(classifications: list, current_price: float) -> dict:
        """
        For each classification, finds historical DB matches and derives a
        weighted swing forecast. Returns forecast dict.
        """
        forecast_rows = []
        total_min = 0.0
        total_max = 0.0
        dominant_direction = "bullish"
        bearish_weight = sum(c.get("weight_pct", 0) for c in classifications if c.get("direction") == "bearish")
        if bearish_weight > 50:
            dominant_direction = "bearish"

        for c in classifications:
            cls_name = c.get("classification", "")
            weight = c.get("weight_pct", 0) / 100.0
            direction = c.get("direction", "bullish")
            matches = system.db.find_matches_by_classification(cls_name)

            if matches:
                swings = [r.swing_value for r in matches]
                avg_swing = sum(swings) / len(swings)
                swing_range_min = min(swings)
                swing_range_max = max(swings)
                ref_tickers = ", ".join(set(r.ticker for r in matches[:3]))
                db_note = f"DB match: {ref_tickers} (avg {avg_swing:+.1f}%)"
                contributed_min = swing_range_min * weight
                contributed_max = swing_range_max * weight
            else:
                # No DB match — use system rule estimates
                if cls_name == "Forward Guidance Hike":
                    contributed_min, contributed_max = 12.0 * weight, 20.0 * weight
                    db_note = "System rule: ≥15% gap-up expected"
                elif cls_name == "Structural Short Squeeze":
                    contributed_min, contributed_max = 15.0 * weight, 30.0 * weight
                    db_note = "System rule: ≥15% gap-up expected"
                elif cls_name == "Hyper-Specific Narrative Validation":
                    contributed_min, contributed_max = 15.0 * weight, 25.0 * weight
                    db_note = "System rule: ≥15% gap-up expected"
                elif direction == "bearish":
                    contributed_min, contributed_max = -20.0 * weight, -10.0 * weight
                    db_note = "No DB match — estimated from direction"
                else:
                    contributed_min, contributed_max = 2.0 * weight, 6.0 * weight
                    db_note = "No DB match — standard beat estimate"

            total_min += contributed_min
            total_max += contributed_max

            forecast_rows.append({
                "classification": cls_name,
                "weight_pct": c.get("weight_pct", 0),
                "direction": direction,
                "db_note": db_note,
                "contributed_min": contributed_min,
                "contributed_max": contributed_max,
            })

        # Net forecast
        sign_min = "+" if total_min >= 0 else ""
        sign_max = "+" if total_max >= 0 else ""
        if dominant_direction == "bullish" and total_min > 0:
            net_text = f"High Probability of {sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}% Gap Up"
        elif dominant_direction == "bearish" and total_max < 0:
            net_text = f"High Probability of {sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}% Gap Down"
        else:
            net_text = f"Estimated Swing of {sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}%"

        midpoint_pct = (total_min + total_max) / 2.0
        projected_open      = current_price * (1 + (midpoint_pct / 100.0))
        projected_open_low  = current_price * (1 + (total_min   / 100.0))
        projected_open_high = current_price * (1 + (total_max   / 100.0))

        # Actionable playbook
        if dominant_direction == "bullish" and total_min >= 15:
            directive = "Extreme move profile detected. Historical precedent shows multi-catalyst bullish events with ≥15% forecast have strong PEAD (post-earnings announcement drift) follow-through."
            playbook = "If pre-market gap is below the forecast floor, high-probability arbitrage window exists to enter before retail volume prices in all catalysts. Set trailing stop at -5% from open."
        elif dominant_direction == "bullish" and total_min >= 8:
            directive = "Moderate-strong gap-up expected. Multiple catalysts compound the move beyond standard beat baseline of +2% to +6%."
            playbook = "Buy the opening range breakout if price holds above the projected open in the first 5 minutes. Target 1.5x the forecast range."
        elif dominant_direction == "bearish" and total_max <= -15:
            directive = "Extreme gap-down profile. Multi-catalyst bearish events with ≥15% forecast rarely recover intraday — selling pressure compounds."
            playbook = "Avoid catching the falling knife. If the opening gap is shallow (above -10%), initiate short positions to capture drift toward projected support."
        else:
            directive = "Standard catalyst reaction. Volatility expected to normalize within the first 30 minutes of open."
            playbook = "Observe initial 5-minute range before committing capital. No edge in pre-market positioning."

        return {
            "forecast_rows": forecast_rows,
            "net_text": net_text,
            "total_min": total_min,
            "total_max": total_max,
            "projected_open":      projected_open,
            "projected_open_low":  projected_open_low,
            "projected_open_high": projected_open_high,
            "dominant_direction": dominant_direction,
            "directive": directive,
            "playbook": playbook,
        }

    # ── Input section ──────────────────────────────────────────────────────────
    st.markdown('<div style="display:flex;align-items:center;margin-bottom:10px"><span class="mb-step-num" style="background:#60a5fa">1</span><span style="color:#60a5fa;font-weight:700;font-size:1rem;">Live News Drop</span></div>', unsafe_allow_html=True)

    def _fetch_price_for_ticker(ticker: str) -> float:
        """Fetch live aftermarket / pre-market price via yfinance."""
        if not YFINANCE_AVAILABLE:
            return 0.0
        try:
            stock = yf.Ticker(ticker)
            price = (
                stock.fast_info.get("lastPrice")
                or stock.fast_info.get("previousClose")
                or 0.0
            )
            return float(price)
        except Exception:
            return 0.0

    def _fetch_url_content(url: str) -> str:
        """
        Fetches article text from a URL (SeekingAlpha, Investing.com, etc).
        Returns cleaned body text suitable for Gemini classification.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # Strip scripts, styles, nav
            import re as _re
            html = _re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
            html = _re.sub(r"<style[^>]*>.*?</style>",  " ", html, flags=_re.DOTALL | _re.IGNORECASE)
            html = _re.sub(r"<nav[^>]*>.*?</nav>",      " ", html, flags=_re.DOTALL | _re.IGNORECASE)
            html = _re.sub(r"<footer[^>]*>.*?</footer>","", html, flags=_re.DOTALL | _re.IGNORECASE)
            # Strip remaining tags
            text = _re.sub(r"<[^>]+>", " ", html)
            # Collapse whitespace
            text = _re.sub(r"\s+", " ", text).strip()
            # Trim to ~4000 chars to stay within Gemini context
            return text[:4000]
        except Exception as e:
            return f"URL_FETCH_ERROR: {e}"

    col1, col2 = st.columns([2, 1])
    with col1:
        news_url_input = st.text_input(
            "Article URL (SeekingAlpha, Investing.com, etc.)",
            placeholder="https://seekingalpha.com/article/... or https://www.investing.com/news/...",
            key="pe_url_input"
        )
        raw_news = st.text_area(
            "Or paste raw news text directly",
            placeholder="Paste the full earnings release, press release, or news headline here...",
            height=100,
            key="pe_news_input"
        )
    with col2:
        pe_ticker_input = st.text_input("Ticker", placeholder="e.g. NVDA", key="pe_ticker_field").strip().upper()
        # Auto-fetch price when ticker is entered
        auto_price = 0.0
        if pe_ticker_input:
            auto_price = _fetch_price_for_ticker(pe_ticker_input)
            if auto_price > 0:
                st.markdown(f'<div class="mb-card"><div class="mb-label">Live Aftermarket Price</div><div style="color:#34d399;font-size:1.4rem;font-weight:800;font-family:monospace">${auto_price:.2f}</div></div>', unsafe_allow_html=True)
            else:
                st.warning("Price unavailable — enter manually")
                auto_price = st.number_input("Manual Price ($)", value=0.0, step=1.0, format="%.2f", key="pe_price_manual")
        predict_btn = st.button("🎯 Analyse Catalysts", type="primary", use_container_width=True, key="pe_analyse_btn")

    if predict_btn:
        st.session_state.pe_classifications = None
        st.session_state.pe_forecast = None
        st.session_state.pe_logged = False
        if not pe_ticker_input:
            st.error("Please enter a ticker symbol.")
        else:
            # Resolve news text — URL takes priority over pasted text
            resolved_news = ""
            if news_url_input.strip().startswith("http"):
                with st.spinner(f"Fetching article from {news_url_input[:60]}…"):
                    resolved_news = _fetch_url_content(news_url_input.strip())
                if resolved_news.startswith("URL_FETCH_ERROR"):
                    st.error(f"Could not fetch URL: {resolved_news}")
                    resolved_news = ""
                elif len(resolved_news) < 80:
                    st.warning("URL returned very little text — falling back to pasted text.")
                    resolved_news = raw_news
                else:
                    st.success(f"Fetched {len(resolved_news):,} characters from article.")
            else:
                resolved_news = raw_news

            if not resolved_news.strip():
                st.error("Please paste news text or enter a valid article URL.")
            else:
                st.session_state.pe_ticker = pe_ticker_input
                st.session_state.pe_price = auto_price
                with st.spinner("Gemini is reading the news and identifying all catalysts…"):
                    cls_list = _gemini_classify_realtime(pe_ticker_input, resolved_news)
                    if cls_list:
                        st.session_state.pe_classifications = cls_list
                        st.session_state.pe_forecast = _build_forecast(cls_list, auto_price)

    # ── Results ────────────────────────────────────────────────────────────────
    if st.session_state.pe_classifications and st.session_state.pe_forecast:
        cls_list = st.session_state.pe_classifications
        fc = st.session_state.pe_forecast
        ticker_disp = st.session_state.pe_ticker
        price_disp = st.session_state.pe_price

        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="display:flex;align-items:center;margin-bottom:12px">'
            f'<span class="mb-step-num" style="background:#60a5fa">2</span>'
            f'<span style="color:#60a5fa;font-weight:700;font-size:1rem;">Catalyst Breakdown</span>'
            f'<span style="color:#6b7280;font-size:0.82rem;margin-left:10px;">{len(cls_list)} catalyst(s) identified for <strong style="color:#e5e7eb">{ticker_disp}</strong></span></div>',
            unsafe_allow_html=True
        )

        rank_labels = {1: "PRIMARY", 2: "SECONDARY", 3: "TERTIARY", 4: "CONTRIBUTING", 5: "CONTRIBUTING"}
        rank_colors = {1: "#60a5fa", 2: "#f59e0b", 3: "#a78bfa", 4: "#6b7280", 5: "#6b7280"}

        for cls in cls_list:
            rank = cls.get("rank", 1)
            r_color = rank_colors.get(rank, "#6b7280")
            r_label = rank_labels.get(rank, "CONTRIBUTING")
            direction = cls.get("direction", "bullish")
            dir_color = "#34d399" if direction == "bullish" else "#f87171"
            dir_icon = "📈" if direction == "bullish" else "📉"
            conf_color = {"High": "#34d399", "Medium": "#fbbf24", "Low": "#f87171"}.get(cls.get("confidence", "Low"), "#9ca3af")

            st.markdown(f"""
            <div class="mb-card" style="border:1px solid {r_color}33;border-left:4px solid {r_color};margin-bottom:8px">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
                    <div style="flex:1">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                            <span style="background:{r_color};color:#000;font-size:0.65rem;font-weight:800;padding:2px 8px;border-radius:999px">{r_label}</span>
                            <span style="color:{r_color};font-size:1.05rem;font-weight:800">{cls.get("classification","—")}</span>
                            <span style="color:{dir_color};font-size:0.8rem">{dir_icon} {direction.capitalize()}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px">Specific Trigger</div>
                        <div style="color:#d1d5db;font-size:0.87rem;margin-bottom:6px">{cls.get("trigger_metric","—")}</div>
                        <div style="color:#6b7280;font-size:0.82rem;font-style:italic">{cls.get("rationale","")}</div>
                    </div>
                    <div style="text-align:right;min-width:100px">
                        <div style="color:#6b7280;font-size:0.72rem;text-transform:uppercase">Weight</div>
                        <div style="color:#e5e7eb;font-weight:700;font-size:1.1rem">{cls.get("weight_pct",0)}%</div>
                        <div style="color:#6b7280;font-size:0.72rem;text-transform:uppercase;margin-top:6px">Confidence</div>
                        <div style="color:{conf_color};font-weight:700">{cls.get("confidence","—")}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Forecast ───────────────────────────────────────────────────────────
        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="display:flex;align-items:center;margin-bottom:12px"><span class="mb-step-num" style="background:#60a5fa">3</span><span style="color:#60a5fa;font-weight:700;font-size:1rem;">Price Forecast</span></div>', unsafe_allow_html=True)

        fc_color = "#34d399" if fc["dominant_direction"] == "bullish" else "#f87171"
        p1, p2, p3 = st.columns(3)
        with p1:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Forecasted Swing</div><div style="color:{fc_color};font-size:1.6rem;font-weight:800;font-family:monospace">{fc["net_text"].split("of ")[-1]}</div></div>', unsafe_allow_html=True)
        with p2:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Projected Open (Midpoint)</div><div style="color:#60a5fa;font-size:1.6rem;font-weight:800;font-family:monospace">${fc["projected_open"]:.2f}</div><div style="color:#6b7280;font-size:0.78rem;margin-top:4px">Floor ${fc["projected_open_low"]:.2f} · Ceiling ${fc["projected_open_high"]:.2f}</div></div>', unsafe_allow_html=True)
        with p3:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Entry Price</div><div style="color:#9ca3af;font-size:1.6rem;font-weight:800;font-family:monospace">${price_disp:.2f}</div></div>', unsafe_allow_html=True)

        # Forecast breakdown table
        st.markdown("<br>", unsafe_allow_html=True)
        for row in fc["forecast_rows"]:
            d_color = "#34d399" if row["direction"] == "bullish" else "#f87171"
            c_min = row["contributed_min"]
            c_max = row["contributed_max"]
            s1 = "+" if c_min >= 0 else ""
            s2 = "+" if c_max >= 0 else ""
            st.markdown(
                f'<div style="display:flex;gap:14px;align-items:center;padding:6px 4px;border-bottom:1px solid #1f2937;flex-wrap:wrap">'
                f'<span style="color:#e5e7eb;font-size:0.88rem;font-weight:700;min-width:220px">{row["classification"]}</span>'
                f'<span style="color:#6b7280;font-size:0.78rem;min-width:55px">{row["weight_pct"]}% weight</span>'
                f'<span style="color:{d_color};font-size:0.82rem;flex:1">{row["db_note"]}</span>'
                f'<span style="color:{d_color};font-family:monospace;font-weight:700;font-size:0.88rem;min-width:120px;text-align:right">{s1}{c_min:.1f}% to {s2}{c_max:.1f}%</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Playbook
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="directive-card"><h4 style="margin:0 0 5px 0;color:#93c5fd;">📋 System Directive</h4><p style="margin:0;font-size:0.93rem;">{fc["directive"]}</p></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="actionable-card"><h4 style="margin:0 0 5px 0;color:#a7f3d0;">⚡ Actionable Playbook</h4><p style="margin:0;font-size:0.93rem;">{fc["playbook"]}</p></div>', unsafe_allow_html=True)

        # ── Phase 3: Auto-log ──────────────────────────────────────────────────
        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="display:flex;align-items:center;margin-bottom:12px"><span class="mb-step-num" style="background:#60a5fa">4</span><span style="color:#60a5fa;font-weight:700;font-size:1rem;">Performance Verification & Auto-Log</span></div>', unsafe_allow_html=True)
        st.caption("After market close, click below to fetch the actual price swing and auto-save qualifying records to the Correlation Database.")

        col_v1, col_v2 = st.columns([1, 2])
        with col_v1:
            verify_btn = st.button("📊 Check Market Close & Auto-Log", type="secondary", use_container_width=True, key="pe_verify_btn", disabled=st.session_state.pe_logged)
        with col_v2:
            if verify_btn and not st.session_state.pe_logged:
                if ticker_disp == "":
                    st.error("No ticker detected.")
                else:
                    with st.spinner(f"Fetching actual close price for {ticker_disp}…"):
                        swings = LiveDataFetcher.check_and_calc_swing(ticker_disp, price_disp)
                    if swings.get("error"):
                        st.error(f"Price check failed: {swings['error']}")
                    else:
                        if swings["meets_5d_threshold"]:
                            actual_swing = swings["swing_5d_pct"]; days_label = "5 Day"
                        elif swings["meets_14d_threshold"]:
                            actual_swing = swings["swing_14d_pct"]; days_label = "14 Day"
                        elif swings["meets_30d_threshold"]:
                            actual_swing = swings["swing_30d_pct"]; days_label = "30 Day"
                        else:
                            actual_swing = None; days_label = ""
                        if actual_swing is not None:
                            sign = "+" if actual_swing >= 0 else ""
                            swing_str = f"{sign}{actual_swing:.2f}% ({days_label})"
                            saved_count = 0
                            rank_labels_save = {1: "PRIMARY", 2: "SECONDARY", 3: "TERTIARY", 4: "CONTRIBUTING", 5: "CONTRIBUTING"}
                            for cls in cls_list:
                                w = cls.get("weight_pct", 100)
                                attr_swing = round(actual_swing * w / 100, 2)
                                attr_sign = "+" if attr_swing >= 0 else ""
                                rl = rank_labels_save.get(cls.get("rank", 1), "CONTRIBUTING")
                                attr_str = f"{attr_sign}{attr_swing:.2f}% ({rl} · {w}% of {sign}{actual_swing:.2f}% {days_label} move)"
                                record = CatalystRecord(
                                    ticker=ticker_disp,
                                    event_type=cls.get("event_type", "Earnings / Catalyst"),
                                    trigger_metric=cls.get("trigger_metric", "Event-Driven Release"),
                                    resulting_swing=attr_str,
                                    classification=cls.get("classification", "Earnings Beat"),
                                    swing_value=attr_swing
                                )
                                system.db.add_record(record)
                                saved_count += 1
                            system.db.save()
                            st.session_state.pe_logged = True
                            st.success(f"✅ Actual swing: **{swing_str}** — {saved_count} catalyst record(s) auto-saved to Correlation Database!")
                        else:
                            st.info(f"Move did not meet threshold. 5-Day: {swings['swing_5d_pct']:+.2f}% | 14-Day: {swings['swing_14d_pct']:+.2f}% | 30-Day: {swings['swing_30d_pct']:+.2f}%. No record saved.")

        if st.session_state.pe_logged:
            st.info("Records logged. Paste a new news drop above to run another prediction.")

    # ── Morning Scan section ───────────────────────────────────────────────────
    st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div style='margin-bottom:12px'>
        <span style='color:#34d399;font-size:1.1rem;font-weight:800;'>🌅 Morning Scan</span>
        <span style='color:#6b7280;font-size:0.88rem;margin-left:10px;'>Select tickers → auto-pull overnight news → classify catalysts → forecast swing</span>
    </div>
    """, unsafe_allow_html=True)

    # ── session state ─────────────────────────────────────────────────────────
    if "ms_results" not in st.session_state:
        st.session_state.ms_results = []
    if "ms_last_run" not in st.session_state:
        st.session_state.ms_last_run = None

    def _fetch_finnhub_news(ticker: str, api_key: str, days_back: int = 2) -> tuple:
        """
        Fetch ticker-specific news headlines from SeekingAlpha (primary)
        with Finnhub as fallback. Returns (articles_list, error_or_None).
        """
        import datetime as dt
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_back)

        # ── Primary: SeekingAlpha news feed ───────────────────────────────────
        try:
            sa_url = f"https://seekingalpha.com/api/sa/combined/{ticker.upper()}.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"https://seekingalpha.com/symbol/{ticker.upper()}/news",
            }
            resp = requests.get(sa_url, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                # SA combined feed has 'news' and 'analysis' keys
                raw_items = data.get("news", []) + data.get("analysis", [])
                articles = []
                for item in raw_items:
                    title    = item.get("title", "") or item.get("headline", "")
                    summary  = item.get("summary", "") or item.get("content", "")
                    pub_date = item.get("publish_on") or item.get("publishOn") or ""
                    source   = item.get("author", {}).get("nick", "SeekingAlpha") if isinstance(item.get("author"), dict) else "SeekingAlpha"
                    if not title:
                        continue
                    articles.append({
                        "headline": title,
                        "summary":  summary[:300],
                        "source":   source,
                        "datetime": 0,
                        "text":     f"{title}. {summary[:300]}".strip()
                    })
                if articles:
                    return articles[:5], None
        except Exception:
            pass  # fall through to Finnhub

        # ── Fallback: Finnhub ─────────────────────────────────────────────────
        try:
            today     = dt.date.today()
            from_date = (today - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
            to_date   = today.strftime("%Y-%m-%d")
            resp = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": from_date, "to": to_date, "token": api_key},
                timeout=10
            )
            resp.raise_for_status()
            raw = resp.json()
            # Filter to ticker-relevant articles only (exclude generic market articles)
            ticker_upper = ticker.upper()
            relevant = [
                a for a in raw
                if ticker_upper in (a.get("headline", "") + a.get("summary", "")).upper()
                or ticker_upper in a.get("related", "").upper()
            ]
            # Fall back to all if filter removes everything
            pool = relevant if len(relevant) >= 2 else raw
            pool = sorted(pool, key=lambda x: x.get("datetime", 0), reverse=True)[:5]
            articles = [
                {
                    "headline": a.get("headline", ""),
                    "summary":  a.get("summary", ""),
                    "source":   a.get("source", "Finnhub"),
                    "datetime": a.get("datetime", 0),
                    "text":     f"{a.get('headline', '')}. {a.get('summary', '')}".strip()
                }
                for a in pool if a.get("headline")
            ]
            return articles, None
        except Exception as e:
            return [], str(e)

    def _fetch_aftermarket_price(ticker: str) -> float:
        """Fetch current extended-hours or last close price via yfinance."""
        try:
            stock = yf.Ticker(ticker)
            price = stock.fast_info.get("lastPrice") or stock.fast_info.get("previousClose") or 0.0
            return float(price)
        except Exception:
            return 0.0

    def _run_morning_scan(watchlist: list, finnhub_key: str, gemini_key: str) -> list:
        """
        Full pipeline: for each ticker, fetch news → classify → forecast.
        Returns list of result dicts, one per ticker.
        """
        results = []
        for ticker in watchlist:
            ticker = ticker.upper()
            result = {
                "ticker": ticker,
                "aftermarket_price": 0.0,
                "news_items": [],
                "all_classifications": [],
                "forecast": None,
                "error": None
            }

            # Step 1 — aftermarket price
            result["aftermarket_price"] = _fetch_aftermarket_price(ticker)

            # Step 2 — news
            news_items, fetch_err = _fetch_finnhub_news(ticker, finnhub_key)
            if fetch_err:
                result["error"] = f"Finnhub fetch error: {fetch_err}"
                results.append(result)
                continue
            if not news_items:
                result["error"] = "No recent news found on Finnhub (past 48h)"
                results.append(result)
                continue
            result["news_items"] = news_items

            # Step 3 — classify all news items via Gemini, merge classifications
            all_cls = []
            for article in news_items:
                if not article["text"].strip():
                    continue
                prompt = f"""You are a quantitative event-driven analyst reviewing a live news drop for {ticker}.

News:
---
{article['text']}
---

Identify ALL distinct catalysts present. Return ONLY a valid JSON array (no markdown, no preamble):

[
  {{
    "rank": 1,
    "event_type": "<Earnings / Catalyst | Macro / Sector | Clinical Data / Regulatory | Corporate Action | Guidance Cut>",
    "trigger_metric": "<1-2 sentence description of this specific catalyst with key numbers>",
    "classification": "<Forward Guidance Hike | Structural Short Squeeze | Hyper-Specific Narrative Validation | Sector Sympathy Rally | Supply Chain Failure | Dividend Suspension / Capital Flight | Earnings Beat | Earnings Miss | Earnings Beat / Product Hype | Binary Pipeline Success | Mega-Contract Visibility | EBITDA Inflection | Sector Macro Tailwind>",
    "weight_pct": <integer, all must sum to 100>,
    "direction": "<bullish | bearish>",
    "confidence": "<High | Medium | Low>",
    "rationale": "<1 sentence why this catalyst matters>"
  }}
]

Rules: 1-5 catalysts only. Each must have a unique classification. weight_pct must sum to 100."""

                try:
                    resp = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:generateContent?key={gemini_key}",
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=30
                    )
                    resp.raise_for_status()
                    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    raw = re.sub(r"```json|```", "", raw).strip()
                    cls_list = json.loads(raw)
                    if isinstance(cls_list, dict):
                        cls_list = [cls_list]
                    for c in cls_list:
                        c["source_headline"] = article["headline"]
                    all_cls.extend(cls_list)
                except Exception as _gem_err:
                    result.setdefault("gemini_errors", []).append(str(_gem_err))
                    continue

            if not all_cls:
                gem_errors = result.get("gemini_errors", [])
                err_detail = f" Errors: {'; '.join(gem_errors[:2])}" if gem_errors else ""
                news_texts = [a["text"][:80] for a in news_items[:2]]
                result["error"] = f"Gemini classification returned no results.{err_detail} | News sample: {news_texts}"
                results.append(result)
                continue

            # Deduplicate classifications — keep highest weight per classification type
            seen = {}
            for c in all_cls:
                cls_name = c.get("classification", "")
                if cls_name not in seen or c.get("weight_pct", 0) > seen[cls_name].get("weight_pct", 0):
                    seen[cls_name] = c
            merged_cls = list(seen.values())

            # Re-normalise weights to 100
            total_w = sum(c.get("weight_pct", 0) for c in merged_cls)
            if total_w > 0 and total_w != 100:
                for c in merged_cls:
                    c["weight_pct"] = round(c.get("weight_pct", 0) * 100 / total_w)
                diff = 100 - sum(c["weight_pct"] for c in merged_cls)
                merged_cls[0]["weight_pct"] += diff

            result["all_classifications"] = sorted(merged_cls, key=lambda x: x.get("weight_pct", 0), reverse=True)

            # Step 4 — forecast using existing _build_forecast logic
            price = result["aftermarket_price"]
            forecast_rows = []
            total_min = 0.0
            total_max = 0.0
            bearish_weight = sum(c.get("weight_pct", 0) for c in merged_cls if c.get("direction") == "bearish")
            dominant_direction = "bearish" if bearish_weight > 50 else "bullish"

            for c in merged_cls:
                cls_name = c.get("classification", "")
                weight = c.get("weight_pct", 0) / 100.0
                direction = c.get("direction", "bullish")
                matches = system.db.find_matches_by_classification(cls_name)
                if matches:
                    swings = [r.swing_value for r in matches]
                    avg_swing = sum(swings) / len(swings)
                    contributed_min = min(swings) * weight
                    contributed_max = max(swings) * weight
                    db_note = f"DB ({len(matches)} match{'es' if len(matches)>1 else ''}): avg {avg_swing:+.1f}%"
                else:
                    if cls_name == "Forward Guidance Hike":
                        contributed_min, contributed_max = 12.0 * weight, 20.0 * weight
                    elif cls_name in ("Structural Short Squeeze", "Hyper-Specific Narrative Validation"):
                        contributed_min, contributed_max = 15.0 * weight, 30.0 * weight
                    elif direction == "bearish":
                        contributed_min, contributed_max = -20.0 * weight, -10.0 * weight
                    else:
                        contributed_min, contributed_max = 2.0 * weight, 6.0 * weight
                    db_note = "No DB match — rule estimate"
                total_min += contributed_min
                total_max += contributed_max
                forecast_rows.append({
                    "classification": cls_name,
                    "weight_pct": c.get("weight_pct", 0),
                    "direction": direction,
                    "db_note": db_note,
                    "contributed_min": contributed_min,
                    "contributed_max": contributed_max,
                })

            sign_min = "+" if total_min >= 0 else ""
            sign_max = "+" if total_max >= 0 else ""
            if dominant_direction == "bullish" and total_min > 0:
                net_text = f"{sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}% Gap Up"
            elif dominant_direction == "bearish" and total_max < 0:
                net_text = f"{sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}% Gap Down"
            else:
                net_text = f"{sign_min}{total_min:.1f}% to {sign_max}{total_max:.1f}%"

            result["forecast"] = {
                "forecast_rows": forecast_rows,
                "net_text": net_text,
                "total_min": total_min,
                "total_max": total_max,
                "projected_open":      price * (1 + ((total_min + total_max) / 2.0) / 100.0) if price > 0 else 0.0,
                "projected_open_low":  price * (1 + total_min / 100.0) if price > 0 else 0.0,
                "projected_open_high": price * (1 + total_max / 100.0) if price > 0 else 0.0,
                "dominant_direction": dominant_direction,
            }
            results.append(result)
        return results

    # ── UI ────────────────────────────────────────────────────────────────────
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.warning("Your watchlist is empty. Add tickers in the sidebar first.")
    else:
        finnhub_key = st.secrets.get("FINNHUB_API_KEY", "") or os.environ.get("FINNHUB_API_KEY", "")
        gemini_key  = st.secrets.get("GEMINI_API_KEY",  "") or os.environ.get("GEMINI_API_KEY",  "")

        if not finnhub_key:
            st.error("FINNHUB_API_KEY not found in Streamlit secrets. Add it under Settings → Secrets.")
        if not gemini_key:
            st.error("GEMINI_API_KEY not found in Streamlit secrets.")

        # ── Ticker selector ───────────────────────────────────────────────────
        selected_tickers = st.multiselect(
            "Select tickers to scan",
            options=watchlist,
            default=[],
            placeholder="Choose one or more tickers…"
        )

        col_btn, col_clear, col_info = st.columns([1, 1, 3])
        with col_btn:
            run_scan = st.button(
                f"🔄 Run Scan ({len(selected_tickers)} ticker{'s' if len(selected_tickers) != 1 else ''})",
                type="primary",
                use_container_width=True,
                disabled=len(selected_tickers) == 0
            )
        with col_clear:
            clear_results = st.button("🗑️ Clear All", use_container_width=True)
        with col_info:
            if st.session_state.ms_last_run:
                scanned = list({r["ticker"] for r in st.session_state.ms_results})
                st.caption(f"Last run: {st.session_state.ms_last_run}  ·  {len(scanned)} ticker(s) in table  ·  Covers past 48h of news")
            else:
                st.caption("Covers past 48h of news  ·  Results accumulate across scans  ·  Run at 9:15am GMT-4 before market open")

        if clear_results:
            st.session_state.ms_results = []
            st.session_state.ms_last_run = None
            st.rerun()

        if run_scan and finnhub_key and gemini_key and selected_tickers:
            with st.spinner(f"Scanning {len(selected_tickers)} ticker(s) — fetching news, classifying catalysts, building forecasts…"):
                new_results = _run_morning_scan(selected_tickers, finnhub_key, gemini_key)
                import datetime as _dt
                st.session_state.ms_last_run = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Merge into existing results — overwrite by ticker key so re-scanning updates in place
                existing = {r["ticker"]: r for r in st.session_state.ms_results}
                for r in new_results:
                    existing[r["ticker"]] = r
                st.session_state.ms_results = list(existing.values())

            st.success(f"Scan complete — {len(new_results)} ticker(s) added/updated. Table now shows {len(st.session_state.ms_results)} ticker(s) total.")

        # ── Summary table ─────────────────────────────────────────────────────
        if st.session_state.ms_results:
            st.markdown("### 📊 Pre-Market Summary")
            summary_rows = []
            for r in st.session_state.ms_results:
                if r.get("error") and not r.get("forecast"):
                    summary_rows.append({
                        "Ticker": r["ticker"],
                        "Aftermarket Price": f"${r['aftermarket_price']:.2f}" if r["aftermarket_price"] else "—",
                        "Forecast Swing": r["error"],
                        "Projected Open": "—",
                        "Catalysts": "—",
                        "Direction": "—",
                    })
                else:
                    fc = r["forecast"]
                    cls_tags = " · ".join(
                        f"{c['classification']} ({c['weight_pct']}%)"
                        for c in r["all_classifications"]
                    )
                    color = "🟢" if fc["dominant_direction"] == "bullish" else "🔴"
                    summary_rows.append({
                        "Ticker": r["ticker"],
                        "Aftermarket Price": f"${r['aftermarket_price']:.2f}" if r["aftermarket_price"] else "—",
                        "Forecast Swing": f"{color} {fc['net_text']}",
                        "Projected Open": f"${fc['projected_open']:.2f} (${fc['projected_open_low']:.2f}–${fc['projected_open_high']:.2f})" if fc["projected_open"] else "—",
                        "Catalysts": cls_tags,
                        "Direction": fc["dominant_direction"].capitalize(),
                    })

            st.dataframe(
                pd.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ticker":           st.column_config.TextColumn(width="small"),
                    "Aftermarket Price":st.column_config.TextColumn(width="small"),
                    "Forecast Swing":   st.column_config.TextColumn(width="medium"),
                    "Projected Open":   st.column_config.TextColumn(width="small"),
                    "Catalysts":        st.column_config.TextColumn(width="large"),
                    "Direction":        st.column_config.TextColumn(width="small"),
                }
            )

            # ── Per-ticker breakdown ──────────────────────────────────────────
            st.markdown("### 🔍 Catalyst Breakdown by Ticker")
            for r in st.session_state.ms_results:
                ticker_color = "#34d399" if (r.get("forecast") and r["forecast"]["dominant_direction"] == "bullish") else "#f87171"
                with st.expander(f"**{r['ticker']}** — {r['forecast']['net_text'] if r.get('forecast') else r.get('error','No data')}", expanded=False):
                    if r.get("error") and not r.get("forecast"):
                        st.warning(r["error"])
                        continue

                    fc = r["forecast"]
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Aftermarket Price", f"${r['aftermarket_price']:.2f}" if r["aftermarket_price"] else "—")
                    col_b.metric("Forecast Swing", fc["net_text"])
                    col_c.metric("Projected Open (Mid)", f"${fc['projected_open']:.2f}" if fc["projected_open"] else "—",
                                 delta=f"Floor ${fc['projected_open_low']:.2f} · Ceil ${fc['projected_open_high']:.2f}")

                    st.markdown("**Catalyst Classification Breakdown**")
                    cls_rows = []
                    for c in r["all_classifications"]:
                        cls_rows.append({
                            "Classification":  c["classification"],
                            "Weight":          f"{c['weight_pct']}%",
                            "Direction":       c["direction"].capitalize(),
                            "Confidence":      c.get("confidence", "—"),
                            "DB Note":         next((f["db_note"] for f in fc["forecast_rows"] if f["classification"] == c["classification"]), "—"),
                            "Swing Contribution": f"{next((f['contributed_min'] for f in fc['forecast_rows'] if f['classification'] == c['classification']), 0):+.1f}% to {next((f['contributed_max'] for f in fc['forecast_rows'] if f['classification'] == c['classification']), 0):+.1f}%",
                            "Trigger":         c.get("trigger_metric", "—"),
                        })
                    st.dataframe(pd.DataFrame(cls_rows), use_container_width=True, hide_index=True)

                    st.markdown("**News Articles Analysed**")
                    for article in r["news_items"]:
                        import datetime as _dt2
                        ts = _dt2.datetime.fromtimestamp(article["datetime"]).strftime("%Y-%m-%d %H:%M") if article.get("datetime") else ""
                        st.markdown(f"- **{article['headline']}** _{article.get('source','')} {ts}_")

# ==========================================
# TAB 2: SCHEDULER & WATCHLIST
# ==========================================
with tab_schedule:
    st.subheader("Event Scheduler & Calendar Automation (Phase 1)")
    col_sync1, col_sync2 = st.columns([1, 3])
    with col_sync1:
        sync_calendar = st.button("Sync Watchlist with Yahoo Finance 🌐", type="primary", use_container_width=True)
    with col_sync2:
        st.write("Clicking sync will fetch the live next-scheduled earnings and dividend dates.")

    if sync_calendar:
        updated_events = []
        progress_bar = st.progress(0, text="Syncing with Yahoo Finance. Please wait...")
        tickers = st.session_state.watchlist
        total_tickers = len(tickers)
        
        if total_tickers == 0:
            st.warning("Your Watchlist is empty. Add tickers in the Sidebar first!")
        else:
            for i, ticker in enumerate(tickers):
                progress_bar.progress((i + 1) / total_tickers, text=f"Querying live metadata for {ticker} ({i+1}/{total_tickers})...")
                live_data = LiveDataFetcher.fetch_upcoming_events(ticker)
                
                if live_data["earnings_date"] != "No Data Found" and "Failed" not in live_data["earnings_date"]:
                    updated_events.append({"ticker": ticker, "event_type": "Earnings", "timing": live_data["earnings_date"]})
                if live_data["ex_dividend_date"] != "No Data Found" and "Failed" not in live_data["ex_dividend_date"]:
                    updated_events.append({"ticker": ticker, "event_type": "Ex-Dividend", "timing": live_data["ex_dividend_date"]})
            
            progress_bar.empty()
            st.session_state.upcoming_events = updated_events
            save_upcoming_events(updated_events)
            st.success(f"Calendar successfully synced! Logged {len(updated_events)} upcoming catalyst events.")

    st.markdown("### 📅 Pre-Scheduled Upcoming Events Grid")

    # ── Event type metadata ────────────────────────────────────────────────────
    EVENT_TYPE_META = {
        "Earnings": {
            "monitoring_window": "2–3 weeks prior",
            "impact": "Sharp gap risk, IV expansion, PEAD",
            "strategy": "Avoid unhedged high-beta positions through binary prints",
            "placeholder_note": "e.g. NVDA Q3 2026 Earnings",
            "example_notes": "Q3 FY2026 results + CapEx guidance. Watch for datacenter revenue beat vs consensus $34.5B."
        },
        "Ex-Dividend": {
            "monitoring_window": "1 week prior",
            "impact": "Price adjusts down by dividend amount on ex-date",
            "strategy": "Capture dividend or avoid holding through if short",
            "placeholder_note": "e.g. AAPL quarterly dividend",
            "example_notes": "$0.25/share quarterly dividend. Stock price adjustment on ex-date."
        },
        "Industry Expo / Keynote": {
            "monitoring_window": "1–2 weeks prior",
            "impact": "Pre-conference momentum rally, sell-the-news risk post-event",
            "strategy": "Buy the rumor during early accumulation; tighten trailing stops into keynote day",
            "placeholder_note": "e.g. COMPUTEX 2026, GTC, CES",
            "example_notes": "NVIDIA GTC 2026 keynote. Jensen expected to announce next-gen Blackwell Ultra. Watch for pre-event AI sector sympathy rallies."
        },
        "Index Rebalancing": {
            "monitoring_window": "3–4 weeks prior (announcement to reconstitution date)",
            "impact": "Massive mechanical volume spikes from passive funds, post-inclusion liquidity drop",
            "strategy": "Front-run passive inflows; take profit near effective inclusion date",
            "placeholder_note": "e.g. S&P 500 inclusion, Russell 2000 rebalance",
            "example_notes": "CRWV added to S&P 500 effective Sep 22. Expect $4–6B in passive fund inflows. Sell into index effective date."
        },
        "Legal / Regulatory Milestone": {
            "monitoring_window": "1–2 weeks prior",
            "impact": "Asymmetric relief rally on expiry, sharp selloff on injunction filing",
            "strategy": "Monitor court docket deadlines to time volatility contraction and short-squeeze relief rallies",
            "placeholder_note": "e.g. Antitrust ruling, lead plaintiff deadline, FDA decision",
            "example_notes": "GOOGL antitrust remedies hearing Oct 8. DOJ pushing for Chrome divestiture. Binary outcome — relief rally if dismissed, -15%+ if injunction filed."
        },
    }

    EVENT_COLORS = {
        "Earnings":                    "#f59e0b",
        "Ex-Dividend":                 "#60a5fa",
        "Industry Expo / Keynote":     "#a78bfa",
        "Index Rebalancing":           "#34d399",
        "Legal / Regulatory Milestone":"#f87171",
    }

    if st.session_state.upcoming_events:
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        future_events = [
            e for e in st.session_state.upcoming_events
            if re.match(r"^\d{4}-\d{2}-\d{2}$", str(e.get("timing", "")))
            and str(e.get("timing", "")) >= today_str
        ]
        if future_events:
            sorted_events = sorted(future_events, key=lambda x: x.get("timing", "9999-12-31"))

            # Render grid with colour-coded event type badges
            st.markdown("""
            <style>
            .evt-badge { padding:2px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; display:inline-block; }
            .evt-row { display:flex; align-items:center; gap:14px; padding:8px 4px; border-bottom:1px solid #1f2937; }
            .evt-ticker { color:#e5e7eb; font-weight:800; font-family:monospace; font-size:0.95rem; min-width:60px; }
            .evt-date { color:#6b7280; font-size:0.82rem; min-width:90px; }
            .evt-notes { color:#9ca3af; font-size:0.80rem; flex:1; }
            </style>
            """, unsafe_allow_html=True)

            for evt in sorted_events:
                etype = evt.get("event_type", "Earnings")
                color = EVENT_COLORS.get(etype, "#6b7280")
                notes = evt.get("notes", "")
                meta = EVENT_TYPE_META.get(etype, {})
                strategy_tip = meta.get("strategy", "")
                notes_display = notes if notes else f'<span style="color:#4b5563;font-style:italic">{strategy_tip}</span>'
                st.markdown(
                    f'<div class="evt-row">'
                    f'<span class="evt-ticker">{evt.get("ticker","")}</span>'
                    f'<span class="evt-badge" style="background:{color}22;color:{color}">{etype}</span>'
                    f'<span class="evt-date">📅 {evt.get("timing","")}</span>'
                    f'<span class="evt-notes">{notes_display}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            st.markdown("<br>", unsafe_allow_html=True)
            st.caption(f"Showing {len(future_events)} upcoming event(s). Past dates are automatically hidden.")
        else:
            st.info("No upcoming events — all scheduled dates have passed. Sync with Yahoo Finance to refresh.")

        if st.button("Reset Calendar Schedule"):
            st.session_state.upcoming_events = []
            save_upcoming_events([])
            st.rerun()
    else:
        st.info("No pre-scheduled dates currently loaded.")

    # ── Add New Event Form ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ➕ Add Catalyst Event")

    with st.expander("Add a new event to the calendar", expanded=False):
        fc1, fc2 = st.columns([1, 1])
        with fc1:
            form_ticker = st.text_input("Ticker", placeholder="e.g. NVDA", key="form_evt_ticker").upper().strip()
        with fc2:
            form_etype = st.selectbox(
                "Event Type",
                list(EVENT_TYPE_META.keys()),
                key="form_evt_type"
            )

        form_date = st.date_input("Scheduled Date", key="form_evt_date", value=datetime.date.today())

        # Show example dynamically based on selected event type
        meta = EVENT_TYPE_META[form_etype]
        st.markdown(f"""
        <div style="background:#111827;border:1px solid #374151;border-left:3px solid {EVENT_COLORS.get(form_etype,'#6b7280')};border-radius:6px;padding:12px 14px;margin:8px 0 12px 0">
            <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px">
                <div><span style="color:#6b7280;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em">Monitoring Window</span><br>
                     <span style="color:#e5e7eb;font-size:0.85rem">{meta['monitoring_window']}</span></div>
                <div><span style="color:#6b7280;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em">Market Impact</span><br>
                     <span style="color:#e5e7eb;font-size:0.85rem">{meta['impact']}</span></div>
            </div>
            <div><span style="color:#6b7280;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em">Core Strategy</span><br>
                 <span style="color:#9ca3af;font-size:0.83rem">{meta['strategy']}</span></div>
        </div>
        """, unsafe_allow_html=True)

        form_notes = st.text_area(
            "Event Notes (optional)",
            placeholder=meta["example_notes"],
            height=80,
            key="form_evt_notes"
        )

        add_evt_btn = st.button("➕ Add to Calendar", type="primary", key="add_evt_btn")

        if add_evt_btn:
            if not form_ticker:
                st.error("Please enter a ticker symbol.")
            else:
                new_evt = {
                    "ticker": form_ticker,
                    "event_type": form_etype,
                    "timing": form_date.strftime("%Y-%m-%d"),
                    "notes": form_notes.strip()
                }
                st.session_state.upcoming_events.append(new_evt)
                save_upcoming_events(st.session_state.upcoming_events)
                st.success(f"✅ {form_ticker} — {form_etype} on {form_date} added to calendar.")
                st.rerun()

# ==========================================
# TAB 3: HISTORICAL CORRELATION DATABASE
# ==========================================
with tab_database:
    st.subheader("🗄️ Historical Correlation Database")
    st.write("This database acts as the system's baseline ground-truth. You can view, add, or edit historical event-driven triggers.")

    records_list = [{"Ticker": r.ticker, "Event Type": r.event_type, "Trigger Metric": r.trigger_metric, "Resulting Swing": r.resulting_swing, "Classification": r.classification, "Swing Value (%)": r.swing_value} for r in system.db.records]
    st.dataframe(pd.DataFrame(records_list), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.info(
        "**⚡ Want to log a new historical event?**\n\n"
        "Use the **🧠 Memory Bank** tab — it runs the same yfinance price fetch, "
        "then sends the news to Gemini for multi-catalyst classification with weighted swing attribution, "
        "before saving to this database.\n\n"
        "The old single-catalyst pipeline here has been retired in favour of that richer workflow.",
        icon="👆"
    )
    st.markdown("---")
    with st.expander("✍️ Manual Data Entry Override"):
        with st.form("add_record_form"):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                new_ticker = st.text_input("Ticker", placeholder="AAPL").upper()
                new_event = st.text_input("Event Type", placeholder="Earnings / Product Launch")
            with col_f2:
                new_trigger = st.text_input("Specific Trigger Metric", placeholder="Beat Revenue estimates by 15%")
                new_swing_str = st.text_input("Resulting Price Swing String", placeholder="+12.45% (1 Day)")
            with col_f3:
                new_class = st.selectbox("Catalyst Classification", ["Forward Guidance Hike", "Structural Short Squeeze", "Hyper-Specific Narrative Validation", "Sector Sympathy Rally", "Supply Chain Failure", "Dividend Suspension / Capital Flight", "Earnings Beat", "Earnings Miss", "Earnings Beat / Product Hype"])
                new_swing_val = st.number_input("Numeric Price Swing (%)", value=0.0, step=0.1)

            submit_record = st.form_submit_button("Force Manual Record Override")
            
            if submit_record:
                if new_ticker and new_event and new_trigger:
                    new_record = CatalystRecord(ticker=new_ticker, event_type=new_event, trigger_metric=new_trigger, resulting_swing=new_swing_str if new_swing_str else f"{new_swing_val:+.2f}% (1 Day)", classification=new_class, swing_value=new_swing_val)
                    system.db.add_record(new_record)
                    system.db.save()
                    st.success(f"Successfully added {new_ticker} manually!")
                    st.rerun()
                else:
                    st.error("Please fill out all required fields.")
# ==========================================
# TAB 4: MEMORY BANK
# ==========================================

# ── helpers ────────────────────────────────────────────────────────────────────

def _classify_catalyst_with_gemini(ticker: str, swing_pct: float, days: int, news_text: str) -> list:
    """
    Sends the price swing + raw news to Gemini and returns a LIST of classification dicts,
    one per distinct catalyst present in the news. Ranked by impact (primary first).
    Each dict: {event_type, trigger_metric, classification, confidence, rationale, rank}
    Falls back to rule-based extraction if the API call fails.
    """
    prompt = f"""You are a quantitative event-driven analyst. A stock ({ticker}) moved {swing_pct:+.2f}% over {days} trading day(s).

The following catalyst news caused that move:
---
{news_text}
---

A single price event can be driven by MULTIPLE distinct catalysts simultaneously. Identify ALL catalysts present and estimate how much of the total price move each one was responsible for.

Return ONLY a valid JSON array (no markdown fences, no preamble). Each element represents one distinct catalyst, ranked by impact (most impactful first):

[
  {{
    "rank": 1,
    "weight_pct": 45,
    "event_type": "<one of: Earnings / Catalyst | Macro / Sector | Clinical Data / Regulatory | Corporate Action | Guidance Cut>",
    "trigger_metric": "<concise 1-2 sentence description of THIS SPECIFIC catalyst. Include numbers where present.>",
    "classification": "<one of: Forward Guidance Hike | Structural Short Squeeze | Hyper-Specific Narrative Validation | Sector Sympathy Rally | Supply Chain Failure | Dividend Suspension / Capital Flight | Earnings Beat | Earnings Miss | Earnings Beat / Product Hype | Binary Pipeline Success | Mega-Contract Visibility | EBITDA Inflection | Sector Macro Tailwind>",
    "confidence": "<High | Medium | Low>",
    "rationale": "<1 sentence explaining why this specific catalyst drove the move>"
  }}
]

Rules:
- Include between 1 and 5 catalysts. Only include real, distinct drivers — do not pad.
- Each catalyst must have a different classification.
- The primary (rank 1) catalyst is the single biggest driver of the move.
- If only one catalyst is present, return an array with one element.
- weight_pct is an integer (0–100) representing each catalyst's estimated share of the total price swing. All weight_pct values MUST sum to exactly 100."""

    try:
        # Resolve API key: Streamlit secrets → environment variable
        api_key = os.environ.get("GEMINI_API_KEY", "")
        try:
            api_key = st.secrets.get("GEMINI_API_KEY", "") or api_key
        except Exception:
            pass  # No secrets.toml — fall back to env var (or empty)
        if not api_key:
            raise ValueError(
                "No Gemini API key found. Add GEMINI_API_KEY to your "
                ".streamlit/secrets.toml or as an environment variable."
            )

        # Gemini REST endpoint — gemini-3.7-flash is the current stable Flash model
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.7-flash:generateContent?key={api_key}"
        )
        resp = requests.post(
            gemini_url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 4000, "temperature": 0.2}
            },
            timeout=60
        )
        resp.raise_for_status()
        raw_resp = resp.json()
        if not raw_resp.get("candidates"):
            raise ValueError(f"Gemini returned no candidates: {raw_resp}")
        raw = raw_resp["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        if not raw.endswith("]"):
            raw = raw[:raw.rfind("}") + 1] + "]"
        result = json.loads(raw)
        # Ensure it's always a list
        if isinstance(result, dict):
            result = [result]
        # Ensure rank field exists
        for i, item in enumerate(result):
            if "rank" not in item:
                item["rank"] = i + 1
        result = sorted(result, key=lambda x: x.get("rank", 99))

        # Normalise weights so they always sum to 100, then attach weighted swing
        total_w = sum(item.get("weight_pct", 0) for item in result)
        if total_w == 0:
            # Fallback: equal weighting when Gemini omitted weights
            equal = round(100 / len(result))
            for item in result:
                item["weight_pct"] = equal
            total_w = equal * len(result)
        for item in result:
            w = item.get("weight_pct", 0)
            # Normalise to true 100 in case of rounding drift
            normalised_w = w / total_w * 100
            item["weight_pct"] = round(normalised_w)
            item["weighted_swing"] = round(swing_pct * normalised_w / 100, 2)

        # Fix any rounding residual so the displayed weights sum cleanly to 100
        diff = 100 - sum(item["weight_pct"] for item in result)
        if diff != 0:
            result[0]["weight_pct"] += diff  # absorb residual into primary catalyst

        return result
    except Exception as e:
        # Rule-based fallback — returns a list with one item
        parsed = EventParser.parse_data_drop(news_text)
        metrics = parsed.get("metrics", {})
        parts = []
        if "revenue" in metrics:
            parts.append(f"Rev {metrics['revenue'].get('amount','')} ({metrics['revenue'].get('change','Beat')})")
        if "eps" in metrics:
            parts.append(f"EPS {metrics['eps'].get('amount','')} ({metrics['eps'].get('beat','Beat')})")
        if "guidance" in metrics:
            parts.append(f"Guidance {metrics['guidance'].get('action','')} by {metrics['guidance'].get('amount','')}")
        trigger = " AND ".join(parts) if parts else "Event-Driven Release"

        if "guidance" in metrics and metrics["guidance"].get("action") == "raised":
            cls = "Forward Guidance Hike"
        elif "guidance" in metrics and metrics["guidance"].get("action") == "lowered":
            cls = "Supply Chain Failure" if "supply" in news_text.lower() else "Guidance Cut"
        elif "narrative" in metrics:
            cls = metrics["narrative"]
        else:
            cls = "Earnings Beat" if swing_pct >= 0 else "Earnings Miss"

        return [{
            "rank": 1,
            "weight_pct": 100,
            "weighted_swing": round(swing_pct, 2),
            "event_type": "Earnings / Catalyst",
            "trigger_metric": trigger,
            "classification": cls,
            "confidence": "Low",
            "rationale": f"Rule-based fallback (Gemini API error: {e})"
        }]


def _score_watchlist_matches(new_classification: str, new_swing_val: float, new_trigger: str) -> list:
    """
    Scans upcoming_events against the DB for pattern-matched alert candidates.
    Returns a list of dicts {ticker, event_type, timing, match_reason, alert_level}.
    """
    alerts = []
    upcoming = st.session_state.upcoming_events
    db_records = system.db.records

    explosive_classes = {
        "Forward Guidance Hike", "Structural Short Squeeze",
        "Hyper-Specific Narrative Validation", "Sector Sympathy Rally"
    }
    is_explosive = new_classification in explosive_classes
    trigger_lower = new_trigger.lower()

    ai_infra_keywords = ["gpu", "ai infrastructure", "data center", "hpc", "hyperscaler", "computing capacity"]
    guidance_keywords = ["guidance raised", "outlook raised", "raised guidance", "targets raised"]
    revenue_5x_keywords = ["5x", "multiplied", "5-fold", "quintupled", "500%"]
    ebitda_positive_keywords = ["ebitda", "positive", "profitability", "margin"]
    contract_keywords = ["billion", "contract", "deal", "visibility", "backlog"]

    for evt in upcoming:
        ticker = evt.get("ticker", "")
        event_type = evt.get("event_type", "")
        timing = evt.get("timing", "")

        # Only flag upcoming Earnings events for catalyst pattern matching
        if event_type != "Earnings":
            continue

        reasons = []
        alert_level = None

        # Check if any same-ticker historical record shares the classification
        ticker_history = [r for r in db_records if r.ticker == ticker]
        for r in ticker_history:
            if r.classification == new_classification:
                reasons.append(f"Ticker has prior {new_classification} event ({r.resulting_swing})")

        # Sector sympathy: AI infra keywords present → flag AI-adjacent tickers
        if is_explosive and any(kw in trigger_lower for kw in ai_infra_keywords):
            ai_adjacent = {"NVDA", "MRVL", "MSFT", "GOOG", "META", "AMZN", "CRWV", "SMCI", "NBIS", "NOW", "IREN"}
            if ticker in ai_adjacent:
                reasons.append("AI-infrastructure sector sympathy candidate")

        # Guidance raise pattern match
        if new_classification == "Forward Guidance Hike" and any(kw in trigger_lower for kw in guidance_keywords):
            reasons.append("Pattern match: Forward Guidance Hike — historically triggers gap-up >12%")

        # Hypergrowth revenue match (5x or extreme YoY)
        if any(kw in trigger_lower for kw in revenue_5x_keywords):
            reasons.append("Hyper-growth revenue signal (>5x YoY) — rare catalyst with explosive precedent")

        # EBITDA inflection
        if all(kw in trigger_lower for kw in ["ebitda"]) and any(kw in trigger_lower for kw in ebitda_positive_keywords):
            reasons.append("EBITDA inflection to positive — monetisation proof catalyst")

        # Mega-contract visibility
        if any(kw in trigger_lower for kw in contract_keywords) and "billion" in trigger_lower:
            reasons.append("Multi-billion contract visibility — backlog-driven re-rating catalyst")

        if not reasons:
            continue

        # Assign alert level
        if len(reasons) >= 3 or abs(new_swing_val) >= 30:
            alert_level = "🔴 HIGH"
        elif len(reasons) >= 2 or abs(new_swing_val) >= 15:
            alert_level = "🟡 MEDIUM"
        else:
            alert_level = "🟢 WATCH"

        alerts.append({
            "ticker": ticker,
            "event_type": event_type,
            "timing": timing,
            "match_reasons": reasons,
            "alert_level": alert_level
        })

    # Deduplicate by ticker, keeping highest severity
    seen = {}
    priority = {"🔴 HIGH": 3, "🟡 MEDIUM": 2, "🟢 WATCH": 1}
    for a in alerts:
        t = a["ticker"]
        if t not in seen or priority[a["alert_level"]] > priority[seen[t]["alert_level"]]:
            seen[t] = a

    return sorted(seen.values(), key=lambda x: priority[x["alert_level"]], reverse=True)


def _scan_for_rule_candidates() -> list:
    """
    After every save, scans the full DB for classifications where:
      - 3+ records ALL produced an absolute swing >= 15% (either direction)
      - The classification is NOT already a known system rule
    Returns list of dicts: {classification, record_count, avg_swing, examples, direction}
    """
    KNOWN_RULES = {
        "Forward Guidance Hike",
        "Structural Short Squeeze",
        "Hyper-Specific Narrative Validation",
    }

    # Load dismissed suggestions from session state so they stay gone
    dismissed = st.session_state.get("mb_dismissed_rules", set())

    from collections import defaultdict
    buckets = defaultdict(list)
    for r in system.db.records:
        if abs(r.swing_value) >= 15.0:
            buckets[r.classification].append(r)

    candidates = []
    for cls, records in buckets.items():
        if len(records) < 3:
            continue
        if cls in KNOWN_RULES:
            continue
        if cls in dismissed:
            continue

        swings = [r.swing_value for r in records]
        avg = sum(swings) / len(swings)
        # Determine dominant direction
        positives = sum(1 for s in swings if s > 0)
        direction = "gap-up" if positives >= len(swings) / 2 else "gap-down"
        examples = [f"{r.ticker} ({'+' if r.swing_value > 0 else ''}{r.swing_value:.1f}%)" for r in records[:4]]

        candidates.append({
            "classification": cls,
            "record_count": len(records),
            "avg_swing": avg,
            "examples": examples,
            "direction": direction,
        })

    # Sort by record count desc, then avg abs swing desc
    candidates.sort(key=lambda x: (x["record_count"], abs(x["avg_swing"])), reverse=True)
    return candidates


def _promote_rule(classification: str, direction: str, avg_swing: float):
    """
    Writes the new rule into Catalyst_Correlations.md's System Correlation Rules section.
    Also updates the in-memory system DB rules text.
    """
    rule_line = (
        f"- **{classification}**: Consistently produces extreme "
        f"{'gap-ups' if direction == 'gap-up' else 'gap-downs'} "
        f"(avg {'+' if avg_swing > 0 else ''}{avg_swing:.1f}%) — "
        f"promoted from pattern analysis (≥3 qualifying events)."
    )

    # Read current file
    with open(system.db.filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Append the new rule line before the end of the rules section
    if "## System Correlation Rules" in content:
        content = content.rstrip() + "\n" + rule_line + "\n"
    else:
        content += f"\n## System Correlation Rules\n{rule_line}\n"

    with open(system.db.filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # Also update the Extreme Gap threshold description dynamically
    # so PredictiveEngine.find_matches_by_classification picks it up on next query
    system.db.load_from_markdown()


# ── session state init ──────────────────────────────────────────────────────────

if "mb_swing_result" not in st.session_state:
    st.session_state.mb_swing_result = None
if "mb_classification" not in st.session_state:
    st.session_state.mb_classification = None
if "mb_pattern_alerts" not in st.session_state:
    st.session_state.mb_pattern_alerts = []
if "mb_saved" not in st.session_state:
    st.session_state.mb_saved = False
if "mb_rule_candidates" not in st.session_state:
    st.session_state.mb_rule_candidates = []
if "mb_dismissed_rules" not in st.session_state:
    st.session_state.mb_dismissed_rules = set()
if "mb_promoted_rules" not in st.session_state:
    st.session_state.mb_promoted_rules = set()


# ── styles ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Memory Bank amber accent system */
.mb-header { 
    color: #f59e0b; 
    font-size: 0.72rem; 
    font-weight: 700; 
    text-transform: uppercase; 
    letter-spacing: 0.12em;
    margin-bottom: 4px;
}
.mb-card {
    background: #111827;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.mb-card-accent {
    background: #111827;
    border: 1px solid #d97706;
    border-left: 4px solid #f59e0b;
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.mb-swing-pos {
    font-size: 2.4rem;
    font-weight: 800;
    color: #34d399;
    font-family: 'Courier New', monospace;
    letter-spacing: -0.02em;
}
.mb-swing-neg {
    font-size: 2.4rem;
    font-weight: 800;
    color: #f87171;
    font-family: 'Courier New', monospace;
    letter-spacing: -0.02em;
}
.mb-label {
    color: #6b7280;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.mb-value {
    color: #e5e7eb;
    font-size: 1.05rem;
    font-weight: 600;
}
.mb-badge-high   { background:#7f1d1d; color:#fca5a5; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:700; }
.mb-badge-medium { background:#78350f; color:#fcd34d; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:700; }
.mb-badge-watch  { background:#064e3b; color:#6ee7b7; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:700; }
.mb-reason-item  { color:#9ca3af; font-size:0.84rem; padding:2px 0; }
.mb-divider { border-top: 1px solid #1f2937; margin: 18px 0; }
.mb-step-num {
    background: #f59e0b;
    color: #000;
    border-radius: 50%;
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 0.75rem;
    margin-right: 8px;
    flex-shrink: 0;
}
</style>
""", unsafe_allow_html=True)


# ── tab body ────────────────────────────────────────────────────────────────────

with tab_memory:

    st.markdown("""
    <div style='margin-bottom:6px'>
        <span style='color:#f59e0b;font-size:1.45rem;font-weight:800;letter-spacing:-0.01em;'>🧠 Memory Bank</span>
        <span style='color:#6b7280;font-size:0.88rem;margin-left:10px;'>Log a historical price event → Gemini classifies the catalyst → Pattern alerts fire for upcoming watchlist tickers</span>
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    # ── STEP 1: Ticker + Date Range ────────────────────────────────────────────
    st.markdown('<div style="display:flex;align-items:center;margin-bottom:10px"><span class="mb-step-num">1</span><span style="color:#f59e0b;font-weight:700;font-size:1rem;">Select Ticker & Date Window</span></div>', unsafe_allow_html=True)

    with st.container():
        s1c1, s1c2, s1c3, s1c4 = st.columns([1.2, 1.4, 1.4, 1.2])
        with s1c1:
            mb_ticker = st.text_input("Ticker Symbol", value="NBIS", key="mb_ticker_input").strip().upper()
        with s1c2:
            mb_start = st.date_input("Start Date", value=datetime.date(2026, 8, 12), key="mb_start")
        with s1c3:
            mb_end = st.date_input("End Date", value=datetime.date(2026, 8, 13), key="mb_end")
        with s1c4:
            st.markdown("<br>", unsafe_allow_html=True)
            fetch_btn = st.button("📡 Fetch Price Swing", type="primary", use_container_width=True, key="mb_fetch")

    if fetch_btn:
        st.session_state.mb_swing_result = None
        st.session_state.mb_classification = None
        st.session_state.mb_pattern_alerts = []
        st.session_state.mb_saved = False
        if not mb_ticker:
            st.error("Please enter a ticker symbol.")
        elif mb_end < mb_start:
            st.error("End date must be after start date.")
        else:
            from volatility_system import HistoricalDataFetcher
            with st.spinner(f"Querying yfinance for {mb_ticker} ({mb_start} → {mb_end})…"):
                result = HistoricalDataFetcher.fetch_historical_swing(
                    mb_ticker,
                    mb_start.strftime("%Y-%m-%d"),
                    mb_end.strftime("%Y-%m-%d")
                )
            if "error" in result:
                st.error(f"Price fetch failed: {result['error']}")
            else:
                st.session_state.mb_swing_result = result

    # ── STEP 2: Show swing + news input ────────────────────────────────────────
    if st.session_state.mb_swing_result:
        res = st.session_state.mb_swing_result
        swing_pct = res["swing_pct"]
        days = res["days"]
        sign = "+" if swing_pct >= 0 else ""
        swing_cls = "mb-swing-pos" if swing_pct >= 0 else "mb-swing-neg"
        threshold_5d  = abs(swing_pct) >= 10 and days <= 5
        threshold_14d = abs(swing_pct) >= 15 and days <= 14
        threshold_30d = abs(swing_pct) >= 20 and days <= 30
        qualifies = threshold_5d or threshold_14d or threshold_30d

        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="display:flex;align-items:center;margin-bottom:10px"><span class="mb-step-num">2</span><span style="color:#f59e0b;font-weight:700;font-size:1rem;">Confirm Price Move</span></div>', unsafe_allow_html=True)

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Swing ({days}d)</div><div class="{swing_cls}">{sign}{swing_pct:.2f}%</div></div>', unsafe_allow_html=True)
        with p2:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Entry Price</div><div class="mb-value" style="font-size:1.5rem;color:#60a5fa">${res["start_price"]:.2f}</div></div>', unsafe_allow_html=True)
        with p3:
            st.markdown(f'<div class="mb-card"><div class="mb-label">Exit Price</div><div class="mb-value" style="font-size:1.5rem;color:#60a5fa">${res["end_price"]:.2f}</div></div>', unsafe_allow_html=True)
        with p4:
            q_color = "#34d399" if qualifies else "#f87171"
            q_label = "✅ Qualifies for DB" if qualifies else "⚠️ Below Threshold"
            q_sub = "(≥10% 5-day · ≥15% 14-day · ≥20% 30-day)" if not qualifies else ""
            st.markdown(f'<div class="mb-card"><div class="mb-label">Threshold Check</div><div class="mb-value" style="color:{q_color};font-size:0.95rem">{q_label}</div><div class="mb-label">{q_sub}</div></div>', unsafe_allow_html=True)

        if not qualifies:
            st.warning(f"**{mb_ticker}** moved {sign}{swing_pct:.2f}% over {days} day(s). This is below the ≥10% (5-day), ≥15% (14-day), or ≥20% (30-day) threshold for the correlation database. You can still classify it manually using the Database Editor tab.")

        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="display:flex;align-items:center;margin-bottom:10px"><span class="mb-step-num">3</span><span style="color:#f59e0b;font-weight:700;font-size:1rem;">Paste Catalyst News</span></div>', unsafe_allow_html=True)
        st.caption("Paste the earnings release, press release, or news that drove the move. The more detail, the better Gemini's classification.")

        mb_news = st.text_area(
            "Raw Catalyst Text",
            height=180,
            placeholder="e.g. NBIS Q2: Revenue $582.3M (5x YoY). Adjusted EBITDA +$236.2M (39.4% margin). Announced $1B+ contracts including Reflection AI through 2029. Raised contracted computing capacity targets…",
            key="mb_news_input",
            label_visibility="collapsed"
        )

        # API key presence check — warn early rather than at classify time
        try:
            _api_key_ok = bool(st.secrets.get("GEMINI_API_KEY", ""))
        except Exception:
            _api_key_ok = False
        _api_key_ok = _api_key_ok or bool(os.environ.get("GEMINI_API_KEY", ""))
        if not _api_key_ok:
            st.warning(
                "⚠️ **No Gemini API key detected.** Classification will fall back to the "
                "basic rules engine (single catalyst, no weighting).\n\n"
                "Add `GEMINI_API_KEY = 'your-key'` to `.streamlit/secrets.toml` and restart the app. "
                "Get a free key at aistudio.google.com/app/apikey",
                icon="🔑"
            )

        classify_btn = st.button("🤖 Classify with AI", type="primary", key="mb_classify", disabled=not mb_news)

        if classify_btn and mb_news:
            st.session_state.mb_classification = None
            st.session_state.mb_pattern_alerts = []
            st.session_state.mb_saved = False
            with st.spinner("Gemini is reading the news and identifying all catalysts…"):
                cls_results = _classify_catalyst_with_gemini(mb_ticker, swing_pct, days, mb_news)
                st.session_state.mb_classification = cls_results  # now a list
                # Run pattern matching across ALL classifications found
                all_alerts = {}
                priority = {"🔴 HIGH": 3, "🟡 MEDIUM": 2, "🟢 WATCH": 1}
                for cls_item in cls_results:
                    for alert in _score_watchlist_matches(cls_item["classification"], swing_pct, cls_item["trigger_metric"]):
                        t = alert["ticker"]
                        if t not in all_alerts or priority[alert["alert_level"]] > priority[all_alerts[t]["alert_level"]]:
                            all_alerts[t] = alert
                st.session_state.mb_pattern_alerts = sorted(all_alerts.values(), key=lambda x: priority[x["alert_level"]], reverse=True)

    # ── STEP 4: Show classifications + pattern alerts + save ──────────────────
    if st.session_state.mb_classification:
        cls_list = st.session_state.mb_classification  # always a list now
        res = st.session_state.mb_swing_result
        swing_pct = res["swing_pct"]
        days = res["days"]
        sign = "+" if swing_pct >= 0 else ""

        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="display:flex;align-items:center;margin-bottom:12px">'
            f'<span class="mb-step-num">4</span>'
            f'<span style="color:#f59e0b;font-weight:700;font-size:1rem;">Gemini\'s Classification</span>'
            f'<span style="color:#6b7280;font-size:0.82rem;margin-left:10px;">'
            f'{len(cls_list)} catalyst(s) identified — each saved as a separate DB record</span></div>',
            unsafe_allow_html=True
        )

        rank_labels = {1: "PRIMARY", 2: "SECONDARY", 3: "TERTIARY", 4: "CONTRIBUTING", 5: "CONTRIBUTING"}
        rank_colors = {1: "#f59e0b", 2: "#60a5fa", 3: "#a78bfa", 4: "#6b7280", 5: "#6b7280"}

        for cls in cls_list:
            rank = cls.get("rank", 1)
            label = rank_labels.get(rank, "CONTRIBUTING")
            r_color = rank_colors.get(rank, "#6b7280")
            conf_color = {"High": "#34d399", "Medium": "#fbbf24", "Low": "#f87171"}.get(cls.get("confidence", "Low"), "#9ca3af")
            border_color = r_color
            weight = cls.get("weight_pct", 0)
            w_swing = cls.get("weighted_swing", 0.0)
            w_swing_sign = "+" if w_swing >= 0 else ""
            w_swing_color = "#34d399" if w_swing >= 0 else "#f87171"
            st.markdown(f"""
            <div class="mb-card" style="border:1px solid {border_color};border-left:4px solid {border_color};margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
                    <div style="flex:1">
                        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
                            <span style="background:{r_color};color:#000;font-size:0.65rem;font-weight:800;padding:2px 8px;border-radius:999px;letter-spacing:0.08em">{label}</span>
                            <span style="color:{r_color};font-size:1.1rem;font-weight:800">{cls.get("classification","—")}</span>
                        </div>
                        <div class="mb-label" style="margin-bottom:2px">Event Type</div>
                        <div class="mb-value" style="font-size:0.9rem;margin-bottom:8px">{cls.get("event_type","—")}</div>
                        <div class="mb-label" style="margin-bottom:2px">Specific Trigger</div>
                        <div style="color:#d1d5db;font-size:0.88rem">{cls.get("trigger_metric","—")}</div>
                    </div>
                    <div style="text-align:right;min-width:120px">
                        <div style="margin-bottom:10px">
                            <div class="mb-label">Confidence</div>
                            <div style="color:{conf_color};font-weight:700;font-size:1rem">{cls.get("confidence","—")}</div>
                        </div>
                        <div>
                            <div class="mb-label">Attributed Swing</div>
                            <div style="color:{w_swing_color};font-weight:800;font-size:1.15rem;font-family:'Courier New',monospace">{w_swing_sign}{w_swing:.2f}%</div>
                            <div style="color:#6b7280;font-size:0.72rem;margin-top:1px">{weight}% of move</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top:10px;border-top:1px solid #1f2937;padding-top:8px">
                    <span class="mb-label">Rationale: </span>
                    <span style="color:#9ca3af;font-size:0.83rem">{cls.get("rationale","")}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Pattern Alerts ─────────────────────────────────────────────────────
        alerts = st.session_state.mb_pattern_alerts
        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="display:flex;align-items:center;margin-bottom:12px"><span class="mb-step-num">5</span><span style="color:#f59e0b;font-weight:700;font-size:1rem;">Pattern Alerts — Watchlist Scan</span><span style="color:#6b7280;font-size:0.82rem;margin-left:10px;">({len(alerts)} ticker(s) flagged)</span></div>', unsafe_allow_html=True)

        if not alerts:
            st.markdown('<div class="mb-card"><span style="color:#6b7280">No watchlist tickers matched the catalyst pattern. No alerts generated.</span></div>', unsafe_allow_html=True)
        else:
            for a in alerts:
                level = a["alert_level"]
                badge_cls = "mb-badge-high" if "HIGH" in level else ("mb-badge-medium" if "MEDIUM" in level else "mb-badge-watch")
                reasons_html = "".join(f'<div class="mb-reason-item">• {r}</div>' for r in a["match_reasons"])
                st.markdown(f"""
                <div class="mb-card" style="border-left:3px solid {'#ef4444' if 'HIGH' in level else ('#f59e0b' if 'MEDIUM' in level else '#10b981')}">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
                        <span style="color:#e5e7eb;font-size:1.15rem;font-weight:800;font-family:monospace">{a['ticker']}</span>
                        <span class="{badge_cls}">{level}</span>
                        <span style="color:#6b7280;font-size:0.82rem">{a['event_type']} · {a['timing']}</span>
                    </div>
                    {reasons_html}
                </div>
                """, unsafe_allow_html=True)

        # ── Save to DB ─────────────────────────────────────────────────────────
        st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="display:flex;align-items:center;margin-bottom:12px"><span class="mb-step-num">6</span><span style="color:#f59e0b;font-weight:700;font-size:1rem;">Save to Correlation Database</span></div>', unsafe_allow_html=True)

        swing_str = f"{sign}{swing_pct:.2f}% ({days} Day)"

        # Preview: one row per classification with attributed (weighted) swing
        def _preview_row(c):
            w = c.get("weight_pct", 0)
            ws = c.get("attributed_swing", c.get("weighted_swing", 0.0))
            ws_sign = "+" if ws >= 0 else ""
            ws_color = "#34d399" if ws >= 0 else "#f87171"
            rank_lbl = rank_labels.get(c.get("rank", 1), "CONTRIBUTING")
            return (
                f'<div style="display:flex;gap:16px;align-items:center;padding:6px 0;border-bottom:1px solid #1f2937">'
                f'<span style="color:#9ca3af;font-size:0.72rem;font-weight:700;min-width:90px">{rank_lbl}</span>'
                f'<span style="color:#f59e0b;font-size:0.88rem;font-weight:700;flex:1">{c.get("classification","—")}</span>'
                f'<span style="color:#6b7280;font-size:0.78rem;min-width:60px">{w}% of move</span>'
                f'<span style="color:{ws_color};font-size:0.88rem;font-weight:700;font-family:monospace;min-width:70px;text-align:right">{ws_sign}{ws:.2f}%</span>'
                f'</div>'
            )
        preview_rows = "".join(_preview_row(c) for c in cls_list)

        col_prev, col_save = st.columns([3, 1])
        with col_prev:
            st.markdown(f"""
            <div class="mb-card" style="padding:12px 16px">
                <div style="display:flex;gap:24px;margin-bottom:10px;flex-wrap:wrap">
                    <div><span class="mb-label">Ticker</span><br><span class="mb-value">{mb_ticker}</span></div>
                    <div><span class="mb-label">Swing</span><br><span class="mb-value" style="color:{'#34d399' if swing_pct>=0 else '#f87171'}">{swing_str}</span></div>
                    <div><span class="mb-label">Records to Save</span><br><span style="color:#a78bfa;font-weight:700;font-size:1.1rem">{len(cls_list)}</span></div>
                </div>
                <div style="border-top:1px solid #374151;padding-top:8px">{preview_rows}</div>
            </div>
            """, unsafe_allow_html=True)
        with col_save:
            st.markdown("<br>", unsafe_allow_html=True)
            save_btn = st.button("💾 Save All to Memory Bank", type="primary", use_container_width=True, key="mb_save", disabled=st.session_state.mb_saved)

        if save_btn and not st.session_state.mb_saved:
            saved_count = 0
            for cls in cls_list:
                # attributed_swing is the weighted portion of the total move for this catalyst
                attributed_swing_val = cls.get("attributed_swing", cls.get("weighted_swing", round(swing_pct, 2)))
                weight_pct = cls.get("weight_pct", 100)
                rank_lbl = rank_labels.get(cls.get("rank", 1), "CONTRIBUTING")
                w_sign = "+" if attributed_swing_val >= 0 else ""
                attributed_swing_str = f"{w_sign}{attributed_swing_val:.2f}% ({rank_lbl} · {weight_pct}% of {sign}{swing_pct:.2f}% {days}d move)"
                new_record = CatalystRecord(
                    ticker=mb_ticker,
                    event_type=cls.get("event_type", "Earnings / Catalyst"),
                    trigger_metric=cls.get("trigger_metric", "Event-Driven Release"),
                    resulting_swing=attributed_swing_str,
                    classification=cls.get("classification", "Earnings Beat"),
                    swing_value=attributed_swing_val
                )
                system.db.add_record(new_record)
                saved_count += 1
            system.db.save()
            st.session_state.mb_saved = True
            st.session_state.mb_rule_candidates = _scan_for_rule_candidates()
            st.success(f"✅ **{mb_ticker}** — {saved_count} catalyst record(s) saved to Correlation Database! `{swing_str}`")
            st.balloons()

        if st.session_state.mb_saved:
            st.info("Records saved this session. Fetch a new ticker above to log another event.")

        # ── STEP 7: Auto-Suggested Rule Promotions ─────────────────────────────
        candidates = st.session_state.mb_rule_candidates
        if candidates:
            st.markdown('<div class="mb-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                '<div style="display:flex;align-items:center;margin-bottom:12px">'
                '<span class="mb-step-num" style="background:#a78bfa;color:#000">7</span>'
                '<span style="color:#a78bfa;font-weight:700;font-size:1rem;">System Rule Suggestions</span>'
                '<span style="color:#6b7280;font-size:0.82rem;margin-left:10px;">'
                f'The pattern engine found {len(candidates)} candidate(s) ready for promotion</span></div>',
                unsafe_allow_html=True
            )

            for i, cand in enumerate(candidates):
                cls_name = cand["classification"]
                already_promoted = cls_name in st.session_state.mb_promoted_rules

                avg_sign = "+" if cand["avg_swing"] > 0 else ""
                direction_label = "📈 Extreme Gap-Up" if cand["direction"] == "gap-up" else "📉 Extreme Gap-Down"
                examples_str = " · ".join(cand["examples"])

                st.markdown(f"""
                <div class="mb-card" style="border:1px solid #7c3aed;border-left:4px solid #a78bfa;background:#1a1232;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px">
                        <div>
                            <div style="color:#a78bfa;font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px">
                                New Rule Candidate
                            </div>
                            <div style="color:#e5e7eb;font-size:1.15rem;font-weight:800">{cls_name}</div>
                        </div>
                        <div style="text-align:right">
                            <div class="mb-label">Direction</div>
                            <div style="color:#e5e7eb;font-size:0.9rem;font-weight:600">{direction_label}</div>
                        </div>
                    </div>
                    <div style="display:flex;gap:28px;flex-wrap:wrap;margin-bottom:10px">
                        <div><span class="mb-label">Qualifying Events</span><br>
                             <span style="color:#a78bfa;font-weight:700;font-size:1.1rem">{cand['record_count']}</span>
                             <span style="color:#6b7280;font-size:0.8rem"> (all ≥15% swing)</span></div>
                        <div><span class="mb-label">Avg Swing</span><br>
                             <span style="color:{'#34d399' if cand['avg_swing']>0 else '#f87171'};font-weight:700;font-size:1.1rem">{avg_sign}{cand['avg_swing']:.1f}%</span></div>
                        <div><span class="mb-label">Evidence</span><br>
                             <span style="color:#9ca3af;font-size:0.84rem">{examples_str}</span></div>
                    </div>
                    <div style="color:#6b7280;font-size:0.82rem;font-style:italic">
                        Promoting adds this classification to the System Rules section of Catalyst_Correlations.md
                        and activates it in the Prediction Engine for future alerts.
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if already_promoted:
                    st.markdown(
                        f'<div style="color:#34d399;font-size:0.88rem;margin:-8px 0 12px 0">'
                        f'✅ <strong>{cls_name}</strong> has been promoted to a System Rule.</div>',
                        unsafe_allow_html=True
                    )
                else:
                    btn_col1, btn_col2, _ = st.columns([1, 1, 3])
                    with btn_col1:
                        if st.button(
                            "⬆ Promote to System Rule",
                            key=f"promote_{i}_{cls_name}",
                            type="primary",
                            use_container_width=True
                        ):
                            _promote_rule(cls_name, cand["direction"], cand["avg_swing"])
                            st.session_state.mb_promoted_rules.add(cls_name)
                            st.session_state.mb_rule_candidates = _scan_for_rule_candidates()
                            st.rerun()
                    with btn_col2:
                        if st.button(
                            "✕ Dismiss",
                            key=f"dismiss_{i}_{cls_name}",
                            use_container_width=True
                        ):
                            st.session_state.mb_dismissed_rules.add(cls_name)
                            st.session_state.mb_rule_candidates = _scan_for_rule_candidates()
                            st.rerun()
