import streamlit as st
import pandas as pd
import os
import json
import re
import datetime
import requests
import yfinance as yf
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime as dt

from supabase_store import (
    load_watchlist, save_watchlist,
    load_upcoming_events, save_upcoming_events,
    IS_CLOUD
)

try:
    from volatility_system import (
        EventDrivenVolatilitySystem, CatalystDatabase, EventParser, 
        PredictiveEngine, CatalystRecord, LiveDataFetcher, HistoricalDataFetcher
    )
except ImportError:
    pass

# ── 1. GLOBAL APP CONFIGURATION ────────────────────────────────────────────────
st.set_page_config(
    page_title="EDPAS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

WATCHLIST_FILE = "watchlist.json"
EVENTS_FILE = "upcoming_events.json"
DB_FILE_PATH = "Catalyst_Correlations.md"

# ── 2. EDPAS INITIALISATION ────────────────────────────────────────────────────
if "db_path" not in st.session_state:
    st.session_state.db_path = DB_FILE_PATH
if "system" not in st.session_state:
    st.session_state.system = EventDrivenVolatilitySystem(db_path=st.session_state.db_path)
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "upcoming_events" not in st.session_state:
    st.session_state.upcoming_events = load_upcoming_events()

system = st.session_state.system

# ── 3. PTS POSTGRESQL INITIALISATION ───────────────────────────────────────────
@st.cache_resource(ttl=60)
def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))
    if not db_url:
        return None
    try:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    except Exception as e:
        st.error(f"PTS Database connection failed: {e}")
        return None

conn = get_db_connection()

@st.cache_data(ttl=30)
def fetch_worksheet():
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, close_price, shares_held, avg_cost, current_directive, 
                       catalyst_tier, etr_day_low, etr_day_high, 
                       etr_week_low, etr_week_high,
                       p_buy_mean, underval_pct, remarks, is_suspended 
                FROM ticker_states 
                ORDER BY ticker ASC;
            """)
            return cur.fetchall()
    except Exception:
        return []

def update_remarks(ticker, new_remark):
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ticker_states SET remarks = %s WHERE ticker = %s;", (new_remark, ticker))
        conn.commit()
        st.toast(f"✅ Remarks saved for {ticker}")
        fetch_worksheet.clear()
    except Exception as e:
        conn.rollback()
        st.error(f"Failed to save remark: {e}")

@st.cache_data(ttl=15)
def fetch_live_market_data(ticker_list):
    live_dict = {}
    timestamp = dt.now().strftime("%I:%M:%S %p")
    if not ticker_list: 
        return live_dict, timestamp
    try:
        df_5d = yf.download(ticker_list, period="5d", progress=False)
        df_live = yf.download(ticker_list, period="2d", interval="1m", prepost=True, progress=False)
        
        if df_live.empty or df_5d.empty: 
            return live_dict, timestamp
            
        is_multi = isinstance(df_live.columns, pd.MultiIndex)
        for t in ticker_list:
            try:
                if is_multi:
                    if t not in df_live['Close'].columns: continue
                    live_px = float(df_live['Close'][t].dropna().iloc[-1])
                    d_high = float(df_live['High'][t].dropna().max())
                    d_low = float(df_live['Low'][t].dropna().min())
                    w_high = float(df_5d['High'][t].dropna().max())
                    w_low = float(df_5d['Low'][t].dropna().min())
                else:
                    live_px = float(df_live['Close'].dropna().iloc[-1])
                    d_high = float(df_live['High'].dropna().max())
                    d_low = float(df_live['Low'].dropna().min())
                    w_high = float(df_5d['High'].dropna().max())
                    w_low = float(df_5d['Low'].dropna().min())
                    
                live_dict[t] = {
                    "price": live_px, "d_high": max(d_high, live_px), "d_low": min(d_low, live_px),
                    "w_high": max(w_high, live_px), "w_low": min(w_low, live_px)
                }
            except Exception:
                continue
    except Exception:
        pass
    return live_dict, timestamp

def move_ticker(ticker, direction):
    idx = st.session_state.custom_ticker_order.index(ticker)
    if direction == "up" and idx > 0:
        st.session_state.custom_ticker_order[idx], st.session_state.custom_ticker_order[idx - 1] = (
            st.session_state.custom_ticker_order[idx - 1], st.session_state.custom_ticker_order[idx])
    elif direction == "down" and idx < len(st.session_state.custom_ticker_order) - 1:
        st.session_state.custom_ticker_order[idx], st.session_state.custom_ticker_order[idx + 1] = (
            st.session_state.custom_ticker_order[idx + 1], st.session_state.custom_ticker_order[idx])
    st.rerun()

def safe_float(val, default=None):
    if val is None or val == "": return default
    try: return float(val)
    except (ValueError, TypeError): return default

# ── 4. GLOBAL CSS & SIDEBAR ────────────────────────────────────────────────────
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
This system merges Continuous GARCH Volatility (PTS) and Discrete Event Classification (EDPAS) into a single predictive engine.
""")

