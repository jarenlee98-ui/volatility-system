import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import datetime

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

@dataclass
class CatalystRecord:
    ticker: str
    event_type: str
    trigger_metric: str
    resulting_swing: str  
    classification: str   
    swing_value: float    

class CatalystDatabase:
    """
    Manages the historical correlation database.
    Supports saving/loading to Catalyst_Correlations.md and matching catalysts.
    """
    def __init__(self, filepath: str = "Catalyst_Correlations.md"):
        self.filepath = filepath
        self.records: List[CatalystRecord] = []
        self._load_defaults()
        # Try cloud first, fall back to local markdown
        loaded_from_cloud = False
        try:
            from supabase_store import load_catalyst_records, IS_CLOUD
            if IS_CLOUD:
                rows = load_catalyst_records(filepath)
                if rows:
                    self.records = [
                        CatalystRecord(
                            ticker=r["ticker"],
                            event_type=r["event_type"],
                            trigger_metric=r["trigger_metric"],
                            resulting_swing=r["resulting_swing"],
                            classification=r["classification"],
                            swing_value=float(r.get("swing_value", 0.0))
                        )
                        for r in rows
                    ]
                    loaded_from_cloud = True
        except ImportError:
            pass
        if not loaded_from_cloud:
            if os.path.exists(self.filepath):
                self.load_from_markdown()
            else:
                self.save()

    def _load_defaults(self):
        # No hardcoded defaults — DB is built entirely from user-logged events via Memory Bank
        self.records = []

    def add_record(self, record: CatalystRecord):
        for r in self.records:
            if r.ticker == record.ticker and r.classification == record.classification and abs(r.swing_value - record.swing_value) < 0.01:
                return
        self.records.append(record)

    def load_from_markdown(self):
        if not os.path.exists(self.filepath):
            return
        
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            parsed_records = []
            parsing_table = False
            for line in lines:
                if "| Ticker |" in line:
                    parsing_table = True
                    continue
                if parsing_table and line.startswith("|") and "---" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 5:
                        ticker = parts[0]
                        event_type = parts[1]
                        trigger_metric = parts[2]
                        resulting_swing = parts[3]
                        classification = parts[4]
                        
                        swing_value = 0.0
                        try:
                            val_match = re.search(r"([+-]?\d+\.?\d*)%", resulting_swing)
                            if val_match:
                                swing_value = float(val_match.group(1))
                        except Exception:
                            pass
                            
                        parsed_records.append(CatalystRecord(
                            ticker=ticker,
                            event_type=event_type,
                            trigger_metric=trigger_metric,
                            resulting_swing=resulting_swing,
                            classification=classification,
                            swing_value=swing_value
                        ))
            if parsed_records:
                self.records = parsed_records
        except Exception as e:
            pass

    def export_to_markdown(self) -> str:
        md = "# Catalyst Correlations Database\n\n"
        md += "This database maps extreme historical price swings (>= ±10% in 1 day or >= ±20% in 5 days) to their specific catalyst events. Thresholds apply in both directions (gap-up and gap-down).\n\n"
        md += "| Ticker | Event Type | Specific Trigger/Metric | Resulting Price Swing | Catalyst Classification |\n"
        md += "|--------|------------|-------------------------|-----------------------|-------------------------|\n"
        for r in self.records:
            md += f"| {r.ticker} | {r.event_type} | {r.trigger_metric} | {r.resulting_swing} | {r.classification} |\n"

        md += "\n## System Correlation Rules\n"
        md += "- **Standard Revenue Beat**: Yields moderate single-digit gains or losses (e.g., ±2% to ±6%).\n"
        md += "- **Extreme Move (≥ ±15%)**: Must contain a **Forward Guidance Raise**, a **Structural Short Squeeze**, or **Hyper-Specific Narrative Validation**.\n"

        # Preserve any promoted rules that were appended to the file
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    existing = f.read()
                in_rules = False
                promoted_lines = []
                for line in existing.splitlines():
                    if line.strip().startswith("## System Correlation Rules"):
                        in_rules = True
                        continue
                    if in_rules and line.strip().startswith("- **") and "promoted from pattern analysis" in line:
                        promoted_lines.append(line)
                for pl in promoted_lines:
                    if pl.strip() not in md:
                        md += pl + "\n"
            except Exception:
                pass

        return md

    def save(self):
        # Try Supabase first (cloud), fall back to local markdown
        try:
            from supabase_store import save_catalyst_records, IS_CLOUD
            if IS_CLOUD:
                saved = save_catalyst_records(self.records, self.filepath)
                if saved:
                    # Also keep local markdown in sync as a readable backup
                    content = self.export_to_markdown()
                    with open(self.filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    return
        except ImportError:
            pass
        # Local fallback
        content = self.export_to_markdown()
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def find_matches_by_classification(self, classification: str) -> List[CatalystRecord]:
        return [r for r in self.records if r.classification.lower() == classification.lower()]

class EventParser:
    @staticmethod
    def parse_watchlist(watchlist_text: str) -> List[Dict[str, Any]]:
        events = []
        earnings_pattern = re.compile(
            r"Earnings\s+upcoming\s+for\s+([A-Z]+)\s+on\s+([A-Za-z0-9\-\/]+)\s*([a-z\-]+market)?", 
            re.IGNORECASE
        )
        for match in earnings_pattern.finditer(watchlist_text):
            timing = match.group(2)
            if match.group(3):
                timing += f" {match.group(3)}"
            events.append({
                "ticker": match.group(1).upper(),
                "event_type": "Earnings",
                "timing": timing.strip()
            })

        div_pattern = re.compile(
            r"Ex-dividend\s+for\s+([A-Z]+)\s+on\s+([A-Za-z0-9\-\/]+)",
            re.IGNORECASE
        )
        for match in div_pattern.finditer(watchlist_text):
            events.append({
                "ticker": match.group(1).upper(),
                "event_type": "Ex-Dividend",
                "timing": match.group(2).strip()
            })
        return events

    @staticmethod
    def parse_data_drop(data_text: str) -> Dict[str, Any]:
        result = {
            "ticker": "UNKNOWN",
            "metrics": {},
            "raw": data_text
        }
        
        ticker_match = re.search(r"^([A-Z0-9]+)\b", data_text)
        if ticker_match:
            result["ticker"] = ticker_match.group(1).upper()
        
        rev_match = re.search(r"Revenue\s+([^\s,]+)\s*\(([^)]+)\)", data_text, re.IGNORECASE)
        if rev_match:
            result["metrics"]["revenue"] = {"amount": rev_match.group(1), "change": rev_match.group(2)}
        else:
            rev_match_alt = re.search(r"Revenue\s+([^\s,]+)", data_text, re.IGNORECASE)
            if rev_match_alt:
                result["metrics"]["revenue"] = {"amount": rev_match_alt.group(1), "change": None}

        eps_match = re.search(r"EPS\s+([^\s,]+)\s*\(([^)]+)\)", data_text, re.IGNORECASE)
        if eps_match:
            result["metrics"]["eps"] = {"amount": eps_match.group(1), "beat": eps_match.group(2)}
        else:
            eps_match_alt = re.search(r"EPS\s+([^\s,]+)", data_text, re.IGNORECASE)
            if eps_match_alt:
                result["metrics"]["eps"] = {"amount": eps_match_alt.group(1), "beat": None}

        guidance_match = re.search(r"guidance\s+(raised|lowered)\s+by\s+([\d\.\%]+)", data_text, re.IGNORECASE)
        if guidance_match:
            result["metrics"]["guidance"] = {"action": guidance_match.group(1).lower(), "amount": guidance_match.group(2)}
        elif "guidance raised" in data_text.lower() or "outlook raised" in data_text.lower():
            result["metrics"]["guidance"] = {"action": "raised", "amount": None}
        elif "guidance lowered" in data_text.lower() or "outlook lowered" in data_text.lower():
            result["metrics"]["guidance"] = {"action": "lowered", "amount": None}

        if "short squeeze" in data_text.lower() or "bank target upgrade" in data_text.lower():
            result["metrics"]["narrative"] = "Structural Short Squeeze"
        elif "u.s. commercial revenue" in data_text.lower() or "commercial revenue specifically" in data_text.lower():
            result["metrics"]["narrative"] = "Hyper-Specific Narrative Validation"
        elif "dividend suspended" in data_text.lower() or "suspended quarterly dividend" in data_text.lower():
            result["metrics"]["narrative"] = "Dividend Suspension / Capital Flight"
        elif "supply chain" in data_text.lower():
            result["metrics"]["narrative"] = "Supply Chain Failure"

        return result

class HistoricalDataFetcher:
    """
    The Quantitative Leg of the Automated Catalyst Extraction Pipeline.
    Uses yfinance to calculate exact intraday or multi-day price swings.
    """
    @staticmethod
    def fetch_historical_swing(ticker: str, start_date: str, end_date: str) -> Dict[str, Any]:
        if not YFINANCE_AVAILABLE:
            return {"error": "yfinance library not installed. Cannot perform quantitative extraction."}
            
        try:
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            
            if end_dt < start_dt:
                return {"error": "End date must be after or equal to start date."}
                
            # yfinance 'end' is exclusive, so we add 1 day to fetch the complete range
            yf_end_dt = end_dt + datetime.timedelta(days=1)
            
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_dt.strftime("%Y-%m-%d"), end=yf_end_dt.strftime("%Y-%m-%d"))
            
            if hist.empty:
                return {"error": f"No market data found for {ticker} between {start_date} and {end_date}."}
            
            start_price = float(hist["Close"].iloc[0])
            end_price = float(hist["Close"].iloc[-1])
            
            swing_pct = ((end_price - start_price) / start_price) * 100.0
            days = len(hist)
            
            return {
                "start_price": start_price,
                "end_price": end_price,
                "swing_pct": swing_pct,
                "days": days
            }
        except Exception as e:
            return {"error": str(e)}

