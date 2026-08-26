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
    load_upcoming_events, save_upcoming_events
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

def delete_ticker(ticker):
    """Permanently deletes the ticker row from the database."""
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ticker_states WHERE ticker = %s;", (ticker,))
        conn.commit()
        st.toast(f"🗑️ Removed {ticker} from database.")
        
        # Remove from custom sorting list
        if ticker in st.session_state.custom_ticker_order:
            st.session_state.custom_ticker_order.remove(ticker)
            
        fetch_worksheet.clear()
    except Exception as e:
        conn.rollback()
        st.error(f"Failed to delete {ticker}: {e}")

def add_ticker(ticker, shares_held=0, avg_cost=None, catalyst_tier="Standard", directive="HOLD"):
    """Inserts a new ticker row into the database so it appears in the PTS worksheet."""
    if not conn: return False
    ticker = (ticker or "").strip().upper()
    if not ticker: return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ticker_states
                    (ticker, shares_held, avg_cost, catalyst_tier, current_directive)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO NOTHING;
                """,
                (ticker, shares_held, avg_cost, catalyst_tier, directive)
            )
        conn.commit()
        st.toast(f"✅ {ticker} added to worksheet.")

        if "custom_ticker_order" in st.session_state and ticker not in st.session_state.custom_ticker_order:
            st.session_state.custom_ticker_order.append(ticker)

        fetch_worksheet.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Failed to add {ticker}: {e}")
        return False

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

    /* Compact Up/Down/Delete controls on the PTS worksheet cards */
    div[class*="st-key-pts_up_"],
    div[class*="st-key-pts_down_"],
    div[class*="st-key-pts_del_"] {
        margin-bottom: 2px !important;
    }
    div[class*="st-key-pts_up_"] button,
    div[class*="st-key-pts_down_"] button,
    div[class*="st-key-pts_del_"] button {
        height: 24px;
        min-height: 0px;
        padding: 0px 6px;
        line-height: 1;
        font-size: 11px;
    }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("📈 Volatility Dashboard")
st.sidebar.subheader("Watchlist Manager")

watchlist_str = st.sidebar.text_area(
    "Active Watchlist Tickers", 
    value=", ".join(st.session_state.watchlist),
    help="Add or remove tickers (comma separated, e.g. NOW, MSFT, AAPL).",
    key="sidebar_watchlist"
)

if st.sidebar.button("Save Watchlist Tickers", key="save_wl_btn"):
    updated_watchlist = [t.strip().upper() for t in watchlist_str.split(",") if t.strip()]
    st.session_state.watchlist = updated_watchlist
    save_watchlist(updated_watchlist)
    st.sidebar.success("Watchlist saved successfully!")
    st.rerun()

st.sidebar.subheader("Configuration")
db_file = st.sidebar.text_input("Database File Path", value=st.session_state.db_path, key="sidebar_db_path")
if db_file != st.session_state.db_path:
    st.session_state.db_path = db_file
    st.session_state.system = EventDrivenVolatilitySystem(db_path=db_file)
    st.rerun()

st.sidebar.info("This system merges Continuous GARCH Volatility (PTS) and Discrete Event Classification (EDPAS) into a single predictive engine.")

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
                    d_low, d_high = f"${dl:.1f}", f"${safe_float(row['etr_day_high']):.1f}"
                    w_low, w_high = f"${safe_float(row['etr_week_low']):.1f}", f"${safe_float(row['etr_week_high']):.1f}"
                else:
                    d_low = f"${live_info.get('d_low'):.1f}" if live_info.get('d_low') else "—"
                    d_high = f"${live_info.get('d_high'):.1f}" if live_info.get('d_high') else "—"
                    w_low = f"${live_info.get('w_low'):.1f}" if live_info.get('w_low') else "—"
                    w_high = f"${live_info.get('w_high'):.1f}" if live_info.get('w_high') else "—"
                
                p_buy_val = safe_float(row['p_buy_mean'])
                if p_buy_val is None or p_buy_val == 0.0:
                    p_buy, underval_str = "—", "Calibrating..."
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
            
                # 4 Columns: Price | Entry Target | Remarks | Discreet Controls
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
                    new_remark = st.text_input(f"Remarks {ticker}", value=remarks_val, placeholder="Add remarks...", label_visibility="collapsed", key=f"pts_rem_{ticker}")
                    if new_remark != remarks_val: update_remarks(ticker, new_remark)
                with c4:
                    st.markdown("<div style='margin-bottom: -15px;'></div>", unsafe_allow_html=True)
                    # Discreet Geometric Arrows and Delete Button
                    st.button("▴", key=f"pts_up_{ticker}", on_click=move_ticker, args=(ticker, "up"), use_container_width=True, help="Move Ticker Up")
                    st.button("▾", key=f"pts_down_{ticker}", on_click=move_ticker, args=(ticker, "down"), use_container_width=True, help="Move Ticker Down")
                    st.button("✕", key=f"pts_del_{ticker}", on_click=delete_ticker, args=(ticker,), use_container_width=True, help="Delete Ticker Data")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Refresh Live Data", use_container_width=True, key="pts_refresh_btn"):
                fetch_worksheet.clear()
                fetch_live_market_data.clear()
                st.rerun()

        st.markdown("---")
        with st.expander("➕ Add Ticker", expanded=not pts_data):
            existing_tickers = [row['ticker'] for row in pts_data] if pts_data else []

            atc1, atc2, atc3 = st.columns([1.2, 1, 1])
            with atc1:
                new_ticker_symbol = st.text_input("Ticker", placeholder="e.g. NVDA", key="pts_add_ticker").strip().upper()
            with atc2:
                new_ticker_shares = st.number_input("Shares Held", min_value=0, value=0, step=1, key="pts_add_shares")
            with atc3:
                new_ticker_avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key="pts_add_avgcost")

            atc4, atc5 = st.columns([1, 1])
            with atc4:
                new_ticker_tier = st.text_input("Catalyst Tier", value="Standard", key="pts_add_tier")
            with atc5:
                new_ticker_directive = st.selectbox(
                    "Directive",
                    ["HOLD", "BUY", "ACCUMULATE", "TRIM", "RUNNER", "STOP_BUY", "SUSPENDED"],
                    key="pts_add_directive"
                )

            if st.button("➕ Add to Worksheet", type="primary", key="pts_add_btn"):
                if not new_ticker_symbol:
                    st.warning("Please enter a ticker symbol.")
                elif new_ticker_symbol in existing_tickers:
                    st.warning(f"{new_ticker_symbol} is already in the worksheet.")
                else:
                    added = add_ticker(
                        new_ticker_symbol,
                        shares_held=new_ticker_shares,
                        avg_cost=new_ticker_avg_cost if new_ticker_avg_cost > 0 else None,
                        catalyst_tier=new_ticker_tier.strip() or "Standard",
                        directive=new_ticker_directive
                    )
                    if added:
                        st.rerun()

# ==========================================
# TAB 2: SCHEDULER & WATCHLIST
# ==========================================
with tab_schedule:
    st.subheader("Event Scheduler & Calendar Automation (Phase 1)")
    col_sync1, col_sync2 = st.columns([1, 3])
    with col_sync1:
        sync_calendar = st.button("Sync Watchlist with Yahoo Finance 🌐", type="primary", use_container_width=True, key="sched_sync_btn")
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
                progress_bar.progress((i + 1) / total_tickers, text=f"Querying metadata for {ticker}...")
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
        "Earnings": {"monitoring_window": "2–3 weeks prior", "impact": "Sharp gap risk, IV expansion"},
        "Ex-Dividend": {"monitoring_window": "1 week prior", "impact": "Price adjusts down by dividend"},
        "Industry Expo / Keynote": {"monitoring_window": "1–2 weeks prior", "impact": "Pre-conference rally"},
        "Index Rebalancing": {"monitoring_window": "3–4 weeks prior", "impact": "Volume spikes"},
        "Legal / Regulatory Milestone": {"monitoring_window": "1–2 weeks prior", "impact": "Asymmetric relief rally"}
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
        else:
            st.info("No upcoming events — all scheduled dates have passed.")
        if st.button("Reset Calendar Schedule", key="sched_reset_btn"):
            st.session_state.upcoming_events = []
            save_upcoming_events([])
            st.rerun()
    else:
        st.info("No pre-scheduled dates currently loaded.")

    st.markdown("---")
    with st.expander("➕ Add Catalyst Event", expanded=False):
        fc1, fc2 = st.columns([1, 1])
        with fc1:
            form_ticker = st.text_input("Ticker", placeholder="e.g. NVDA", key="sched_add_ticker").upper().strip()
        with fc2:
            form_etype = st.selectbox("Event Type", list(EVENT_TYPE_META.keys()), key="sched_add_etype")
        form_date = st.date_input("Scheduled Date", value=datetime.date.today(), key="sched_add_date")
        form_notes = st.text_area("Event Notes (optional)", placeholder="Event context...", key="sched_add_notes")
        if st.button("➕ Add to Calendar", type="primary", key="sched_add_btn"):
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
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    if "pe_classifications" not in st.session_state: st.session_state.pe_classifications = None
    if "pe_forecast" not in st.session_state: st.session_state.pe_forecast = None

    def _gemini_classify_realtime(ticker: str, news_text: str) -> list:
        api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key: return []
        prompt = f"""You are a quantitative analyst reviewing a live news drop for {ticker}. News: {news_text}