st.title("EDPAS")
st.caption("Discrete Event Classification & Quantitative Arbitrage Matching Engine")

# ── 5. MAIN TABS ───────────────────────────────────────────────────────────────
tab_pts, tab_schedule, tab_predict, tab_database, tab_memory = st.tabs([
    "⚡ PTS", 
    "📅 Scheduler & Watchlist", 
    "🎯 Real-Time Prediction Engine", 
    "🗄️ Correlation Database Editor",
    "🧠 Memory Bank"
])

# ==========================================
# TAB 1: PTS LIVE MARKET MATRIX
# ==========================================
with tab_pts:
    st.markdown("<h3 style='color: #3b82f6; margin-bottom: 5px;'>⚡ PTS Live Market Matrix</h3>", unsafe_allow_html=True)
    
    if not conn:
        st.warning("⚠️ Waiting for DATABASE_URL secret to be added to Streamlit Cloud.")
    else:
        pts_data = fetch_worksheet()
        if not pts_data:
            st.info("No assets found in the PTS database.")
        else:
            all_pts_tickers = [row['ticker'] for row in pts_data]
            live_market_data, last_updated = fetch_live_market_data(all_pts_tickers)
            
            st.caption(f"🕒 **Live Market Snapshot:** {last_updated}")
            
            if 'custom_ticker_order' not in st.session_state:
                st.session_state.custom_ticker_order = all_pts_tickers
            
            current_order = [t for t in st.session_state.custom_ticker_order if t in all_pts_tickers]
            missing_tickers = [t for t in all_pts_tickers if t not in current_order]
            st.session_state.custom_ticker_order = current_order + missing_tickers
            
            data_dict = {row['ticker']: row for row in pts_data}
            sorted_data = [data_dict[t] for t in st.session_state.custom_ticker_order if t in data_dict]
            
            for row in sorted_data:
                ticker = row['ticker']
                live_info = live_market_data.get(ticker, {})
                
                live_px = live_info.get("price")
                db_px = safe_float(row['close_price'])
                final_px = live_px if live_px is not None else db_px
                close_px = f"${final_px:.2f}" if final_px is not None else "—"
                
                shares = row['shares_held'] or 0
                ac = safe_float(row['avg_cost'])
                avg_cost = f"${ac:.2f}" if ac is not None else "—"
                is_watch = shares == 0
            
                directive = row['current_directive'] or "HOLD"
                d_color = "#f59e0b"
                if directive in ["BUY", "ACCUMULATE"]: d_color = "#10b981"
                elif directive in ["TRIM", "SUSPENDED", "STOP_BUY"]: d_color = "#ef4444"
                elif directive == "RUNNER": d_color = "#8b5cf6"
            
                dl = safe_float(row['etr_day_low'])
                if dl is not None and dl > 0:
                    d_low = f"${dl:.1f}"
                    d_high = f"${safe_float(row['etr_day_high']):.1f}"
                    w_low = f"${safe_float(row['etr_week_low']):.1f}"
                    w_high = f"${safe_float(row['etr_week_high']):.1f}"
                else:
                    d_low = f"${live_info.get('d_low'):.1f}" if live_info.get('d_low') else "—"
                    d_high = f"${live_info.get('d_high'):.1f}" if live_info.get('d_high') else "—"
                    w_low = f"${live_info.get('w_low'):.1f}" if live_info.get('w_low') else "—"
                    w_high = f"${live_info.get('w_high'):.1f}" if live_info.get('w_high') else "—"
                
                p_buy_val = safe_float(row['p_buy_mean'])
                is_calibrating = (p_buy_val is None or p_buy_val == 0.0)
                
                if is_calibrating:
                    p_buy = "—"
                    underval_str = "Calibrating..."
                else:
                    p_buy = f"${p_buy_val:.2f}"
                    uv = safe_float(row['underval_pct'], 0.0) * 100
                    underval_str = f"↓ {abs(uv):.1f}%" if uv >= 0 else f"↑ {abs(uv):.1f}%"
                    
                remarks_val = row['remarks'] if row['remarks'] else ""
            
                st.markdown(f"""
                <div style="background-color: #111827; border: 1px solid #1f293d; border-radius: 10px 10px 0 0; padding: 10px 12px 6px 12px; margin-top: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 18px; font-weight: 800; color: white;">{ticker}</span>
                            <span style="font-size: 11px; color: #9ca3af; margin-left: 8px;">
                                {'<span style="color:#8b5cf6">Watchlist</span>' if is_watch else f"{shares} shs @ {avg_cost}"}
                            </span>
                        </div>
                        <div>
                            <span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: {d_color}33; color: {d_color};">{directive}</span>
                            <span style="font-size: 11px; color: #9ca3af; margin-left: 6px;">Cat: <strong style="color:white;">{row['catalyst_tier'] or 'Std'}</strong></span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
                c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.6, 0.4], gap="small")
                
                with c1:
                    st.markdown(f"""
                    <div style="background: #0b111e; padding: 8px; border-radius: 4px; height: 100%;">
                        <div style="font-size: 9px; color: #9ca3af; text-transform: uppercase;">Price</div>
                        <div style="font-size: 14px; font-weight: 700; color: #e5e7eb;">{close_px}</div>
                        <div style="font-size: 10px; color: #9ca3af; margin-top: 2px;">D: {d_low}-{d_high}</div>
                        <div style="font-size: 10px; color: #9ca3af;">W: {w_low}-{w_high}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with c2:
                    st.markdown(f"""
                    <div style="background: #0b111e; padding: 8px; border-radius: 4px; height: 100%;">
                        <div style="font-size: 9px; color: #9ca3af; text-transform: uppercase;">Entry Target</div>
                        <div style="font-size: 14px; font-weight: 700; color: #3b82f6;">{p_buy}</div>
                        <div style="font-size: 10px; color: #9ca3af; margin-top: 2px;">{underval_str}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with c3:
                    new_remark = st.text_input(
                        f"Remarks {ticker}",
                        value=remarks_val,
                        placeholder="Add remarks...",
                        label_visibility="collapsed",
                        key=f"rem_{ticker}"
                    )
                    if new_remark != remarks_val:
                        update_remarks(ticker, new_remark)
            
                with c4:
                    st.button("⬆", key=f"up_{ticker}", on_click=move_ticker, args=(ticker, "up"), use_container_width=True)
                    st.button("⬇", key=f"down_{ticker}", on_click=move_ticker, args=(ticker, "down"), use_container_width=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Refresh Live Data", use_container_width=True):
                fetch_worksheet.clear()
                fetch_live_market_data.clear()
                st.rerun()

# ==========================================
# TAB 2: SCHEDULER & WATCHLIST
# ==========================================
with tab_schedule:
    st.subheader("Event Scheduler & Calendar Automation")
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
    EVENT_TYPE_META = {
        "Earnings": {"monitoring_window": "2–3 weeks prior", "impact": "Sharp gap risk, IV expansion", "strategy": "Avoid unhedged high-beta positions", "example_notes": "Watch for revenue beats."},
        "Ex-Dividend": {"monitoring_window": "1 week prior", "impact": "Price adjusts down by dividend", "strategy": "Capture dividend or avoid holding short", "example_notes": "Stock price adjustment on ex-date."},
        "Industry Expo / Keynote": {"monitoring_window": "1–2 weeks prior", "impact": "Pre-conference rally, sell-the-news post-event", "strategy": "Buy the rumor during accumulation", "example_notes": "Watch for sector sympathy rallies."},
        "Index Rebalancing": {"monitoring_window": "3–4 weeks prior", "impact": "Volume spikes from passive funds", "strategy": "Front-run passive inflows", "example_notes": "Expect passive fund inflows."},
        "Legal / Regulatory Milestone": {"monitoring_window": "1–2 weeks prior", "impact": "Asymmetric relief rally or selloff", "strategy": "Monitor court docket deadlines", "example_notes": "Binary outcome risk."},
    }
    EVENT_COLORS = {"Earnings": "#f59e0b", "Ex-Dividend": "#60a5fa", "Industry Expo / Keynote": "#a78bfa", "Index Rebalancing": "#34d399", "Legal / Regulatory Milestone":"#f87171"}

    if st.session_state.upcoming_events:
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        future_events = [e for e in st.session_state.upcoming_events if re.match(r"^\d{4}-\d{2}-\d{2}$", str(e.get("timing", ""))) and str(e.get("timing", "")) >= today_str]
        if future_events:
            sorted_events = sorted(future_events, key=lambda x: x.get("timing", "9999-12-31"))
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
                st.markdown(f'<div class="evt-row"><span class="evt-ticker">{evt.get("ticker","")}</span><span class="evt-badge" style="background:{color}22;color:{color}">{etype}</span><span class="evt-date">📅 {evt.get("timing","")}</span><span class="evt-notes">{notes}</span></div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.info("No upcoming events — all scheduled dates have passed. Sync with Yahoo Finance to refresh.")
        if st.button("Reset Calendar Schedule"):
            st.session_state.upcoming_events = []
            save_upcoming_events([])
            st.rerun()
    else:
        st.info("No pre-scheduled dates currently loaded.")

    st.markdown("---")
    with st.expander("➕ Add Catalyst Event", expanded=False):
        fc1, fc2 = st.columns([1, 1])
        with fc1:
            form_ticker = st.text_input("Ticker", placeholder="e.g. NVDA").upper().strip()
        with fc2:
            form_etype = st.selectbox("Event Type", list(EVENT_TYPE_META.keys()))
        form_date = st.date_input("Scheduled Date", value=datetime.date.today())
        form_notes = st.text_area("Event Notes (optional)", placeholder="Event context...")
        if st.button("➕ Add to Calendar", type="primary"):
            if form_ticker:
                st.session_state.upcoming_events.append({"ticker": form_ticker, "event_type": form_etype, "timing": form_date.strftime("%Y-%m-%d"), "notes": form_notes.strip()})
                save_upcoming_events(st.session_state.upcoming_events)
                st.success(f"✅ {form_ticker} added to calendar.")
                st.rerun()

# ==========================================
# TAB 3: REAL-TIME PREDICTION ENGINE
# ==========================================
with tab_predict:
    st.markdown("""
    <div style='margin-bottom:6px'>
        <span style='color:#60a5fa;font-size:1.45rem;font-weight:800;letter-spacing:-0.01em;'>🎯 Real-Time Prediction Engine</span>
        <span style='color:#6b7280;font-size:0.88rem;margin-left:10px;'>Paste a live news drop → AI identifies all catalysts → forecasts price swing from historical DB matches</span>
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    if "pe_classifications" not in st.session_state: st.session_state.pe_classifications = None
    if "pe_forecast" not in st.session_state: st.session_state.pe_forecast = None
    if "pe_ticker" not in st.session_state: st.session_state.pe_ticker = ""
    if "pe_price" not in st.session_state: st.session_state.pe_price = 0.0
    if "pe_logged" not in st.session_state: st.session_state.pe_logged = False

    def _gemini_classify_realtime(ticker: str, news_text: str) -> list:
        api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            st.error("No GEMINI_API_KEY found in secrets.")
            return []
        prompt = f"""You are a quantitative event-driven analyst reviewing a live news drop for {ticker}.
News:
---
{news_text}
---
Identify ALL distinct catalysts present. Return ONLY a valid JSON array matching this exact schema:
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
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 4000, "temperature": 0.2}},
                timeout=25
            )
            resp.raise_for_status()
            raw_resp = resp.json()
            content_parts = raw_resp["candidates"][0]["content"].get("parts", [])
            actual_texts = [p["text"] for p in content_parts if not p.get("thought", False) and "text" in p]
            raw = "".join(actual_texts).strip() if actual_texts else content_parts[-1].get("text", "").strip()
            raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
            if isinstance(result, dict): result = [result]
            total_w = sum(item.get("weight_pct", 0) for item in result)
            if total_w != 100 and total_w > 0:
                for item in result: item["weight_pct"] = round(item.get("weight_pct", 0) * 100 / total_w)
                result[0]["weight_pct"] += 100 - sum(item["weight_pct"] for item in result)
            return sorted(result, key=lambda x: x.get("rank", 99))
        except Exception as e:
            st.error(f"Gemini classification failed: {e}")
            return []

    def _build_forecast(classifications: list, current_price: float) -> dict:
        forecast_rows = []
        total_min = 0.0
        total_max = 0.0
        dominant_direction = "bullish"
        if sum(c.get("weight_pct", 0) for c in classifications if c.get("direction") == "bearish") > 50: dominant_direction = "bearish"

        for c in classifications:
            cls_name = c.get("classification", "")
            weight = c.get("weight_pct", 0) / 100.0
            direction = c.get("direction", "bullish")
            matches = system.db.find_matches_by_classification(cls_name)

            if matches:
                swings = [r.swing_value for r in matches]
                db_note = f"DB match (avg {sum(swings)/len(swings):+.1f}%)"
                contributed_min = min(swings) * weight
                contributed_max = max(swings) * weight
            else:
                if cls_name in ["Forward Guidance Hike", "Structural Short Squeeze", "Hyper-Specific Narrative Validation"]:
                    contributed_min, contributed_max = 12.0 * weight, 25.0 * weight
                    db_note = "System rule: ≥15% gap-up expected"
                elif direction == "bearish":
                    contributed_min, contributed_max = -20.0 * weight, -10.0 * weight
                    db_note = "Estimated from bearish direction"
                else:
                    contributed_min, contributed_max = 2.0 * weight, 6.0 * weight
                    db_note = "Standard beat estimate"
            total_min += contributed_min
            total_max += contributed_max
            forecast_rows.append({"classification": cls_name, "weight_pct": c.get("weight_pct", 0), "direction": direction, "db_note": db_note, "contributed_min": contributed_min, "contributed_max": contributed_max})

        s_min, s_max = ("+" if total_min >= 0 else ""), ("+" if total_max >= 0 else "")
        net_text = f"High Probability of {s_min}{total_min:.1f}% to {s_max}{total_max:.1f}% Gap {'Up' if dominant_direction == 'bullish' else 'Down'}"
        return {"forecast_rows": forecast_rows, "net_text": net_text, "projected_open": current_price * (1 + (total_min / 100.0)), "dominant_direction": dominant_direction, "directive": "System standard playbook logic applies.", "playbook": "Observe volume trends in first 15 mins."}

    col1, col2 = st.columns([2, 1])
    with col1: raw_news = st.text_area("Raw Headline / Press Release", height=130)
    with col2:
        pe_ticker_input = st.text_input("Ticker", placeholder="e.g. NVDA").strip().upper()
        ref_price = st.number_input("Current / Pre-Market Price ($)", value=0.0, step=1.0)
        predict_btn = st.button("🎯 Analyse Catalysts", type="primary", use_container_width=True)

    if predict_btn and raw_news and pe_ticker_input:
        st.session_state.pe_classifications = _gemini_classify_realtime(pe_ticker_input, raw_news)
        st.session_state.pe_forecast = _build_forecast(st.session_state.pe_classifications, ref_price)
        st.session_state.pe_ticker = pe_ticker_input
        st.session_state.pe_price = ref_price

    if st.session_state.pe_classifications:
        cls_list, fc = st.session_state.pe_classifications, st.session_state.pe_forecast
        st.markdown(f"### Catalyst Breakdown for {st.session_state.pe_ticker}")
        for cls in cls_list:
            st.info(f"**{cls.get('classification')}** ({cls.get('weight_pct')}%) - {cls.get('direction')} - {cls.get('rationale')}")
        st.success(f"**Forecast:** {fc['net_text']} | **Projected Open:** ${fc['projected_open']:.2f}")

# ==========================================
# TAB 4: HISTORICAL CORRELATION DATABASE
# ==========================================
with tab_database:
    st.subheader("🗄️ Historical Correlation Database")
    system.db.load_from_markdown()
    records_list = [{"Ticker": r.ticker, "Event Type": r.event_type, "Trigger Metric": r.trigger_metric, "Resulting Swing": r.resulting_swing, "Classification": r.classification, "Swing Value (%)": r.swing_value} for r in system.db.records]
    st.dataframe(pd.DataFrame(records_list), use_container_width=True, hide_index=True)

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
                new_class = st.selectbox("Catalyst Classification", ["Forward Guidance Hike", "Structural Short Squeeze", "Hyper-Specific Narrative Validation", "Sector Sympathy Rally", "Supply Chain Failure", "Dividend Suspension / Capital Flight", "Earnings Beat", "Earnings Miss"])
                new_swing_val = st.number_input("Numeric Price Swing (%)", value=0.0, step=0.1)

            if st.form_submit_button("Force Manual Record Override"):
                if new_ticker and new_event and new_trigger:
                    system.db.add_record(CatalystRecord(ticker=new_ticker, event_type=new_event, trigger_metric=new_trigger, resulting_swing=new_swing_str if new_swing_str else f"{new_swing_val:+.2f}% (1 Day)", classification=new_class, swing_value=new_swing_val))
                    system.db.save()
                    st.success(f"Successfully added {new_ticker} manually!")
                    st.rerun()

# ==========================================
# TAB 5: MEMORY BANK
# ==========================================
def _classify_catalyst_with_gemini(ticker: str, swing_pct: float, days: int, news_text: str) -> list:
    prompt = f"""You are a quantitative event-driven analyst. A stock ({ticker}) moved {swing_pct:+.2f}% over {days} trading day(s).
The following catalyst news caused that move:
---
{news_text}
---
A single price event can be driven by MULTIPLE distinct catalysts simultaneously. Identify ALL catalysts present and estimate how much of the total price move each one was responsible for.
Return ONLY a valid JSON array matching this exact schema:
[
  {{
    "rank": 1,
    "weight_pct": 45,
    "event_type": "<Earnings / Catalyst | Macro / Sector | Clinical Data / Regulatory | Corporate Action | Guidance Cut>",
    "trigger_metric": "<concise 1-2 sentence description of THIS SPECIFIC catalyst with exact numbers>",
    "classification": "<Forward Guidance Hike | Structural Short Squeeze | Hyper-Specific Narrative Validation | Sector Sympathy Rally | Supply Chain Failure | Dividend Suspension / Capital Flight | Earnings Beat | Earnings Miss | Earnings Beat / Product Hype | Binary Pipeline Success | Mega-Contract Visibility | EBITDA Inflection | Sector Macro Tailwind>",
    "confidence": "<High | Medium | Low>",
    "rationale": "<1 sentence explaining why this specific catalyst drove the move>"
  }}
]
Rules: Include between 1 and 5 distinct catalysts. weight_pct must sum to exactly 100."""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key: raise ValueError("No Gemini API key found.")
        
        resp = requests.post(
            f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 4000, "temperature": 0.2}},
            timeout=25
        )
        resp.raise_for_status()
        raw_resp = resp.json()
        content_parts = raw_resp["candidates"][0]["content"].get("parts", [])
        actual_texts = [p["text"] for p in content_parts if not p.get("thought", False) and "text" in p]
        raw = "".join(actual_texts).strip() if actual_texts else content_parts[-1].get("text", "").strip()
        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        
        result = json.loads(raw)
        if isinstance(result, dict): result = [result]
        total_w = sum(item.get("weight_pct", 0) for item in result)
        if total_w != 100 and total_w > 0:
            for item in result: item["weight_pct"] = round(item.get("weight_pct", 0) * 100 / total_w)
            result[0]["weight_pct"] += 100 - sum(item["weight_pct"] for item in result)
        for item in result:
            item["weighted_swing"] = round(swing_pct * item["weight_pct"] / 100, 2)
        return sorted(result, key=lambda x: x.get("rank", 99))
    except Exception as e:
        return [{"rank": 1, "weight_pct": 100, "weighted_swing": round(swing_pct, 2), "event_type": "Earnings / Catalyst", "trigger_metric": "Event-Driven Release", "classification": "Earnings Beat" if swing_pct >= 0 else "Earnings Miss", "confidence": "Low", "rationale": f"Fallback (API Error: {e})"}]

with tab_memory:
    st.markdown("""
    <div style='margin-bottom:6px'>
        <span style='color:#f59e0b;font-size:1.45rem;font-weight:800;letter-spacing:-0.01em;'>🧠 Memory Bank</span>
        <span style='color:#6b7280;font-size:0.88rem;margin-left:10px;'>Log a historical price event → Gemini classifies the catalyst → Pattern alerts fire for upcoming watchlist tickers</span>
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    if "mb_swing_result" not in st.session_state: st.session_state.mb_swing_result = None
    if "mb_classification" not in st.session_state: st.session_state.mb_classification = None

    s1c1, s1c2, s1c3, s1c4 = st.columns([1.2, 1.4, 1.4, 1.2])
    with s1c1: mb_ticker = st.text_input("Ticker Symbol", value="NBIS").strip().upper()
    with s1c2: mb_start = st.date_input("Start Date", value=datetime.date(2026, 8, 12))
    with s1c3: mb_end = st.date_input("End Date", value=datetime.date(2026, 8, 13))
    with s1c4:
        st.markdown("<br>", unsafe_allow_html=True)
        fetch_btn = st.button("📡 Fetch Price Swing", type="primary", use_container_width=True)

    if fetch_btn:
        with st.spinner(f"Querying yfinance for {mb_ticker}..."):
            st.session_state.mb_swing_result = HistoricalDataFetcher.fetch_historical_swing(mb_ticker, mb_start.strftime("%Y-%m-%d"), mb_end.strftime("%Y-%m-%d"))
            st.session_state.mb_classification = None

    if st.session_state.mb_swing_result and "error" not in st.session_state.mb_swing_result:
        res = st.session_state.mb_swing_result
        st.info(f"**Swing Captured:** {res['swing_pct']:+.2f}% over {res['days']} days.")
        
        mb_news = st.text_area("Raw Catalyst Text", height=150, placeholder="Paste the news that drove the move.")
        if st.button("🤖 Classify with AI", type="primary"):
            with st.spinner("Classifying with Gemini..."):
                cls_results = _classify_catalyst_with_gemini(mb_ticker, res['swing_pct'], res['days'], mb_news)
                st.session_state.mb_classification = cls_results
                for cls in cls_results:
                    system.db.add_record(CatalystRecord(ticker=mb_ticker, event_type=cls.get("event_type", "Earnings / Catalyst"), trigger_metric=cls.get("trigger_metric", "Event Release"), resulting_swing=f"{cls.get('weighted_swing'):+.2f}%", classification=cls.get("classification"), swing_value=cls.get("weighted_swing")))
                system.db.save()
                st.success("Successfully Classified and logged to the Correlation Database!")

    if st.session_state.mb_classification:
        for c in st.session_state.mb_classification:
            st.write(f"**{c.get('classification')}**: {c.get('weight_pct')}% influence ({c.get('weighted_swing'):+.2f}%). *{c.get('rationale')}*")