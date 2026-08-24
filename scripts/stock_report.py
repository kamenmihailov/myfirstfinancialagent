#!/usr/bin/env python3
"""
Top 100 YTD stock performers across DAX 40, S&P 500, and NASDAQ 100.
Sends an HTML email via Gmail SMTP.

Required environment variables:
  GMAIL_USER         - your Gmail address
  GMAIL_APP_PASSWORD - Gmail App Password (16-char, from Google Account > Security)
  RECIPIENT_EMAIL    - address to send the report to (can be same as GMAIL_USER)
"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date

import pandas as pd
import yfinance as yf


# --- Ticker sources ---

def fetch_sp500():
    df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    return [
        {
            "ticker": str(row["Symbol"]).strip().replace(".", "-"),
            "name": str(row["Security"]).strip(),
            "index": "S&P 500",
        }
        for _, row in df.iterrows()
    ]


def fetch_nasdaq100():
    tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
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


# DAX 40 — hardcoded, stable list
DAX_40 = [
    ("ADS.DE", "Adidas"),       ("AIR.DE", "Airbus"),          ("ALV.DE", "Allianz"),
    ("BAS.DE", "BASF"),         ("BAYN.DE", "Bayer"),          ("BEI.DE", "Beiersdorf"),
    ("BMW.DE", "BMW"),          ("BNR.DE", "Brenntag"),        ("CBK.DE", "Commerzbank"),
    ("CON.DE", "Continental"),  ("1COV.DE", "Covestro"),       ("DB1.DE", "Deutsche Boerse"),
    ("DBK.DE", "Deutsche Bank"),("DHL.DE", "DHL Group"),       ("DTE.DE", "Deutsche Telekom"),
    ("EOAN.DE", "E.ON"),        ("ENR.DE", "Siemens Energy"),  ("FME.DE", "Fresenius Medical Care"),
    ("FRE.DE", "Fresenius"),    ("HEI.DE", "Heidelberg Materials"), ("HEN3.DE", "Henkel"),
    ("HNR1.DE", "Hannover Re"), ("IFX.DE", "Infineon"),        ("MBG.DE", "Mercedes-Benz"),
    ("MRK.DE", "Merck KGaA"),   ("MTX.DE", "MTU Aero Engines"),("MUV2.DE", "Munich Re"),
    ("P911.DE", "Porsche AG"),  ("PAH3.DE", "Porsche SE"),     ("QIA.DE", "Qiagen"),
    ("RHM.DE", "Rheinmetall"),  ("RWE.DE", "RWE"),             ("SAP.DE", "SAP"),
    ("SHL.DE", "Siemens Healthineers"), ("SIE.DE", "Siemens"), ("SRT3.DE", "Sartorius"),
    ("SY1.DE", "Symrise"),      ("VNA.DE", "Vonovia"),         ("VOW3.DE", "Volkswagen"),
    ("ZAL.DE", "Zalando"),
]


def fetch_dax():
    return [{"ticker": t, "name": n, "index": "DAX"} for t, n in DAX_40]


# --- Data fetching ---

def get_ytd_top100(all_tickers):
    year_start = f"{date.today().year}-01-01"

    seen = set()
    unique = []
    for t in all_tickers:
        if t["ticker"] not in seen:
            seen.add(t["ticker"])
            unique.append(t)

    meta = {t["ticker"]: t for t in unique}
    symbols = [t["ticker"] for t in unique]
    results = []

    print(f"Downloading YTD data for {len(symbols)} tickers...", file=sys.stderr)

    for i in range(0, len(symbols), 100):
        batch = symbols[i : i + 100]
        try:
            raw = yf.download(batch, start=year_start, progress=False, auto_adjust=True)

            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Close"]
            else:
                closes = raw[["Close"]].rename(columns={"Close": batch[0]}) if len(batch) == 1 else raw

            for sym in batch:
                if sym not in closes.columns:
                    continue
                series = closes[sym].dropna()
                if len(series) < 2:
                    continue
                start_px = float(series.iloc[0])
                end_px = float(series.iloc[-1])
                ytd = round(((end_px - start_px) / start_px) * 100, 2)
                results.append({
                    **meta[sym],
                    "start_price": round(start_px, 2),
                    "current_price": round(end_px, 2),
                    "ytd_pct": ytd,
                })
        except Exception as e:
            print(f"  Batch {i}–{i+100} error: {e}", file=sys.stderr)

    return sorted(results, key=lambda x: x["ytd_pct"], reverse=True)[:100]


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
        idx_colors = {"DAX": "#1565c0", "S&P 500": "#2e7d32", "NASDAQ 100": "#6a1b9a"}
        idx_color = idx_colors.get(s["index"], "#555")
        rows += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:7px 12px;text-align:center;color:#888;font-size:13px">{rank}</td>'
            f'<td style="padding:7px 12px;font-weight:700">{s["ticker"]}</td>'
            f'<td style="padding:7px 12px;font-size:13px">{s["name"]}</td>'
            f'<td style="padding:7px 12px;text-align:center">'
            f'<span style="background:#188038;color:white;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:600">'
            f'+{s["ytd_pct"]:.1f}%</span></td>'
            f'<td style="padding:7px 12px;text-align:right;font-size:13px">{price_str}</td>'
            f'<td style="padding:7px 12px;text-align:center;font-size:11px;font-weight:600;color:{idx_color}">{s["index"]}</td>'
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #202124; max-width: 900px; margin: 0 auto; padding: 24px; }}
  h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  th {{ background: #1a73e8; color: white; padding: 10px 12px; text-align: left; font-size: 13px; font-weight: 600; }}
  tr:hover td {{ background: #e8f0fe !important; }}
  td {{ border-bottom: 1px solid #f0f0f0; }}
</style>
</head>
<body>
  <h1>Top 100 Stock Performers &mdash; {today}</h1>
  <p style="color:#666;margin:4px 0 0">YTD performance &middot; {year} &middot; {summary}</p>
  <table>
    <thead>
      <tr>
        <th style="width:44px;text-align:center">#</th>
        <th style="width:110px">Ticker</th>
        <th>Company</th>
        <th style="text-align:center;width:110px">YTD Gain</th>
        <th style="text-align:right;width:110px">Price</th>
        <th style="text-align:center;width:110px">Index</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="color:#bbb;font-size:11px;margin-top:20px">
    Data via Yahoo Finance (yfinance) &middot; Prices as of most recent market close &middot;
    Generated {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
  </p>
</body>
</html>"""


# --- Email sending ---

def send_email(html: str, subject: str):
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
    all_tickers = fetch_sp500() + fetch_nasdaq100() + fetch_dax()
    print(f"Total tickers (pre-dedup): {len(all_tickers)}", file=sys.stderr)

    top100 = get_ytd_top100(all_tickers)
    print("Top 100 computed. Building HTML...", file=sys.stderr)

    today_str = datetime.now().strftime("%B %d, %Y")
    subject = f"Top 100 Stock Performers - {today_str}"
    html = build_html(top100)

    if os.environ.get("GMAIL_APP_PASSWORD"):
        send_email(html, subject)
    else:
        # No credentials — print HTML for local inspection
        print(html)
        print("\nTip: set GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL to send via email.", file=sys.stderr)