Identify ALL distinct catalysts present. Return ONLY a JSON array:
[ {{"rank": 1, "event_type": "...", "trigger_metric": "...", "classification": "...", "weight_pct": 100, "direction": "bullish", "confidence": "High", "rationale": "..."}} ]"""
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
                timeout=25
            )
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
            if isinstance(result, dict): result = [result]
            return sorted(result, key=lambda x: x.get("rank", 99))
        except Exception:
            return []

    def _build_forecast(classifications: list, current_price: float) -> dict:
        total_min, total_max, dominant = 0.0, 0.0, "bullish"
        if sum(c.get("weight_pct", 0) for c in classifications if c.get("direction") == "bearish") > 50: dominant = "bearish"
        for c in classifications:
            w = c.get("weight_pct", 0) / 100.0
            total_min += 5.0 * w if c.get("direction") == "bullish" else -5.0 * w
            total_max += 10.0 * w if c.get("direction") == "bullish" else -10.0 * w
        return {"net_text": f"Swing: {total_min:.1f}% to {total_max:.1f}%", "projected_open": current_price * (1 + (total_min / 100.0)), "dominant_direction": dominant, "directive": "Standard Logic applies."}

    col1, col2 = st.columns([2, 1])
    with col1: 
        raw_news = st.text_area("Raw Headline / Press Release", height=130, key="pe_news")
    with col2:
        pe_ticker_input = st.text_input("Ticker", placeholder="e.g. NVDA", key="pe_ticker").strip().upper()
        ref_price = st.number_input("Current / Pre-Market Price ($)", value=0.0, step=1.0, key="pe_price")
        predict_btn = st.button("🎯 Analyse Catalysts", type="primary", use_container_width=True, key="pe_btn")

    if predict_btn and raw_news and pe_ticker_input:
        st.session_state.pe_classifications = _gemini_classify_realtime(pe_ticker_input, raw_news)
        st.session_state.pe_forecast = _build_forecast(st.session_state.pe_classifications, ref_price)

    if st.session_state.pe_classifications:
        st.success(f"Forecast for {pe_ticker_input}: {st.session_state.pe_forecast['net_text']}")

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
                new_ticker = st.text_input("Ticker", placeholder="AAPL", key="db_ticker").upper()
                new_event = st.text_input("Event Type", placeholder="Earnings", key="db_event")
            with col_f2:
                new_trigger = st.text_input("Specific Trigger Metric", placeholder="Beat Rev", key="db_trigger")
                new_swing_str = st.text_input("Resulting Price Swing String", placeholder="+12.45% (1 Day)", key="db_swing_str")
            with col_f3:
                new_class = st.selectbox("Catalyst Classification", ["Forward Guidance Hike", "Structural Short Squeeze", "Earnings Beat", "Earnings Miss"], key="db_class")
                new_swing_val = st.number_input("Numeric Price Swing (%)", value=0.0, step=0.1, key="db_swing_val")

            if st.form_submit_button("Force Manual Record Override"):
                if new_ticker and new_event and new_trigger:
                    system.db.add_record(CatalystRecord(ticker=new_ticker, event_type=new_event, trigger_metric=new_trigger, resulting_swing=new_swing_str if new_swing_str else f"{new_swing_val:+.2f}% (1 Day)", classification=new_class, swing_value=new_swing_val))
                    system.db.save()
                    st.success(f"Successfully added {new_ticker} manually!")
                    st.rerun()

# ==========================================
# TAB 5: MEMORY BANK
# ==========================================
with tab_memory:
    st.markdown("""
    <div style='margin-bottom:6px'>
        <span style='color:#f59e0b;font-size:1.45rem;font-weight:800;'>🧠 Memory Bank</span>
    </div>
    <hr style='border-color:#1f2937;margin-bottom:20px;'>
    """, unsafe_allow_html=True)

    s1c1, s1c2, s1c3, s1c4 = st.columns([1.2, 1.4, 1.4, 1.2])
    with s1c1: mb_ticker = st.text_input("Ticker Symbol", value="NBIS", key="mb_ticker").strip().upper()
    with s1c2: mb_start = st.date_input("Start Date", value=datetime.date(2026, 8, 12), key="mb_start")
    with s1c3: mb_end = st.date_input("End Date", value=datetime.date(2026, 8, 13), key="mb_end")
    with s1c4:
        st.markdown("<br>", unsafe_allow_html=True)
        fetch_btn = st.button("📡 Fetch Price Swing", type="primary", use_container_width=True, key="mb_fetch")

    if fetch_btn:
        st.info("Fetching yfinance data...")