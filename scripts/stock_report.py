#!/usr/bin/env python3
"""
Top 100 YTD stock performers across DAX 40, S&P 500, and NASDAQ 100.
Extended report: multi-timeframe performance, market cap, 52W high, earnings.

Required environment variables:
  GMAIL_USER         - your Gmail address
  GMAIL_APP_PASSWORD - Gmail App Password (16-char, from Google Account > Security)
  RECIPIENT_EMAIL    - address to send the report to (defaults to GMAIL_USER)
"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import requests
import pandas as pd
import yfinance as yf

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; stock-report-bot/1.0; +https://github.com/kamenmihailov/myfirstfinancialagent)"
}


# --- Ticker sources ---

def _read_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def fetch_sp500():
    df = _read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    return [
        {"ticker": str(r["Symbol"]).strip().replace(".", "-"), "name": str(r["Security"]).strip(), "index": "S&P 500"}
        for _, r in df.iterrows()
    ]


def fetch_nasdaq100():
    tables = _read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
    for table in tables:
        cols = list(table.columns)
        lower = [str(c).lower() for c in cols]
        if any("ticker" in c or "symbol" in c for c in lower):
            ticker_col = next(c for c in cols if "ticker" in str(c).lower() or "symbol" in str(c).lower())
            name_col = next((c for c in cols if "company" in str(c).lower()), cols[0])
            result = []
            for _, row in table.iterrows():
                sym = str(row[ticker_col]).strip()
                if sym and sym.lower() != "nan":
                    result.append({"ticker": sym, "name": str(row[name_col]).strip(), "index": "NASDAQ 100"})
            if result:
                return result
    return []


DAX_40 = [
    ("ADS.DE", "Adidas"),        ("AIR.DE", "Airbus"),           ("ALV.DE", "Allianz"),
    ("BAS.DE", "BASF"),          ("BAYN.DE", "Bayer"),           ("BEI.DE", "Beiersdorf"),
    ("BMW.DE", "BMW"),           ("BNR.DE", "Brenntag"),         ("CBK.DE", "Commerzbank"),
    ("CON.DE", "Continental"),   ("1COV.DE", "Covestro"),        ("DB1.DE", "Deutsche Boerse"),
    ("DBK.DE", "Deutsche Bank"), ("DHL.DE", "DHL Group"),        ("DTE.DE", "Deutsche Telekom"),
    ("EOAN.DE", "E.ON"),         ("ENR.DE", "Siemens Energy"),   ("FME.DE", "Fresenius Medical Care"),
    ("FRE.DE", "Fresenius"),     ("HEI.DE", "Heidelberg Materials"), ("HEN3.DE", "Henkel"),
    ("HNR1.DE", "Hannover Re"),  ("IFX.DE", "Infineon"),         ("MBG.DE", "Mercedes-Benz"),
    ("MRK.DE", "Merck KGaA"),    ("MTX.DE", "MTU Aero Engines"), ("MUV2.DE", "Munich Re"),
    ("P911.DE", "Porsche AG"),   ("PAH3.DE", "Porsche SE"),      ("QIA.DE", "Qiagen"),
    ("RHM.DE", "Rheinmetall"),   ("RWE.DE", "RWE"),              ("SAP.DE", "SAP"),
    ("SHL.DE", "Siemens Healthineers"), ("SIE.DE", "Siemens"),   ("SRT3.DE", "Sartorius"),
    ("SY1.DE", "Symrise"),       ("VNA.DE", "Vonovia"),          ("VOW3.DE", "Volkswagen"),
    ("ZAL.DE", "Zalando"),
]


def fetch_dax():
    return [{"ticker": t, "name": n, "index": "DAX"} for t, n in DAX_40]


def fetch_nasdaq_top500():
    """Top 500 NASDAQ-listed stocks by market cap, via the NASDAQ screener API."""
    url = "https://api.nasdaq.com/api/screener/stocks"
    params = {
        "tableonly": "true",
        "limit": 500,
        "offset": 0,
        "exchange": "nasdaq",
        "sortcolumn": "marketcap",
        "sortorder": "desc",
        "download": "true",
    }
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nasdaq.com/",
    }
    resp = requests.get(url, params=params, headers=hdrs, timeout=30)
    resp.raise_for_status()
    rows = resp.json().get("data", {}).get("rows", [])
    result = []
    for row in rows:
        sym = str(row.get("symbol", "")).strip()
        name = str(row.get("name", "")).strip()
        # Skip warrants, rights, and other non-standard tickers
        if sym and sym.replace("-", "").isalpha():
            result.append({"ticker": sym, "name": name, "index": "NASDAQ"})
    print(f"  Fetched {len(result)} NASDAQ stocks from screener.", file=sys.stderr)
    return result


# --- Price metrics ---

def _pct_return(series, ref_ts):
    """% return from first close at or after ref_ts to the latest close."""
    subset = series[series.index >= ref_ts]
    if subset.empty:
        return None
    start = float(subset.iloc[0])
    end = float(series.iloc[-1])
    if start == 0:
        return None
    return round(((end - start) / start) * 100, 1)


def compute_price_metrics(closes, sym):
    if sym not in closes.columns:
        return None
    series = closes[sym].dropna()
    if len(series) < 5:
        return None

    latest_ts = series.index[-1]
    tz = series.index.tz
    current = float(series.iloc[-1])
    high_52w = float(series.max())

    year_start = pd.Timestamp(f"{date.today().year}-01-01", tz=tz)

    return {
        "current_price": round(current, 2),
        "ytd_pct":    _pct_return(series, year_start),
        "m6_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=182)),
        "m3_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=91)),
        "m1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=30)),
        "w1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=7)),
        "vs_52w_pct": round(((current - high_52w) / high_52w) * 100, 1),
    }


def get_all_price_metrics(all_tickers):
    # Download 1 year of history to cover all timeframes + 52W high
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=370)).strftime("%Y-%m-%d")

    seen = set()
    unique = []
    for t in all_tickers:
        if t["ticker"] not in seen:
            seen.add(t["ticker"])
            unique.append(t)

    meta = {t["ticker"]: t for t in unique}
    symbols = [t["ticker"] for t in unique]
    results = []
    price_series_cache = {}

    print(f"Downloading 1-year price data for {len(symbols)} tickers...", file=sys.stderr)

    for i in range(0, len(symbols), 100):
        batch = symbols[i : i + 100]
        try:
            raw = yf.download(batch, start=start_date, progress=False, auto_adjust=True)
            closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
            if isinstance(closes, pd.Series):
                closes = closes.to_frame(name=batch[0])

            for sym in batch:
                metrics = compute_price_metrics(closes, sym)
                if metrics and metrics["ytd_pct"] is not None:
                    results.append({**meta[sym], **metrics})
                    if sym in closes.columns:
                        price_series_cache[sym] = closes[sym].dropna()
        except Exception as e:
            print(f"  Batch {i} error: {e}", file=sys.stderr)

    top100 = sorted(results, key=lambda x: x["ytd_pct"] or -999, reverse=True)[:100]

    # Attach cached price series for earnings reaction calculation
    for s in top100:
        s["_series"] = price_series_cache.get(s["ticker"])

    return top100


# --- Market cap + earnings (individual calls, parallelised) ---

def fetch_extra_info(stock):
    sym = stock["ticker"]
    price_series = stock.get("_series")
    out = {"market_cap": None, "earnings_date": None, "earnings_reaction": None}

    try:
        t = yf.Ticker(sym)

        # Market cap
        try:
            out["market_cap"] = t.info.get("marketCap")
        except Exception:
            pass

        # Last earnings date + price reaction
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                now_ts = pd.Timestamp.now(tz="UTC")
                past = ed[ed.index < now_ts]
                if not past.empty:
                    last_date = past.index[0]
                    out["earnings_date"] = last_date.strftime("%b %d, %Y")

                    if price_series is not None and len(price_series) > 0:
                        ps = price_series.copy()
                        if ps.index.tz is None:
                            ps.index = ps.index.tz_localize("UTC")
                        else:
                            ps.index = ps.index.tz_convert("UTC")

                        before = ps[ps.index < last_date]
                        on_day = ps[
                            (ps.index >= last_date) &
                            (ps.index <= last_date + pd.Timedelta(days=3))
                        ]
                        if not before.empty and not on_day.empty:
                            prev = float(before.iloc[-1])
                            earn = float(on_day.iloc[0])
                            if prev > 0:
                                out["earnings_reaction"] = round(((earn - prev) / prev) * 100, 1)
        except Exception:
            pass

    except Exception:
        pass

    return sym, out


def enrich_with_extra_info(top100):
    print(f"Fetching market cap + earnings for {len(top100)} stocks...", file=sys.stderr)
    extra = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_extra_info, s): s["ticker"] for s in top100}
        for future in as_completed(futures):
            sym, data = future.result()
            extra[sym] = data

    for s in top100:
        s.update(extra.get(s["ticker"], {}))
        s.pop("_series", None)

    return top100


# --- Formatting helpers ---

def fmt_mcap(v):
    if v is None:
        return "—"
    if v >= 1e12:
        return f"{v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{v / 1e9:.1f}B"
    return f"{v / 1e6:.0f}M"


def fmt_pct(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    sign = "+" if v > 0 else ""
    color = "#188038" if v > 0 else ("#c5221f" if v < 0 else "#555")
    return f'<span style="color:{color};font-weight:600">{sign}{v:.1f}%</span>'


def fmt_52w(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    color = "#188038" if v >= -5 else ("#f57c00" if v >= -15 else "#c5221f")
    return f'<span style="color:{color};font-weight:600">{v:.1f}%</span>'


# --- HTML report ---

def build_html(top100):
    today = datetime.now().strftime("%B %d, %Y")
    year = datetime.now().year

    index_counts = {}
    for s in top100:
        index_counts[s["index"]] = index_counts.get(s["index"], 0) + 1
    summary = " · ".join(f"{v} from {k}" for k, v in sorted(index_counts.items()))

    rows = ""
    for rank, s in enumerate(top100, 1):
        bg = "#e8f5e9" if rank <= 10 else ("#f1f8e9" if rank <= 25 else "white")
        price_str = f"€{s['current_price']:,.2f}" if s["index"] == "DAX" else f"${s['current_price']:,.2f}"
        idx_colors = {"DAX": "#1565c0", "S&P 500": "#2e7d32", "NASDAQ 100": "#6a1b9a", "NASDAQ": "#e65100"}
        idx_color = idx_colors.get(s["index"], "#555")

        earn_date = s.get("earnings_date") or "—"
        earn_react = s.get("earnings_reaction")

        rows += (
            f'<tr style="background:{bg}">'
            f'<td class="c dim">{rank}</td>'
            f'<td class="b">{s["ticker"]}</td>'
            f'<td class="name">{s["name"]}</td>'
            f'<td class="c">{fmt_mcap(s.get("market_cap"))}</td>'
            f'<td class="c">{price_str}</td>'
            f'<td class="c">{fmt_pct(s.get("ytd_pct"))}</td>'
            f'<td class="c">{fmt_pct(s.get("m6_pct"))}</td>'
            f'<td class="c">{fmt_pct(s.get("m3_pct"))}</td>'
            f'<td class="c">{fmt_pct(s.get("m1_pct"))}</td>'
            f'<td class="c">{fmt_pct(s.get("w1_pct"))}</td>'
            f'<td class="c">{fmt_52w(s.get("vs_52w_pct"))}</td>'
            f'<td class="c small">{earn_date}</td>'
            f'<td class="c">{fmt_pct(earn_react)}</td>'
            f'</tr>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body   {{ font-family: Arial, sans-serif; color: #202124; max-width: 1300px; margin: 0 auto; padding: 24px; }}
  h1     {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; font-size: 20px; margin-bottom: 4px; }}
  .wrap  {{ overflow-x: auto; margin-top: 16px; }}
  table  {{ border-collapse: collapse; font-size: 12px; min-width: 1000px; width: 100%; }}
  th     {{ background: #1a73e8; color: white; padding: 8px 10px; text-align: center; font-size: 11px;
             font-weight: 600; white-space: nowrap; position: sticky; top: 0; }}
  th.l   {{ text-align: left; }}
  td     {{ border-bottom: 1px solid #f0f0f0; padding: 6px 10px; white-space: nowrap; }}
  td.c   {{ text-align: center; }}
  td.b   {{ font-weight: 700; font-size: 13px; }}
  td.dim {{ color: #999; }}
  td.name{{ max-width: 180px; overflow: hidden; text-overflow: ellipsis; }}
  td.small{{ font-size: 11px; color: #555; }}
  tr:hover td {{ background: #e8f0fe !important; }}
</style>
</head>
<body>
  <h1>Top 100 Stock Performers &mdash; {today}</h1>
  <p style="color:#666;font-size:13px;margin:4px 0 0">
    YTD performance &middot; {year} &middot; {summary}
  </p>
  <div class="wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th class="l">Ticker</th>
        <th class="l">Company</th>
        <th>Mkt Cap</th>
        <th>Price</th>
        <th>YTD</th>
        <th>6M</th>
        <th>3M</th>
        <th>1M</th>
        <th>1W</th>
        <th>vs 52W High</th>
        <th>Last Earnings</th>
        <th>Earn. Reaction</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  <p style="color:#bbb;font-size:11px;margin-top:16px">
    Data via Yahoo Finance (yfinance) &middot; Prices as of most recent market close &middot;
    Generated {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
  </p>
</body>
</html>"""


# --- Email ---

def send_email(html, subject):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", gmail_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipient, msg.as_string())

    print(f"Email sent to {recipient}", file=sys.stderr)


# --- Main ---

if __name__ == "__main__":
    print("Fetching ticker lists...", file=sys.stderr)
    all_tickers = fetch_sp500() + fetch_nasdaq100() + fetch_dax() + fetch_nasdaq_top500()
    print(f"Total tickers (pre-dedup): {len(all_tickers)}", file=sys.stderr)

    top100 = get_all_price_metrics(all_tickers)
    top100 = enrich_with_extra_info(top100)

    today_str = datetime.now().strftime("%B %d, %Y")
    subject = f"Top 100 Stock Performers - {today_str}"
    html = build_html(top100)

    if os.environ.get("GMAIL_APP_PASSWORD"):
        send_email(html, subject)
    else:
        print(html)
        print("\nTip: set GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL to send via email.", file=sys.stderr)
