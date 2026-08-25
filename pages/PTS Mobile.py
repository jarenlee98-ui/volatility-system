import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Mobile-friendly configuration
st.set_page_config(page_title="PTS Mobile", page_icon="⚡", layout="centered")

st.markdown("<h3 style='text-align: center; color: #3b82f6;'>⚡ PTS-v1 Mobile</h3>", unsafe_allow_html=True)
st.caption("Live GJR-GARCH Volatility Matrix")

# 1. Connect directly to your Neon Database
@st.cache_resource(ttl=60)
def get_db_connection():
    # Fetch URL from Streamlit Cloud Secrets or local .env
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

# 2. Fetch the current worksheet
@st.cache_data(ttl=30)
def fetch_worksheet():
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, close_price, shares_held, avg_cost, current_directive, 
                       catalyst_tier, regime_scalar, etr_day_low, etr_day_high, 
                       p_buy_mean, underval_pct, remarks, is_suspended 
                FROM ticker_states 
                ORDER BY ticker ASC;
            """)
            return cur.fetchall()
    except Exception as e:
        st.error(f"Query Error: {e}")
        return []

data = fetch_worksheet()

# 3. Render the Mobile UI Cards
if not data:
    st.info("No assets found in the database.")
else:
    for row in data:
        # Number formatting guardrails
        close_px = f"${float(row['close_price']):.2f}" if row['close_price'] is not None else "—"
        shares = row['shares_held'] or 0
        avg_cost = f"${float(row['avg_cost']):.2f}" if row['avg_cost'] is not None else "—"
        is_watch = shares == 0

        # Colors for Directives
        directive = row['current_directive'] or "HOLD"
        d_color = "#f59e0b" # amber
        if directive in ["BUY", "ACCUMULATE"]: d_color = "#10b981" # green
        elif directive in ["TRIM", "SUSPENDED"]: d_color = "#ef4444" # red
        elif directive == "RUNNER": d_color = "#8b5cf6" # purple

        # Extract Metrics
        d_low = f"${float(row['etr_day_low']):.1f}" if row['etr_day_low'] is not None else "—"
        d_high = f"${float(row['etr_day_high']):.1f}" if row['etr_day_high'] is not None else "—"
        p_buy = f"${float(row['p_buy_mean']):.2f}" if row['p_buy_mean'] is not None else "—"
        underval = float(row['underval_pct'] or 0) * 100
        underval_str = f"↓ {abs(underval):.1f}%" if underval >= 0 else f"↑ {abs(underval):.1f}%"
        scalar = f"{float(row['regime_scalar'] or 1):.2f}×"

        # HTML Card UI
        st.markdown(f"""
        <div style="background-color: #111827; border: 1px solid #1f293d; border-radius: 10px; padding: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <div>
                    <span style="font-size: 18px; font-weight: 800; color: white;">{row['ticker']}</span>
                    <div style="font-size: 11px; color: #9ca3af;">
                        {'<span style="color:#8b5cf6">Watchlist</span>' if is_watch else f"{shares} shs @ {avg_cost}"}
                    </div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: {d_color}33; color: {d_color};">{directive}</span>
                    <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">Cat: <strong style="color:white;">{row['catalyst_tier'] or 'Std'}</strong></div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; background: #0b111e; padding: 8px; border-radius: 6px;">
                <div>
                    <div style="font-size: 9px; color: #9ca3af; text-transform: uppercase;">Price</div>
                    <div style="font-size: 13px; font-weight: 600; color: #e5e7eb;">{close_px}</div>
                    <div style="font-size: 10px; color: #9ca3af;">D: {d_low}-{d_high}</div>
                </div>
                <div>
                    <div style="font-size: 9px; color: #9ca3af; text-transform: uppercase;">Regime</div>
                    <div style="font-size: 13px; font-weight: 600; color: #e5e7eb;">{scalar}</div>
                    <div style="font-size: 10px; color: #9ca3af;">Volatility</div>
                </div>
                <div>
                    <div style="font-size: 9px; color: #9ca3af; text-transform: uppercase;">Entry Target</div>
                    <div style="font-size: 13px; font-weight: 600; color: #3b82f6;">{p_buy}</div>
                    <div style="font-size: 10px; color: #9ca3af;">{underval_str}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    st.button("🔄 Refresh Data", use_container_width=True)