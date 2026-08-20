"""
trigger_scanner.py — EDPAS Manual Trigger Scanner

Wire this behind a "Scan Watchlist Now" button in Tab 2 (Scheduler & Watchlist).
Runs three independent detectors against a list of tickers and returns a
combined DataFrame of potential-trigger hits — display it in Streamlit and/or
upsert it into Supabase.

Detectors:
  A. detector_calendar     - upcoming earnings-date proximity (yfinance)
  B. detector_news_gemini  - live news classified against your correlation
                              database via Gemini + Google Search grounding
  C. detector_technical    - volume spike + moving-average breakout (yfinance)

INTEGRATION NOTES (read before wiring in):
  - GEMINI_MODEL below is a placeholder — set it to whatever model you
    already call elsewhere in the app (Memory Bank's classification step).
  - build_correlation_library() expects a DataFrame shaped like
    Historical_Correlation_Database.csv: Ticker, Event Type, Trigger Metric,
    Classification, Swing Value (%). Once Tab 3 is reseeded, point this at
    a Supabase read instead of the CSV so the pattern library always
    reflects current System Rules rather than a static snapshot.
  - detector_calendar / detector_technical use yfinance's documented
    attribute surface (checked against the installed yfinance version's
    actual API) but have NOT been run against live market data — this
    sandbox can't reach Yahoo Finance's servers. Test locally before
    wiring into the button.
  - detector_news_gemini needs no separate news API key: Google Search
    grounding lets Gemini fetch + classify in one call.
"""

import json
from datetime import datetime, timedelta

import pandas as pd

GEMINI_MODEL = "gemini-2.5-flash"  # match whatever you use in Memory Bank


# ---------------------------------------------------------------------------
# Shared: correlation pattern library -> compact text block for prompting
# ---------------------------------------------------------------------------