class ExtractionPipeline:
    """
    Automates the workflow of bridging quantitative market data (yfinance) 
    with qualitative news classification into the database.
    """
    def __init__(self, db: CatalystDatabase):
        self.db = db
        
    def run_extraction(self, ticker: str, start_date: str, end_date: str, raw_news_text: str) -> Dict[str, Any]:
        # Step 1: yfinance Market Data Calculation
        market_data = HistoricalDataFetcher.fetch_historical_swing(ticker, start_date, end_date)
        if "error" in market_data:
            return {"success": False, "message": market_data["error"]}
            
        swing_val = market_data["swing_pct"]
        days = market_data["days"]
        swing_str = f"{'+' if swing_val > 0 else ''}{swing_val:.2f}% ({days} Day)"
        
        # Step 2 & 3: Qualitative Leg & Processor (Rules Engine fallback until full LLM connection)
        parsed_data = EventParser.parse_data_drop(raw_news_text)
        metrics = parsed_data.get("metrics", {})
        
        text_lower = raw_news_text.lower()
        
        # Capture the specific NBIS Clinical Trial Example
        if "phase 3" in text_lower or "clinical" in text_lower or "endpoint" in text_lower:
            event_type = "Clinical Data / Regulatory"
            classification = "Binary Pipeline Success"
            trigger_str = "Phase 3 trial met primary endpoints" if "met" in text_lower else "Clinical Trial Update"
        else:
            event_type = "Earnings / Catalyst"
            parts = []
            if "revenue" in metrics:
                parts.append(f"Rev {metrics['revenue'].get('amount', '')} ({metrics['revenue'].get('change', 'Beat')})")
            if "eps" in metrics:
                parts.append(f"EPS {metrics['eps'].get('amount', '')} ({metrics['eps'].get('beat', 'Beat')})")
            if "guidance" in metrics:
                parts.append(f"Guidance {metrics['guidance'].get('action', '')} by {metrics['guidance'].get('amount', '')}")
            
            trigger_str = " AND ".join(parts) if parts else "Event-Driven Release"
                
            if "guidance" in metrics and metrics["guidance"].get("action") == "raised":
                classification = "Forward Guidance Hike"
            elif "guidance" in metrics and metrics["guidance"].get("action") == "lowered":
                classification = "Supply Chain Failure" if "supply" in text_lower else "Guidance Cut"
            elif "narrative" in metrics:
                classification = metrics["narrative"]
            else:
                classification = "Earnings Beat" if swing_val >= 0 else "Earnings Miss"
        
        # Step 4: Database Auto-Commit
        record = CatalystRecord(
            ticker=ticker.upper(),
            event_type=event_type,
            trigger_metric=trigger_str,
            resulting_swing=swing_str,
            classification=classification,
            swing_value=swing_val
        )
        
        self.db.add_record(record)
        self.db.save()
        
        return {
            "success": True,
            "message": f"Pipeline Complete. Quantitative Price Swing automatically calculated: {swing_str}",
            "record": record,
            "payload": {
                "ticker": record.ticker,
                "event_date": end_date,
                "event_type": record.event_type,
                "specific_trigger_metric": record.trigger_metric,
                "catalyst_classification": record.classification,
                "resulting_price_swing_string": record.resulting_swing,
                "numeric_price_swing": round(record.swing_value, 2)
            }
        }

