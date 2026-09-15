#!/usr/bin/env python3
"""
Top performing UCITS ETFs from Vanguard, Xtrackers (DWS), Amundi, and SPDR
(State Street) - broad-market and thematic funds, ranked by YTD performance.

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

import pandas as pd
import yfinance as yf

# --- ETF universe ---
# Curated list of major UCITS ETFs from the four requested providers, spanning
# broad-market (MSCI World, S&P 500, All-World, regional) and thematic/sector
# funds. Ticker symbols are drawn from general knowledge, not scraped live
# from justETF/extraETF - a few may fail to resolve on Yahoo Finance and will
# be silently dropped (logged to stderr) rather than break the run.

ETF_UNIVERSE = [
    # --- Vanguard ---
    ("VWCE.DE", "Vanguard FTSE All-World UCITS ETF (Acc)", "Vanguard"),
    ("VWRL.L",  "Vanguard FTSE All-World UCITS ETF (Dist)", "Vanguard"),
    ("VUSA.L",  "Vanguard S&P 500 UCITS ETF (Dist)", "Vanguard"),
    ("VUAA.DE", "Vanguard S&P 500 UCITS ETF (Acc)", "Vanguard"),
    ("VEUR.L",  "Vanguard FTSE Developed Europe UCITS ETF", "Vanguard"),
    ("VERX.L",  "Vanguard FTSE Developed Europe ex UK UCITS ETF", "Vanguard"),
    ("VFEM.L",  "Vanguard FTSE Emerging Markets UCITS ETF", "Vanguard"),
    ("VJPN.L",  "Vanguard FTSE Japan UCITS ETF", "Vanguard"),
    ("VAPX.L",  "Vanguard FTSE Developed Asia Pacific ex Japan UCITS ETF", "Vanguard"),
    ("VNRT.L",  "Vanguard FTSE North America UCITS ETF", "Vanguard"),
    ("VHYL.L",  "Vanguard FTSE All-World High Dividend Yield UCITS ETF", "Vanguard"),
    ("VGWE.DE", "Vanguard FTSE Developed World UCITS ETF", "Vanguard"),
    ("VEVE.L",  "Vanguard FTSE Developed World UCITS ETF (Acc)", "Vanguard"),
    ("VWRP.L",  "Vanguard FTSE All-World UCITS ETF (Acc, LSE)", "Vanguard"),
    ("VUKE.L",  "Vanguard FTSE 100 UCITS ETF", "Vanguard"),
    ("VMID.L",  "Vanguard FTSE 250 UCITS ETF", "Vanguard"),
    ("VFEG.L",  "Vanguard FTSE Emerging Markets UCITS ETF (Acc)", "Vanguard"),

    # --- Xtrackers (DWS) ---
    ("XDWD.DE", "Xtrackers MSCI World UCITS ETF", "Xtrackers"),
    ("XMME.DE", "Xtrackers MSCI Emerging Markets UCITS ETF", "Xtrackers"),
    ("XMEU.DE", "Xtrackers MSCI Europe UCITS ETF", "Xtrackers"),
    ("XMUS.DE", "Xtrackers MSCI USA UCITS ETF", "Xtrackers"),
    ("XDJP.DE", "Xtrackers MSCI Japan UCITS ETF", "Xtrackers"),
    ("XDWT.DE", "Xtrackers MSCI World Information Technology UCITS ETF", "Xtrackers"),
    ("XDWH.DE", "Xtrackers MSCI World Health Care UCITS ETF", "Xtrackers"),
    ("XDWF.DE", "Xtrackers MSCI World Financials UCITS ETF", "Xtrackers"),
    ("XDWC.DE", "Xtrackers MSCI World Consumer Discretionary UCITS ETF", "Xtrackers"),
    ("XAIX.DE", "Xtrackers Artificial Intelligence and Big Data UCITS ETF", "Xtrackers"),
    ("XDEW.DE", "Xtrackers S&P 500 Equal Weight UCITS ETF", "Xtrackers"),
    ("DBXD.DE", "Xtrackers DAX UCITS ETF", "Xtrackers"),
    ("XSX6.DE", "Xtrackers Stoxx Europe 600 UCITS ETF", "Xtrackers"),
    ("XDWM.DE", "Xtrackers MSCI World Momentum UCITS ETF", "Xtrackers"),

    # --- Amundi (incl. former Lyxor funds) ---
    ("CW8.PA",   "Amundi MSCI World UCITS ETF (Acc)", "Amundi"),
    ("LYP6.DE",  "Amundi MSCI World UCITS ETF (Xetra)", "Amundi"),
    ("500.PA",   "Amundi S&P 500 UCITS ETF (Acc)", "Amundi"),
    ("LYPS.DE",  "Amundi S&P 500 UCITS ETF (Xetra)", "Amundi"),
    ("ANX.PA",   "Amundi Nasdaq-100 UCITS ETF", "Amundi"),
    ("CG9.PA",   "Amundi MSCI Emerging Markets UCITS ETF", "Amundi"),
    ("CJ1.PA",   "Amundi Japan Topix UCITS ETF", "Amundi"),
    ("WAT.PA",   "Amundi MSCI Water ESG Screened UCITS ETF", "Amundi"),
    ("RS2K.PA",  "Amundi Russell 2000 UCITS ETF", "Amundi"),
    ("PUST.PA",  "Amundi Prime USA UCITS ETF", "Amundi"),

    # --- SPDR (State Street) ---
    ("SPY5.L",  "SPDR S&P 500 UCITS ETF", "SPDR"),
    ("SPPW.DE", "SPDR MSCI World UCITS ETF (Xetra)", "SPDR"),
    ("SWRD.L",  "SPDR MSCI World UCITS ETF", "SPDR"),
    ("WTEC.L",  "SPDR MSCI World Technology UCITS ETF", "SPDR"),
    ("WHEA.L",  "SPDR MSCI World Health Care UCITS ETF", "SPDR"),
    ("WNRG.L",  "SPDR MSCI World Energy UCITS ETF", "SPDR"),
    ("WFIN.L",  "SPDR MSCI World Financials UCITS ETF", "SPDR"),
    ("WCOD.L",  "SPDR MSCI World Consumer Discretionary UCITS ETF", "SPDR"),
    ("EMDV.L",  "SPDR MSCI Emerging Markets UCITS ETF", "SPDR"),
    ("USDV.L",  "SPDR S&P US Dividend Aristocrats UCITS ETF", "SPDR"),
    ("GLDV.L",  "SPDR S&P Global Dividend Aristocrats UCITS ETF", "SPDR"),
    ("WSML.L",  "SPDR MSCI World Small Cap UCITS ETF", "SPDR"),
]


def fetch_etf_universe():
    return [{"ticker": t, "name": n, "provider": p} for t, n, p in ETF_UNIVERSE]


# --- Price metrics (mirrors scripts/stock_report.py) ---

def _pct_return(series, ref_ts, require_history=False):
    """% return from first close at or after ref_ts to the latest close.

    If require_history, returns None when the series doesn't actually reach
    back to ref_ts - otherwise a fund with only 2 years of data would report
    its since-inception return as if it were a full 5-year return.
    """
    if require_history and series.index[0] > ref_ts + pd.Timedelta(days=10):
        return None
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

    # Filter 1: require sufficient trading history (~7+ months)
    if len(series) < 150:
        return None

    current_price = float(series.iloc[-1])
    tz = series.index.tz
    year_start = pd.Timestamp(f"{date.today().year}-01-01", tz=tz)
    ytd_series = series[series.index >= year_start]

    # Filter 2/3: sanity floor on start/current price, catches NaN-riddled or
    # thinly-traded series that would otherwise produce nonsense percentages.
    if current_price < 5.0:
        return None
    if ytd_series.empty or float(ytd_series.iloc[0]) < 5.0:
        return None

    latest_ts = series.index[-1]
    # 52W high must come from the trailing year only, not the full multi-year window
    last_365 = series[series.index >= latest_ts - pd.Timedelta(days=365)]
    high_52w = float(last_365.max())

    ytd_pct = _pct_return(series, year_start)
    # Filter 4: >500% YTD is almost certainly corrupted data (un-adjusted split/action)
    if ytd_pct is None or ytd_pct > 500:
        return None

    return {
        "current_price": round(current_price, 2),
        "ytd_pct":    ytd_pct,
        "m6_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=182)),
        "m3_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=91)),
        "m1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=30)),
        "w1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=7)),
        "y2_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=365 * 2), require_history=True),
        "y3_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=365 * 3), require_history=True),
        "y5_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=365 * 5), require_history=True),
        "vs_52w_pct": round(((current_price - high_52w) / high_52w) * 100, 1),
    }


def get_all_price_metrics(all_etfs):
    # Download 5+ years of history to cover all timeframes up to the 5Y column
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")

    meta = {e["ticker"]: e for e in all_etfs}
    symbols = list(meta.keys())
    results = []

    print(f"Downloading 5-year price data for {len(symbols)} ETFs...", file=sys.stderr)

    for i in range(0, len(symbols), 100):
        batch = symbols[i : i + 100]
        try:
            # auto_adjust=False: use Yahoo's own pre-computed Adj Close, which handles
            # splits/distributions more reliably than yfinance's in-library recalculation.
            raw = yf.download(batch, start=start_date, progress=False, auto_adjust=False)
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Adj Close"]
            elif "Adj Close" in raw.columns:
                closes = raw[["Adj Close"]].rename(columns={"Adj Close": batch[0]})
            else:
                closes = raw
            if isinstance(closes, pd.Series):
                closes = closes.to_frame(name=batch[0])

            found = set(closes.columns) if hasattr(closes, "columns") else set()
            for sym in batch:
                if sym not in found:
                    print(f"  No data for {sym}, skipping.", file=sys.stderr)
                    continue
                metrics = compute_price_metrics(closes, sym)
                if metrics:
                    results.append({**meta[sym], **metrics})
        except Exception as e:
            print(f"  Batch {i} error: {e}", file=sys.stderr)

    return sorted(results, key=lambda x: x["ytd_pct"] or -999, reverse=True)


# --- Fund size (AUM), parallelised ---

def fetch_extra_info(etf):
    sym = etf["ticker"]
    out = {"aum": None}
    try:
        t = yf.Ticker(sym)
        try:
            out["aum"] = t.info.get("totalAssets")
        except Exception:
            pass
    except Exception:
        pass
    return sym, out


def enrich_with_extra_info(etfs):
    print(f"Fetching fund size for {len(etfs)} ETFs...", file=sys.stderr)
    extra = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_extra_info, e): e["ticker"] for e in etfs}
        for future in as_completed(futures):
            sym, data = future.result()
            extra[sym] = data

    for e in etfs:
        e.update(extra.get(e["ticker"], {}))

    return etfs


# --- Formatting helpers ---

def fmt_aum(v):
    if not v:
        return "—"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    return f"${v / 1e6:.0f}M"


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


def currency_for(sym):
    if sym.endswith(".L"):
        return "GBX"  # London Stock Exchange quotes ETFs in pence, not pounds
    if sym.endswith(".SW"):
        return "CHF"
    return "EUR"


def fmt_price(sym, v):
    cur = currency_for(sym)
    if cur == "GBX":
        return f"GBX {v:,.1f}"
    if cur == "EUR":
        return f"€{v:,.2f}"
    return f"{cur} {v:,.2f}"


# --- HTML report ---

PROVIDER_COLORS = {
    "Vanguard": "#8b0000", "Xtrackers": "#00558c", "Amundi": "#f2a900", "SPDR": "#2e7d32",
}


def build_html(etfs):
    today = datetime.now().strftime("%B %d, %Y")
    year = datetime.now().year

    provider_counts = {}
    for e in etfs:
        provider_counts[e["provider"]] = provider_counts.get(e["provider"], 0) + 1
    summary = " · ".join(f"{v} from {k}" for k, v in sorted(provider_counts.items()))

    rows = ""
    for rank, e in enumerate(etfs, 1):
        bg = "#e8f5e9" if rank <= 5 else ("#f1f8e9" if rank <= 15 else "white")
        provider_color = PROVIDER_COLORS.get(e["provider"], "#555")

        rows += (
            f'<tr style="background:{bg}">'
            f'<td class="c dim">{rank}</td>'
            f'<td class="b">{e["ticker"]}</td>'
            f'<td class="name">{e["name"]}</td>'
            f'<td class="c"><span style="background:{provider_color};color:white;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600;white-space:nowrap">{e["provider"]}</span></td>'
            f'<td class="c">{fmt_aum(e.get("aum"))}</td>'
            f'<td class="c">{fmt_price(e["ticker"], e["current_price"])}</td>'
            f'<td class="c">{fmt_pct(e.get("y5_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("y3_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("y2_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("ytd_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("m6_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("m3_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("m1_pct"))}</td>'
            f'<td class="c">{fmt_pct(e.get("w1_pct"))}</td>'
            f'<td class="c">{fmt_52w(e.get("vs_52w_pct"))}</td>'
            f'</tr>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body   {{ font-family: Arial, sans-serif; color: #202124; max-width: 1200px; margin: 0 auto; padding: 24px; }}
  h1     {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; font-size: 20px; margin-bottom: 4px; }}
  .wrap  {{ overflow-x: auto; margin-top: 16px; }}
  table  {{ border-collapse: collapse; font-size: 12px; min-width: 1150px; width: 100%; }}
  th     {{ background: #1a73e8; color: white; padding: 8px 10px; text-align: center; font-size: 11px;
             font-weight: 600; white-space: nowrap; position: sticky; top: 0; }}
  th.l   {{ text-align: left; }}
  td     {{ border-bottom: 1px solid #f0f0f0; padding: 6px 10px; white-space: nowrap; }}
  td.c   {{ text-align: center; }}
  td.b   {{ font-weight: 700; font-size: 13px; }}
  td.dim {{ color: #999; }}
  td.name{{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; }}
  tr:hover td {{ background: #e8f0fe !important; }}
</style>
</head>
<body>
  <h1>ETF Performance Report &mdash; {today}</h1>
  <p style="color:#666;font-size:13px;margin:4px 0 0">
    Ranked by YTD performance &middot; {year} &middot; {summary}
  </p>
  <div class="wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th class="l">Ticker</th>
        <th class="l">Fund</th>
        <th>Provider</th>
        <th>AUM</th>
        <th>Price</th>
        <th>5Y</th>
        <th>3Y</th>
        <th>2Y</th>
        <th>YTD</th>
        <th>6M</th>
        <th>3M</th>
        <th>1M</th>
        <th>1W</th>
        <th>vs 52W High</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  <p style="color:#bbb;font-size:11px;margin-top:16px">
    Data via Yahoo Finance (yfinance) &middot; Prices as of most recent market close &middot;
    London-listed (.L) funds quoted in GBX (pence) &middot; AUM in USD &middot;
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
    print("Building ETF universe...", file=sys.stderr)
    all_etfs = fetch_etf_universe()
    print(f"Total ETFs to check: {len(all_etfs)}", file=sys.stderr)

    ranked = get_all_price_metrics(all_etfs)
    ranked = enrich_with_extra_info(ranked)

    today_str = datetime.now().strftime("%B %d, %Y")
    subject = f"ETF Performance Report - {today_str}"
    html = build_html(ranked)

    if os.environ.get("GMAIL_APP_PASSWORD"):
        send_email(html, subject)
    else:
        print(html)
        print("\nTip: set GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL to send via email.", file=sys.stderr)
