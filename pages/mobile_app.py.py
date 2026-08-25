import streamlit as st
import pandas as pd
import os
import json
import re
import datetime
import requests
from supabase_store import (
    load_watchlist, save_watchlist,
    load_upcoming_events, save_upcoming_events
)

try:
    from volatility_system import (
        EventDrivenVolatilitySystem, CatalystRecord, LiveDataFetcher, HistoricalDataFetcher, EventParser
    )
except ImportError:
    pass # Ensure your local module files are in the same directory

# 1. Mobile-Optimized Config
st.set_page_config(
    page_title="EDPAS Mobile",
    page_icon="📱",
    layout="centered", # Better for mobile than "wide"
    initial_sidebar_state="collapsed" # Save screen real estate on mobile
)

DB_FILE_PATH = "Catalyst_Correlations.md"
if "db_path" not in st.session_state:
    st.session_state.db_path = DB_FILE_PATH
if "system" not in st.session_state:
    st.session_state.system = EventDrivenVolatilitySystem(db_path=st.session_state.db_path)
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

# 2. Mobile Custom CSS
st.markdown("""
<style>
    /* Compact padding for mobile screens */
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; padding-left: 1rem; padding-right: 1rem; }
    .mobile-card { background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
    .mobile-title { color: #60a5fa; font-size: 1.2rem; font-weight: 800; margin-bottom: 4px; }
    .mobile-label { color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .mobile-value { color: #e5e7eb; font-size: 1rem; font-weight: 600; }
    .mobile-btn { width: 100%; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='mobile-title'>📱 EDPAS Mobile</div>", unsafe_allow_html=True)
st.caption("Event-Driven Volatility Correlation System")

# 3. Mobile Navigation via Tabs
tab_predict, tab_memory, tab_watch = st.tabs(["🎯 Predict", "🧠 Memory", "📅 Watch"])

# --- CORE LLM FUNCTION (Using gemini-3.5-flash with thought filtering) ---
def _run_gemini_classification(ticker: str, news_text: str, is_memory_bank: bool = False, swing_pct: float = 0.0, days: int = 1) -> list:
    api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("No API Key.")
        return []

    # Prompt logic adapts based on whether it is a live prediction or historical memory log
    if is_memory_bank:
        prompt = f"Analyze {ticker} which moved {swing_pct:+.2f}% over {days} days due to this news:\n{news_text}\nOutput a JSON array of up to 5 catalysts. Each must have: rank, weight_pct (must sum to 100), event_type, trigger_metric, classification, confidence, rationale."
    else:
        prompt = f"Analyze live news for {ticker}:\n{news_text}\nOutput a JSON array of up to 5 catalysts. Each must have: rank, weight_pct (sum to 100), event_type, trigger_metric, classification, direction (bullish/bearish), confidence, rationale."

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 2000,
                    "temperature": 0.2
                }
            },
            timeout=25
        )
        resp.raise_for_status()
        raw_resp = resp.json()

        # Safely bypass internal reasoning/thought parts from 3.5-flash
        content_parts = raw_resp["candidates"][0]["content"].get("parts", [])
        actual_texts = [p["text"] for p in content_parts if not p.get("thought", False) and "text" in p]
        raw = "".join(actual_texts).strip() if actual_texts else content_parts[-1].get("text", "").strip()

        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        return result if isinstance(result, list) else [result]
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

# ==========================================
# TAB 1: REAL-TIME PREDICTION
# ==========================================
with tab_predict:
    st.markdown("<div class='mobile-label'>Live News Drop</div>", unsafe_allow_html=True)
    pe_ticker = st.text_input("Ticker", placeholder="NVDA").upper()
    pe_price = st.number_input("Pre-Market Price ($)", value=0.0)
    pe_news = st.text_area("News Headline / PR", height=100)
    
    if st.button("🎯 Predict Swing", type="primary", use_container_width=True):
        if pe_ticker and pe_news:
            with st.spinner("Analyzing..."):
                results = _run_gemini_classification(pe_ticker, pe_news)
                if results:
                    st.success(f"Found {len(results)} catalysts.")
                    for res in results:
                        dir_icon = "📈" if res.get('direction') == 'bullish' else "📉"
                        st.markdown(f"""
                        <div class="mobile-card">
                            <div style="display:flex; justify-content:space-between;">
                                <span style="font-weight:bold; color:#60a5fa;">{res.get('classification')}</span>
                                <span>{dir_icon} {res.get('weight_pct')}%</span>
                            </div>
                            <div style="font-size:0.85rem; color:#d1d5db; margin-top:6px;">{res.get('trigger_metric')}</div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.error("Input required.")

# ==========================================
# TAB 2: MEMORY BANK
# ==========================================
with tab_memory:
    st.markdown("<div class='mobile-label'>Look-Back Catalyst Extraction</div>", unsafe_allow_html=True)
    mb_ticker = st.text_input("Ticker to Log", placeholder="NBIS").upper()
    
    col1, col2 = st.columns(2)
    with col1:
        mb_start = st.date_input("Start Date", value=datetime.date.today())
    with col2:
        mb_end = st.date_input("End Date", value=datetime.date.today())
        
    mb_news = st.text_area("Historical News Drop", height=100)
    
    if st.button("🧠 Extract & Save", type="primary", use_container_width=True):
        if mb_ticker and mb_news:
            with st.spinner("Fetching yfinance data..."):
                swing_data = HistoricalDataFetcher.fetch_historical_swing(
                    mb_ticker, mb_start.strftime("%Y-%m-%d"), mb_end.strftime("%Y-%m-%d")
                )
            
            if "error" not in swing_data:
                swing_pct = swing_data["swing_pct"]
                st.info(f"Calculated Swing: {swing_pct:+.2f}%")
                
                with st.spinner("Classifying with Gemini 3.5 Flash..."):
                    results = _run_gemini_classification(mb_ticker, mb_news, True, swing_pct, swing_data["days"])
                    if results:
                        st.success("Logged to Database!")
            else:
                st.error(swing_data["error"])

# ==========================================
# TAB 3: WATCHLIST & SCHEDULER
# ==========================================
with tab_watch:
    watchlist_str = st.text_area("Active Watchlist", value=", ".join(st.session_state.watchlist))
    if st.button("💾 Save Watchlist", use_container_width=True):
        updated = [t.strip().upper() for t in watchlist_str.split(",") if t.strip()]
        st.session_state.watchlist = updated
        save_watchlist(updated)
        st.success("Saved!")
        
    if st.button("🌐 Sync with Yahoo Finance", type="primary", use_container_width=True):
        st.info("Syncing events for mobile view...")
        # Add your Yahoo Finance sync logic here