def build_correlation_library(df: pd.DataFrame, max_rows: int = None) -> str:
    """Serialize the correlation database into a compact block for few-shot
    context. Send the full table if you can -- it's small enough (under
    ~90 rows today), and more examples means better classification."""
    rows = df if max_rows is None else df.head(max_rows)
    lines = []
    for _, r in rows.iterrows():
        lines.append(
            f"- [{r['Ticker']}] {r['Event Type']} -> {r['Classification']} "
            f"({r['Swing Value (%)']:+.2f}%): {r['Trigger Metric']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Detector B: news + Gemini classification
# ---------------------------------------------------------------------------

def _build_classification_prompt(ticker: str, library: str) -> str:
    return f"""You are a catalyst-classification engine for a stock volatility system.

REFERENCE LIBRARY (confirmed historical price-catalyst matches):
{library}

TASK: Search for genuine, recent (last 3 trading days) news, filings, or
public statements about {ticker}. Compare what you find against the
Classification patterns in the reference library above. Only report a
match if a real, current event resembles one of these patterns -- do not
force a match if nothing fits.

Respond with ONLY a JSON object. No markdown fences, no preamble, no text
before or after the JSON.
{{
  "ticker": "{ticker}",
  "match_found": true or false,
  "event_type": "<one of: Earnings / Catalyst, Macro / Sector, Corporate Action, Guidance Cut, Clinical Data / Regulatory, or null>",
  "classification": "<matching Classification from the library, or null>",
  "confidence": <integer 0-100>,
  "closest_historical_match": "<ticker + short description of the library row it resembles, or null>",
  "reasoning": "<1-2 sentences>",
  "trigger_summary": "<1 sentence describing what actually happened, or null>"
}}"""


def _parse_json_response(raw_text: str) -> dict:
    """Gemini sometimes wraps JSON in markdown fences despite instructions
    not to -- strip them before parsing."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return json.loads(cleaned)


def detector_news_gemini(tickers: list, correlation_df: pd.DataFrame,
                          api_key: str) -> list:
    """One grounded Gemini call per ticker. Synchronous -- fine for a
    manual-trigger button; each call typically takes a few seconds."""
    from google import genai
    from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

    client = genai.Client(api_key=api_key)
    library = build_correlation_library(correlation_df)
    search_tool = Tool(google_search=GoogleSearch())
    results = []

    for ticker in tickers:
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=_build_classification_prompt(ticker, library),
                config=GenerateContentConfig(tools=[search_tool]),
            )
            parsed = _parse_json_response(response.text)
            parsed["detector"] = "news_gemini"
            results.append(parsed)
        except Exception as e:
            results.append({
                "ticker": ticker, "match_found": False,
                "detector": "news_gemini", "error": str(e),
            })
    return results


# ---------------------------------------------------------------------------
# Detector C: technical -- volume spike + moving-average breakout
# (rule-based, no LLM call, cheap enough to run every time)
# ---------------------------------------------------------------------------

def detector_technical(tickers: list, volume_multiple: float = 2.0) -> list:
    import yfinance as yf

    results = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="6mo")
            if len(hist) < 100:
                results.append({"ticker": ticker, "match_found": False,
                                 "detector": "technical", "note": "insufficient history"})
                continue

            hist["avg_vol_20d"] = hist["Volume"].rolling(20).mean()
            hist["sma20"] = hist["Close"].rolling(20).mean()
            hist["sma50"] = hist["Close"].rolling(50).mean()
            hist["sma100"] = hist["Close"].rolling(100).mean()
            latest = hist.iloc[-1]

            volume_spike = latest["Volume"] > volume_multiple * latest["avg_vol_20d"]
            breakout = latest["Close"] > latest["sma20"] > latest["sma50"] > latest["sma100"]
            hit = bool(volume_spike and breakout)

            results.append({
                "ticker": ticker,
                "detector": "technical",
                "match_found": hit,
                "classification": "Structural Short Squeeze" if hit else None,
                "confidence": 65 if hit else 0,
                "trigger_summary": (
                    f"Volume {latest['Volume']:,.0f} vs 20d avg {latest['avg_vol_20d']:,.0f}; "
                    f"close {latest['Close']:.2f} vs SMA20/50/100 "
                    f"{latest['sma20']:.2f}/{latest['sma50']:.2f}/{latest['sma100']:.2f}"
                ) if hit else None,
            })
        except Exception as e:
            results.append({"ticker": ticker, "match_found": False,
                             "detector": "technical", "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Detector A: calendar -- flags tickers entering a pre-earnings window
# ---------------------------------------------------------------------------

def detector_calendar(tickers: list, days_ahead: int = 10) -> list:
    import yfinance as yf

    results = []
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    for ticker in tickers:
        try:
            dates_df = yf.Ticker(ticker).earnings_dates
            # NOTE: use len() rather than .empty -- a DataFrame with rows but
            # no columns (as some yfinance responses can be) still reports
            # .empty == True, which would silently swallow a real match.
            if dates_df is None or len(dates_df) == 0:
                results.append({"ticker": ticker, "match_found": False,
                                 "detector": "calendar", "note": "no earnings date found"})
                continue

            upcoming = []
            for d in dates_df.index:
                d_naive = d.tz_localize(None) if getattr(d, "tzinfo", None) is not None else d
                if now <= d_naive <= cutoff:
                    upcoming.append(d_naive)

            results.append({
                "ticker": ticker,
                "detector": "calendar",
                "match_found": bool(upcoming),
                "event_type": "Earnings / Catalyst" if upcoming else None,
                "trigger_summary": f"Earnings expected {upcoming[0].date()}" if upcoming else None,
            })
        except Exception as e:
            results.append({"ticker": ticker, "match_found": False,
                             "detector": "calendar", "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Orchestrator -- call this from your "Scan Watchlist Now" button
# ---------------------------------------------------------------------------

def run_scan(tickers: list, correlation_df: pd.DataFrame, gemini_api_key: str) -> pd.DataFrame:
    all_results = []
    all_results.extend(detector_calendar(tickers))
    all_results.extend(detector_technical(tickers))
    all_results.extend(detector_news_gemini(tickers, correlation_df, gemini_api_key))
    df = pd.DataFrame(all_results)
    df["scanned_at"] = datetime.now().isoformat()
    return df