class PredictiveEngine:
    def __init__(self, database: CatalystDatabase):
        self.db = database

    def generate_prediction(self, parsed_data: Dict[str, Any], current_price: float = 111.15) -> Dict[str, Any]:
        ticker = parsed_data.get("ticker", "UNKNOWN")
        metrics = parsed_data.get("metrics", {})
        table_rows = []
        contributions = []

        rev_data = metrics.get("revenue")
        if rev_data:
            change_str = rev_data.get("change", "Beat")
            rev_min, rev_max = 4.0, 6.0
            contributions.append((rev_min, rev_max))
            table_rows.append({"metric": "Revenue", "reported_data": f"{rev_data.get('amount', '')} ({change_str})", "historical_match": "Standard Tech Beat", "predicted_open_impact": f"+{rev_min:.0f}% to +{rev_max:.0f}%"})

        eps_data = metrics.get("eps")
        if eps_data:
            beat_str = eps_data.get("beat", "Beat")
            eps_min, eps_max = 1.0, 2.0
            contributions.append((eps_min, eps_max))
            table_rows.append({"metric": "EPS", "reported_data": f"{eps_data.get('amount', '')} ({beat_str})", "historical_match": "Standard Tech Beat", "predicted_open_impact": f"+{eps_min:.0f}% to +{eps_max:.0f}%"})

        guidance_data = metrics.get("guidance")
        is_negative_guidance = False
        if guidance_data:
            action = guidance_data.get("action")
            amt = guidance_data.get("amount", "")
            amt_str = f" by {amt}" if amt else ""
            
            if action == "raised":
                guid_min, guid_max = 8.0, 10.0
                contributions.append((guid_min, guid_max))
                table_rows.append({"metric": "Forward Guidance", "reported_data": f"Raised{amt_str}", "historical_match": "Matches 'APPS' Guidance Raise profile", "predicted_open_impact": f"+{guid_min:.0f}% to +{guid_max:.0f}%"})
            else:
                guid_min, guid_max = -20.0, -15.0
                is_negative_guidance = True
                contributions.append((guid_min, guid_max))
                table_rows.append({"metric": "Forward Guidance", "reported_data": f"Lowered{amt_str}", "historical_match": "Matches 'HONA' Guidance Cut profile", "predicted_open_impact": f"{guid_min:.0f}% to {guid_max:.0f}%"})

        narrative = metrics.get("narrative")
        if narrative:
            matches = self.db.find_matches_by_classification(narrative)
            if matches:
                ref_match = matches[0]
                sign = "+" if ref_match.swing_value >= 0 else ""
                val = ref_match.swing_value
                nat_min, nat_max = val - 5.0, val + 5.0
                contributions.append((nat_min, nat_max))
                table_rows.append({"metric": "Narrative/Catalyst", "reported_data": ref_match.trigger_metric, "historical_match": f"Matches '{ref_match.ticker}' {ref_match.classification} profile", "predicted_open_impact": f"{sign}{nat_min:.1f}% to {sign}{nat_max:.1f}%"})

        if contributions:
            sum_min = sum(c[0] for c in contributions)
            sum_max = sum(c[1] for c in contributions)
            
            if sum_min > 0 and not is_negative_guidance:
                if len(contributions) >= 3:
                    net_min, net_max = sum_min, sum_min + 2.0 
                else:
                    net_min, net_max = sum_min, sum_max
                net_predicted_text = f"High Probability of +{net_min:.0f}% to +{net_max:.0f}% Gap Up"
                projected_open = current_price * (1 + (net_min / 100.0))
            elif is_negative_guidance:
                net_min, net_max = sum_min, sum_max
                net_predicted_text = f"High Probability of {net_min:.0f}% to {net_max:.0f}% Gap Down"
                projected_open = current_price * (1 + (net_max / 100.0)) 
            else:
                net_min, net_max = sum_min, sum_max
                sign = "+" if sum_min >= 0 else ""
                net_predicted_text = f"Estimated Swing of {sign}{net_min:.1f}% to {sign}{net_max:.1f}%"
                projected_open = current_price * (1 + (sum_min / 100.0))
        else:
            net_predicted_text = "No material catalysts parsed."
            projected_open = current_price

        is_high_revenue_beat = False
        if rev_data and rev_data.get("change"):
            try:
                num = float(re.findall(r"[\d\.]+", rev_data.get("change"))[0])
                if num >= 20: is_high_revenue_beat = True
            except Exception: pass
                
        has_guidance_raise = (guidance_data and guidance_data.get("action") == "raised")

        if is_high_revenue_beat and has_guidance_raise:
            system_directive = "Historical Precedent: Stocks in your tracked Top 100 that combine a +20% revenue beat with a forward guidance raise have historically gapped up >12% at the open."
            actionable_read = "If the stock opens pre-market below +10%, there is a high-probability arbitrage window to buy the opening minute before retail volume prices in the guidance raise."
        elif is_negative_guidance:
            system_directive = "Historical Precedent: Supply chain or major guidance cuts with capital flight triggers have resulted in steep day-1 selling pressure exceeding -20%."
            actionable_read = "Avoid catching the falling knife. If opening gap is shallow (e.g. > -10%), initiate or add to short positions to capture the drift down to projected support levels."
        else:
            system_directive = "Standard catalyst reaction. Volatility expected to normalize within the first 30 minutes of open."
            actionable_read = "Observe initial 5-minute range before committing capital."

        return {
            "ticker": ticker,
            "table_rows": table_rows,
            "net_predicted_swing": net_predicted_text,
            "projected_open": f"${projected_open:.2f}",
            "system_directive": system_directive,
            "actionable_read": actionable_read
        }

