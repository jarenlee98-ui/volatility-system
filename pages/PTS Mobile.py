import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Mobile-friendly configuration
st.set_page_config(page_title="PTS Mobile", page_icon="⚡", layout="centered")

st.markdown("<h3 style='text-align: center; color: #3b82f6; margin-bottom: 0;'>⚡ PTS-v1 Mobile</h3>", unsafe_allow_html=True)

# 1. Connect directly to your Neon Database
@st.cache_resource(ttl=60)
def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))
    if not db_url:
        return None
    try:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

conn = get_db_connection()

if not conn:
    st.warning("⚠️ Waiting for DATABASE_URL secret to be added to Streamlit Cloud.")
    st.stop()

# 2. Database Fetch & Update Functions
@st.cache_data(ttl=30)
def fetch_worksheet():
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
    except Exception as e:
        st.error(f"Query Error: {e}")
        return []

def update_remarks(ticker, new_remark):
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ticker_states SET remarks = %s WHERE ticker = %s;", (new_remark, ticker))
        conn.commit()
        st.toast(f"✅ Remarks saved for {ticker}")
        fetch_worksheet.clear()
    except Exception as e:
        conn.rollback()
        st.error(f"Failed to save remark: {e}")

data = fetch_worksheet()

if not data:
    st.info("No assets found in the database.")
    st.stop()

# 3. Ticker Ordering Logic with Up/Down Controls
all_tickers = [row['ticker'] for row in data]

if 'custom_ticker_order' not in st.session_state:
    st.session_state.custom_ticker_order = all_tickers

# Sync with DB tickers
current_order = [t for t in st.session_state.custom_ticker_order if t in all_tickers]
missing_tickers = [t for t in all_tickers if t not in current_order]
st.session_state.custom_ticker_order = current_order + missing_tickers

def move_ticker(ticker, direction):
    idx = st.session_state.custom_ticker_order.index(ticker)
    if direction == "up" and idx > 0:
        st.session_state.custom_ticker_order[idx], st.session_state.custom_ticker_order[idx - 1] = (
            st.session_state.custom_ticker_order[idx - 1],
            st.session_state.custom_ticker_order[idx]
        )
    elif direction == "down" and idx < len(st.session_state.custom_ticker_order) - 1:
        st.session_state.custom_ticker_order[idx], st.session_state.custom_ticker_order[idx + 1] = (
            st.session_state.custom_ticker_order[idx + 1],
            st.session_state.custom_ticker_order[idx]
        )
    st.rerun()

# 4. Render Mobile Cards
data_dict = {row['ticker']: row for row in data}
sorted_data = [data_dict[t] for t in st.session_state.custom_ticker_order if t in data_dict]

for row in sorted_data:
    ticker = row['ticker']
    close_px = f"${float(row['close_price']):.2f}" if row['close_price'] is not None else "—"
    shares = row['shares_held'] or 0
    avg_cost = f"${float(row['avg_cost']):.2f}" if row['avg_cost'] is not None else "—"
    is_watch = shares == 0

    directive = row['current_directive'] or "HOLD"
    d_color = "#f59e0b"
    if directive in ["BUY", "ACCUMULATE"]: d_color = "#10b981"
    elif directive in ["TRIM", "SUSPENDED"]: d_color = "#ef4444"
    elif directive == "RUNNER": d_color = "#8b5cf6"

    d_low = f"${float(row['etr_day_low']):.1f}" if row['etr_day_low'] is not None else "—"
    d_high = f"${float(row['etr_day_high']):.1f}" if row['etr_day_high'] is not None else "—"
    w_low = f"${float(row['etr_week_low']):.1f}" if row['etr_week_low'] is not None else "—"
    w_high = f"${float(row['etr_week_high']):.1f}" if row['etr_week_high'] is not None else "—"
    p_buy = f"${float(row['p_buy_mean']):.2f}" if row['p_buy_mean'] is not None else "—"
    
    underval = float(row['underval_pct'] or 0) * 100
    underval_str = f"↓ {abs(underval):.1f}%" if underval >= 0 else f"↑ {abs(underval):.1f}%"
    remarks_val = row['remarks'] if row['remarks'] else ""

    # Card Top: Ticker, Position, Directive, and Reorder Buttons
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

    # 3-Column Layout: [Price (1.1x)] | [Entry Target (1.1x)] | [Remarks + Order (2x)]
    c1, c2, c3 = st.columns([1.1, 1.1, 2.0], gap="small")
    
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

        # Up/Down Reorder Buttons
        btn_u, btn_d = st.columns(2)
        with btn_u:
            st.button("⬆ Move Up", key=f"up_{ticker}", on_click=move_ticker, args=(ticker, "up"), use_container_width=True)
        with btn_d:
            st.button("⬇ Move Down", key=f"down_{ticker}", on_click=move_ticker, args=(ticker, "down"), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
st.button("🔄 Refresh Data", use_container_width=True, on_click=fetch_worksheet.clear)