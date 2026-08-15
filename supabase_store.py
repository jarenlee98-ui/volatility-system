"""
supabase_store.py
-----------------
Drop-in cloud persistence layer replacing local flat-file storage.
Called by app.py instead of open()/json.load() when SUPABASE_URL is set.

Tables required in your Supabase project (SQL in README):
  - catalyst_records   (id, ticker, event_type, trigger_metric, resulting_swing, classification, swing_value)
  - watchlist          (id, ticker)
  - upcoming_events    (id, ticker, event_type, timing)
"""

import os
import json
import streamlit as st

# ── detect whether Supabase is configured ──────────────────────────────────────

def _is_configured() -> bool:
    try:
        url = st.secrets.get("SUPABASE_URL", "") or os.environ.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_KEY", "")
        return bool(url and key)
    except Exception:
        return False

def _client():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL") or os.environ["SUPABASE_URL"]
        key = st.secrets.get("SUPABASE_KEY") or os.environ["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        raise RuntimeError(f"Supabase connection failed: {e}")

IS_CLOUD = _is_configured()


# ── Watchlist ──────────────────────────────────────────────────────────────────

def load_watchlist(fallback_path: str = "watchlist.json") -> list:
    if IS_CLOUD:
        try:
            sb = _client()
            rows = sb.table("watchlist").select("ticker").execute().data
            return [r["ticker"] for r in rows] if rows else []
        except Exception as e:
            st.warning(f"Supabase watchlist load failed, using local file. ({e})")
    # Local fallback
    if os.path.exists(fallback_path):
        with open(fallback_path, "r") as f:
            return json.load(f)
    return []


def save_watchlist(tickers: list, fallback_path: str = "watchlist.json"):
    if IS_CLOUD:
        try:
            sb = _client()
            sb.table("watchlist").delete().neq("id", 0).execute()
            if tickers:
                sb.table("watchlist").insert([{"ticker": t} for t in tickers]).execute()
            return
        except Exception as e:
            st.warning(f"Supabase watchlist save failed, falling back to local. ({e})")
    with open(fallback_path, "w") as f:
        json.dump(tickers, f)


# ── Upcoming Events ────────────────────────────────────────────────────────────

def load_upcoming_events(fallback_path: str = "upcoming_events.json") -> list:
    if IS_CLOUD:
        try:
            sb = _client()
            rows = sb.table("upcoming_events").select("ticker,event_type,timing").execute().data
            return rows if rows else []
        except Exception as e:
            st.warning(f"Supabase events load failed, using local file. ({e})")
    if os.path.exists(fallback_path):
        with open(fallback_path, "r") as f:
            return json.load(f)
    return []


def save_upcoming_events(events: list, fallback_path: str = "upcoming_events.json"):
    if IS_CLOUD:
        try:
            sb = _client()
            sb.table("upcoming_events").delete().neq("id", 0).execute()
            if events:
                sb.table("upcoming_events").insert(events).execute()
            return
        except Exception as e:
            st.warning(f"Supabase events save failed, falling back to local. ({e})")
    with open(fallback_path, "w") as f:
        json.dump(events, f)


# ── Catalyst Records ───────────────────────────────────────────────────────────

def load_catalyst_records(fallback_path: str = "Catalyst_Correlations.md") -> list:
    """
    Returns raw rows as list of dicts. CatalystDatabase.load_from_supabase() calls this.
    """
    if IS_CLOUD:
        try:
            sb = _client()
            rows = sb.table("catalyst_records").select(
                "ticker,event_type,trigger_metric,resulting_swing,classification,swing_value"
            ).order("id").execute().data
            return rows if rows else []
        except Exception as e:
            st.warning(f"Supabase records load failed, using local file. ({e})")
    return []  # empty → CatalystDatabase falls back to load_from_markdown()


def save_catalyst_records(records: list, fallback_path: str = "Catalyst_Correlations.md"):
    """
    Accepts list of CatalystRecord dataclass instances.
    """
    if IS_CLOUD:
        try:
            sb = _client()
            sb.table("catalyst_records").delete().neq("id", 0).execute()
            if records:
                rows = [
                    {
                        "ticker": r.ticker,
                        "event_type": r.event_type,
                        "trigger_metric": r.trigger_metric,
                        "resulting_swing": r.resulting_swing,
                        "classification": r.classification,
                        "swing_value": r.swing_value,
                    }
                    for r in records
                ]
                sb.table("catalyst_records").insert(rows).execute()
            return True
        except Exception as e:
            st.warning(f"Supabase records save failed, falling back to local file. ({e})")
    return False  # signal caller to fall back to markdown save