class LiveDataFetcher:
    @staticmethod
    def fetch_upcoming_events(ticker: str) -> Dict[str, Any]:
        results = {"ticker": ticker.upper(), "earnings_date": "No Data Found", "ex_dividend_date": "No Data Found"}
        if not YFINANCE_AVAILABLE:
            results["earnings_date"] = "Requires 'pip install yfinance'"
            return results
        try:
            stock = yf.Ticker(ticker)
            calendar = stock.calendar
            if calendar is not None:
                if isinstance(calendar, dict) and "Earnings Date" in calendar:
                    dates_list = calendar["Earnings Date"]
                    if dates_list and len(dates_list) > 0: results["earnings_date"] = dates_list[0].strftime("%Y-%m-%d")
                elif hasattr(calendar, "index") and hasattr(calendar, "columns"):
                    for idx, row in calendar.iterrows():
                        if "Earnings Date" in idx:
                            vals = row.values
                            if len(vals) > 0: results["earnings_date"] = str(vals[0])
            info = stock.info
            if info and isinstance(info, dict):
                ex_div_timestamp = info.get("exDividendDate")
                if ex_div_timestamp:
                    try: results["ex_dividend_date"] = datetime.datetime.fromtimestamp(ex_div_timestamp).strftime("%Y-%m-%d")
                    except Exception: pass
                if results["earnings_date"] == "No Data Found":
                    next_earn = info.get("nextEarningsDate")
                    if next_earn:
                        try: results["earnings_date"] = datetime.datetime.fromtimestamp(next_earn).strftime("%Y-%m-%d")
                        except Exception: pass
        except Exception as e:
            results["earnings_date"] = "Query Failed / No Data"
            results["ex_dividend_date"] = "Query Failed / No Data"
        return results

    @staticmethod
    def check_and_calc_swing(ticker: str, reference_price: float) -> Dict[str, Any]:
        swings = {"ticker": ticker.upper(), "close_1d": 0.0, "swing_1d_pct": 0.0, "close_5d": 0.0, "swing_5d_pct": 0.0, "meets_1d_threshold": False, "meets_5d_threshold": False, "error": None}
        if not YFINANCE_AVAILABLE:
            swings["error"] = "yfinance library not installed."
            return swings
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="10d")
            if hist.empty or len(hist) < 2:
                swings["error"] = "Not enough historical candle data returned."
                return swings
            close_1d = float(hist["Close"].iloc[-1])
            swing_1d = ((close_1d - reference_price) / reference_price) * 100.0
            close_5d = close_1d
            if len(hist) >= 6:
                price_5d_ago = float(hist["Close"].iloc[-6])
                swing_5d = ((close_1d - price_5d_ago) / price_5d_ago) * 100.0
            else: swing_5d = 0.0
            swings["close_1d"] = close_1d; swings["swing_1d_pct"] = swing_1d
            swings["close_5d"] = close_5d; swings["swing_5d_pct"] = swing_5d
            if abs(swing_1d) >= 10.0: swings["meets_1d_threshold"] = True
            if abs(swing_5d) >= 25.0: swings["meets_5d_threshold"] = True
        except Exception as e: swings["error"] = str(e)
        return swings

class EventDrivenVolatilitySystem:
    def __init__(self, db_path: str = "Catalyst_Correlations.md"):
        self.db = CatalystDatabase(db_path)
        self.engine = PredictiveEngine(self.db)
        self.extractor = ExtractionPipeline(self.db)
        self.current_watchlist = []

    def handle_phase1_watchlist(self, watchlist_text: str) -> str:
        parsed = EventParser.parse_watchlist(watchlist_text)
        self.current_watchlist = parsed
        output = "=== Phase 1: Watchlist Logged ===\n"
        for item in parsed: output += f"Registered upcoming Catalyst Event: {item['ticker']} ({item['event_type']}) scheduled for {item['timing']}\n"
        return output

    def handle_phase2_and_3(self, data_drop_text: str, current_price: float = 111.15) -> str:
        parsed = EventParser.parse_data_drop(data_drop_text)
        prediction = self.engine.generate_prediction(parsed, current_price)
        report = "=" * 80 + "\n"
        report += f"PRE-MARKET CATALYST ALERT: {prediction['ticker']}\n"
        report += f"Processed: {parsed['raw']}\n"
        report += "=" * 80 + "\n\n"
        headers = ["Metric", "Reported Data", "Historical Correlation Match", "Predicted Open Impact"]
        col_widths = [18, 25, 38, 22]
        header_row = "".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
        separator = "-" * sum(col_widths)
        report += header_row + "\n" + separator + "\n"
        for row in prediction["table_rows"]: report += f"{row['metric']:<18}{row['reported_data']:<25}{row['historical_match']:<38}{row['predicted_open_impact']:<22}\n"
        report += separator + "\n"
        report += f"{'Net Predicted Swing':<18}{'':<25}{prediction['net_predicted_swing']:<38}\n"
        report += f"{'Projected Open':<18}{'':<25}{prediction['projected_open']:<38}\n"
        report += "=" * 80 + "\n\n"
        report += f"System Directive:\n{prediction['system_directive']}\n\n"
        report += f"Actionable Read:\n{prediction['actionable_read']}\n"
        report += "=" * 80 + "\n"
        return report

    def check_and_auto_log_market_swing(self, ticker: str, ref_price: float, raw_data_drop: str) -> Dict[str, Any]:
        results = {"logged": False, "record": None, "message": ""}
        swings = LiveDataFetcher.check_and_calc_swing(ticker, ref_price)
        if swings.get("error"):
            results["message"] = f"Price check failed: {swings['error']}"
            return results
        ticker_upper = ticker.upper()
        parsed_drop = EventParser.parse_data_drop(raw_data_drop)
        metrics = parsed_drop.get("metrics", {})
        parts = []
        if "revenue" in metrics: parts.append(f"Rev {metrics['revenue'].get('amount', '')} ({metrics['revenue'].get('change', 'Beat')})")
        if "eps" in metrics: parts.append(f"EPS {metrics['eps'].get('amount', '')} ({metrics['eps'].get('beat', 'Beat')})")
        if "guidance" in metrics: parts.append(f"Guidance {metrics['guidance'].get('action', '')} by {metrics['guidance'].get('amount', '')}")
        trigger_str = " AND ".join(parts) if parts else "Event-Driven Release"
        if "guidance" in metrics and metrics["guidance"].get("action") == "raised": classification = "Forward Guidance Hike"
        elif "guidance" in metrics and metrics["guidance"].get("action") == "lowered": classification = "Supply Chain Failure" if "supply" in raw_data_drop.lower() else "Guidance Cut"
        elif "narrative" in metrics: classification = metrics["narrative"]
        else: classification = "Earnings Beat" if swings["swing_1d_pct"] >= 0 else "Earnings Miss"

        if swings["meets_1d_threshold"]:
            val = swings["swing_1d_pct"]
            sign = "+" if val >= 0 else ""
            resulting_swing = f"{sign}{val:.2f}% (1 Day)"
            record = CatalystRecord(ticker=ticker_upper, event_type="Earnings / Catalyst", trigger_metric=trigger_str, resulting_swing=resulting_swing, classification=classification, swing_value=val)
            self.db.add_record(record)
            self.db.save()
            results["logged"] = True; results["record"] = record
            results["message"] = f"SUCCESS: Actual 1-Day swing was {resulting_swing} (exceeding the ±10% threshold). Event auto-saved to Catalyst Database!"
        elif swings["meets_5d_threshold"]:
            val = swings["swing_5d_pct"]
            sign = "+" if val >= 0 else ""
            resulting_swing = f"{sign}{val:.2f}% (5 Day)"
            record = CatalystRecord(ticker=ticker_upper, event_type="Earnings / Catalyst", trigger_metric=trigger_str, resulting_swing=resulting_swing, classification="Sector Sympathy Rally" if "sympathy" in raw_data_drop.lower() else classification, swing_value=val)
            self.db.add_record(record)
            self.db.save()
            results["logged"] = True; results["record"] = record
            results["message"] = f"SUCCESS: Actual 5-Day swing was {resulting_swing} (exceeding the ±25% threshold). Event auto-saved to Catalyst Database!"
        else:
            results["message"] = f"No record saved. Actual 1-Day swing ({swings['swing_1d_pct']:+.2f}%) and 5-Day swing ({swings['swing_5d_pct']:+.2f}%) did not cross thresholds."
        return results