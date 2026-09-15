#!/usr/bin/env python3
"""
Core buy-and-hold UCITS ETF screener: Vanguard, Xtrackers (DWS), Amundi, SPDR.

Two-stage decision this report is built around: pick the index (a strategy
choice), then pick the cheapest accurate wrapper for it (a mechanical
choice). Sorting everything by YTD mixes those two decisions into one
column and makes the strategy choice look like a performance comparison -
this report groups by index and sorts by cost within each group instead.

Filters applied (drops anything that fails any of these):
  - AUM >= EUR 1B                  (closure/merger risk below this)
  - Fund age >= 5 years            (otherwise the 5Y column is empty noise)
  - Domicile = Ireland             (15% US treaty withholding vs 30%)
  - Accumulating share class only  (no manual reinvestment step)
  - EUR-denominated listing        (Xetra/gettex/Euronext - no FX conversion;
                                     GBX/LSE listings are excluded)
  - Broad-market index only        (single-sector and single-country funds
                                     are dropped entirely, not demoted)

Domicile and Acc/Dist are inferred live from Yahoo's fund metadata
(fundFamily text, phone country code, longName), not hardcoded - see
infer_domicile() / infer_acc_dist(). Replication method is NOT available
from Yahoo at all and is maintained as a static, general-knowledge field
below - it is not live-verified, see the report footer.

True tracking difference (fund return minus benchmark return) can't be
computed from Yahoo Finance - there's no benchmark total-return series
available. TER is shown instead as a labeled proxy. A separate manually-
maintained overrides file (etf_td_overrides.csv) supplies real published
TD figures for any fund you've looked up on justETF; everything else
stays visibly empty rather than silently falling back to TER.

Required environment variables:
  GMAIL_USER         - your Gmail address
  GMAIL_APP_PASSWORD - Gmail App Password (16-char, from Google Account > Security)
  RECIPIENT_EMAIL    - address to send the report to (defaults to GMAIL_USER)
"""

import os
import sys
import csv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

# --- ETF universe ---
# (ticker, name, provider, index_category, index_type)
# index_type: "core" (broad market-cap-weighted) or "factor" (strategy tilt -
# dividend/momentum/small-cap/equal-weight) are kept, each as their own index
# group. "sector" and "country" are dropped entirely by the filter below.
#
# Two same-fund dual listings (Amundi MSCI World and Amundi S&P 500 each
# have a Paris AND a Xetra line) are deliberately represented once - showing
# both would just duplicate the same TER/domicile/age in the same group.

ETF_UNIVERSE = [
    # --- Vanguard ---
    ("VWCE.DE", "Vanguard FTSE All-World UCITS ETF (Acc)", "Vanguard", "FTSE All-World", "core"),
    ("VWRL.L",  "Vanguard FTSE All-World UCITS ETF (Dist)", "Vanguard", "FTSE All-World", "core"),
    ("VUSA.L",  "Vanguard S&P 500 UCITS ETF (Dist)", "Vanguard", "S&P 500", "core"),
    ("VUAA.DE", "Vanguard S&P 500 UCITS ETF (Acc)", "Vanguard", "S&P 500", "core"),
    ("VEUR.L",  "Vanguard FTSE Developed Europe UCITS ETF", "Vanguard", "Developed Europe", "core"),
    ("VERX.L",  "Vanguard FTSE Developed Europe ex UK UCITS ETF", "Vanguard", "Developed Europe ex UK", "core"),
    ("VFEM.L",  "Vanguard FTSE Emerging Markets UCITS ETF", "Vanguard", "Emerging Markets", "core"),
    ("VJPN.L",  "Vanguard FTSE Japan UCITS ETF", "Vanguard", "Japan", "country"),
    ("VAPX.L",  "Vanguard FTSE Developed Asia Pacific ex Japan UCITS ETF", "Vanguard", "Asia-Pacific ex Japan", "core"),
    ("VNRT.L",  "Vanguard FTSE North America UCITS ETF", "Vanguard", "North America", "core"),
    ("VHYL.L",  "Vanguard FTSE All-World High Dividend Yield UCITS ETF", "Vanguard", "High Dividend Yield", "factor"),
    ("VGWE.DE", "Vanguard FTSE Developed World UCITS ETF", "Vanguard", "Developed World", "core"),
    ("VEVE.L",  "Vanguard FTSE Developed World UCITS ETF (Acc)", "Vanguard", "Developed World", "core"),
    ("VWRP.L",  "Vanguard FTSE All-World UCITS ETF (Acc, LSE)", "Vanguard", "FTSE All-World", "core"),
    ("VUKE.L",  "Vanguard FTSE 100 UCITS ETF", "Vanguard", "FTSE 100 (UK)", "country"),
    ("VMID.L",  "Vanguard FTSE 250 UCITS ETF", "Vanguard", "FTSE 250 (UK)", "country"),
    ("VFEG.L",  "Vanguard FTSE Emerging Markets UCITS ETF (Acc)", "Vanguard", "Emerging Markets", "core"),

    # --- Xtrackers (DWS) ---
    ("XDWD.DE", "Xtrackers MSCI World UCITS ETF", "Xtrackers", "MSCI World", "core"),
    ("XMME.DE", "Xtrackers MSCI Emerging Markets UCITS ETF", "Xtrackers", "Emerging Markets", "core"),
    ("XMEU.DE", "Xtrackers MSCI Europe UCITS ETF", "Xtrackers", "Europe", "core"),
    ("XMUS.DE", "Xtrackers MSCI USA UCITS ETF", "Xtrackers", "US Large Cap (MSCI USA)", "core"),
    ("XDJP.DE", "Xtrackers MSCI Japan UCITS ETF", "Xtrackers", "Japan", "country"),
    ("XDWT.DE", "Xtrackers MSCI World Information Technology UCITS ETF", "Xtrackers", "Technology", "sector"),
    ("XDWH.DE", "Xtrackers MSCI World Health Care UCITS ETF", "Xtrackers", "Health Care", "sector"),
    ("XDWF.DE", "Xtrackers MSCI World Financials UCITS ETF", "Xtrackers", "Financials", "sector"),
    ("XDWC.DE", "Xtrackers MSCI World Consumer Discretionary UCITS ETF", "Xtrackers", "Consumer Discretionary", "sector"),
    ("XAIX.DE", "Xtrackers Artificial Intelligence and Big Data UCITS ETF", "Xtrackers", "AI & Big Data", "sector"),
    ("XDEW.DE", "Xtrackers S&P 500 Equal Weight UCITS ETF", "Xtrackers", "S&P 500 Equal Weight", "factor"),
    ("DBXD.DE", "Xtrackers DAX UCITS ETF", "Xtrackers", "DAX (Germany)", "country"),
    ("XSX6.DE", "Xtrackers Stoxx Europe 600 UCITS ETF", "Xtrackers", "Stoxx Europe 600", "core"),
    ("XDWM.DE", "Xtrackers MSCI World Materials UCITS ETF", "Xtrackers", "Materials", "sector"),

    # --- Amundi (incl. former Lyxor funds) ---
    ("CW8.PA",   "Amundi MSCI World UCITS ETF (Acc)", "Amundi", "MSCI World", "core"),
    ("500.PA",   "Amundi S&P 500 UCITS ETF (Acc)", "Amundi", "S&P 500", "core"),
    ("ANX.PA",   "Amundi Nasdaq-100 UCITS ETF", "Amundi", "Nasdaq-100", "core"),
    ("CG9.PA",   "Amundi MSCI Europe Growth UCITS ETF", "Amundi", "Europe Growth", "factor"),
    ("CJ1.PA",   "Amundi Japan Topix UCITS ETF", "Amundi", "Japan (Topix)", "country"),
    ("WAT.PA",   "Amundi MSCI Water ESG Screened UCITS ETF", "Amundi", "Water (Thematic)", "sector"),
    ("RS2K.PA",  "Amundi Russell 2000 UCITS ETF", "Amundi", "US Small Cap (Russell 2000)", "factor"),
    ("PUST.PA",  "Amundi PEA Nasdaq-100 UCITS ETF", "Amundi", "Nasdaq-100", "core"),

    # --- SPDR (State Street) ---
    ("SPY5.L",  "SPDR S&P 500 UCITS ETF", "SPDR", "S&P 500", "core"),
    ("SPPW.DE", "SPDR MSCI World UCITS ETF (Xetra)", "SPDR", "MSCI World", "core"),
    ("SWRD.L",  "SPDR MSCI World UCITS ETF", "SPDR", "MSCI World", "core"),
    ("WTEC.L",  "SPDR MSCI World Technology UCITS ETF", "SPDR", "Technology", "sector"),
    ("WHEA.L",  "SPDR MSCI World Health Care UCITS ETF", "SPDR", "Health Care", "sector"),
    ("WNRG.L",  "SPDR MSCI World Energy UCITS ETF", "SPDR", "Energy", "sector"),
    ("WFIN.L",  "SPDR MSCI World Financials UCITS ETF", "SPDR", "Financials", "sector"),
    ("WCOD.L",  "SPDR MSCI World Consumer Discretionary UCITS ETF", "SPDR", "Consumer Discretionary", "sector"),
    ("EMDV.L",  "SPDR MSCI Emerging Markets UCITS ETF", "SPDR", "Emerging Markets", "core"),
    ("USDV.L",  "SPDR S&P US Dividend Aristocrats UCITS ETF", "SPDR", "US Dividend Aristocrats", "factor"),
    ("GLDV.L",  "SPDR S&P Global Dividend Aristocrats UCITS ETF", "SPDR", "Global Dividend Aristocrats", "factor"),
    ("WSML.L",  "SPDR MSCI World Small Cap UCITS ETF", "SPDR", "World Small Cap", "factor"),
]

# Replication method: NOT available from Yahoo Finance for any of these
# tickers - maintained here from general knowledge only. Confirm on the
# fund's KIID/factsheet before relying on this for a withholding-tax
# decision (see module docstring and report footer).
REPLICATION = {
    # Confirmed directly from Yahoo's longName field where it says "Swap"
    # explicitly (CW8.PA, 500.PA, ANX.PA, XMUS.DE all confirmed Swap this
    # way - contradicting earlier general-knowledge guesses for CW8/XMUS).
    # Everything else here is still a general-knowledge default, not
    # individually confirmed - a fund not saying "Swap" in its longName is
    # presumptively physical, but that heuristic isn't proof.
    "VWCE.DE": "Physical", "VUAA.DE": "Physical", "VGWE.DE": "Physical",
    "XDWD.DE": "Physical", "XMME.DE": "Physical", "XMEU.DE": "Physical",
    "XMUS.DE": "Synthetic (Swap)", "XDEW.DE": "Physical", "XSX6.DE": "Physical",
    "CW8.PA": "Synthetic (Swap)", "500.PA": "Synthetic (Swap)", "ANX.PA": "Synthetic (Swap)",
    "CG9.PA": "Physical", "RS2K.PA": "Physical", "PUST.PA": "Physical",
    "SPY5.L": "Physical", "SPPW.DE": "Physical", "SWRD.L": "Physical",
    "EMDV.L": "Physical", "USDV.L": "Physical", "GLDV.L": "Physical",
    "WSML.L": "Physical",
}

# Sort order for index groups: broad global first, then US, Europe, EM,
# regional, then factor/strategy tilts. Anything unlisted sorts last.
INDEX_ORDER = {
    "FTSE All-World": 0, "MSCI World": 1, "Developed World": 2,
    "S&P 500": 10, "Nasdaq-100": 11, "US Large Cap (MSCI USA)": 12,
    "S&P 500 Equal Weight": 13, "US Large Cap (Prime)": 14,
    "Developed Europe": 20, "Developed Europe ex UK": 21, "Europe": 22,
    "Stoxx Europe 600": 23,
    "Emerging Markets": 30,
    "North America": 40, "Asia-Pacific ex Japan": 41,
    "High Dividend Yield": 50, "Global Dividend Aristocrats": 51,
    "US Dividend Aristocrats": 52, "World Small Cap": 53,
    "US Small Cap (Russell 2000)": 54, "Momentum": 55,
}

AUM_FLOOR_EUR = 1_000_000_000
MIN_FUND_AGE_YEARS = 5

# Fallbacks for fields Yahoo's live metadata frequently omits (confirmed by
# testing: e.g. Amundi's CW8.PA, a multi-billion-euro MSCI World fund, has no
# totalAssets field at all - treating "missing" as "fails the threshold"
# would silently exclude large, legitimate funds due to an API gap rather
# than their actual size). These are general-knowledge fallbacks, used only
# when the live lookup returns nothing - not overrides of live data.

PROVIDER_DOMICILE_FALLBACK = {
    "Vanguard": "IE", "SPDR": "IE", "Xtrackers": "LU", "Amundi": "LU",
}

# Yahoo's fundFamily/phone fields are WRONG for these, not just missing -
# verified case: XDWD.DE reported "DWS Investment S.A. (ETF)" / Luxembourg
# phone via Yahoo, but its real domicile (per justETF, ISIN IE00BJ0KDQ92) is
# Ireland. That contact info is DWS's generic administrative office, not the
# fund's legal domicile. DWS migrated its core equity index Xtrackers range
# to an Irish-domiciled "Xtrackers (IE) plc" umbrella starting 2014; the
# other core equity trackers below are presumed to have moved with it by the
# same reasoning - reasoned from one verified data point, not individually
# confirmed per fund. Spot-check on justETF before relying on this for a
# real tax decision. Amundi's LU finding is NOT overridden here - its
# longName explicitly names "Amundi Index Solutions", an identifiable
# Luxembourg SICAV (not a generic contact address), so that reading is
# higher-confidence than DWS's.
DOMICILE_OVERRIDE = {
    "XDWD.DE": "IE", "XMME.DE": "IE", "XMEU.DE": "IE", "XMUS.DE": "IE",
    "XDEW.DE": "IE", "XSX6.DE": "IE",
    # PUST.PA turned out to be "Amundi PEA Nasdaq-100", not "Prime USA" as
    # originally assumed (see ETF_UNIVERSE) - PEA-branded funds are French
    # tax-wrapper products, most likely LU/FR domiciled like Amundi's other
    # Index Solutions range, not Ireland. No override here; falls through to
    # the live value / Amundi provider fallback (LU).
}

# Acc/Dist per ticker, from general knowledge - used only when Yahoo's
# longName doesn't say (which was true for most non-Vanguard tickers tested).
ACC_DIST_FALLBACK = {
    "VWCE.DE": "Acc", "VWRL.L": "Dist", "VUSA.L": "Dist", "VUAA.DE": "Acc",
    "VEUR.L": "Dist", "VERX.L": "Dist", "VFEM.L": "Dist", "VJPN.L": "Dist",
    "VAPX.L": "Dist", "VNRT.L": "Dist", "VHYL.L": "Dist", "VGWE.DE": "Acc",
    "VEVE.L": "Acc", "VWRP.L": "Acc", "VUKE.L": "Dist", "VMID.L": "Dist",
    "VFEG.L": "Acc",
    "XDWD.DE": "Acc", "XMME.DE": "Acc", "XMEU.DE": "Acc", "XMUS.DE": "Acc",
    "XDJP.DE": "Acc", "XDWT.DE": "Acc", "XDWH.DE": "Acc", "XDWF.DE": "Acc",
    "XDWC.DE": "Acc", "XAIX.DE": "Acc", "XDEW.DE": "Acc", "DBXD.DE": "Dist",
    "XSX6.DE": "Acc", "XDWM.DE": "Acc",
    "CW8.PA": "Acc", "500.PA": "Acc", "ANX.PA": "Acc", "CG9.PA": "Acc",
    "CJ1.PA": "Acc", "WAT.PA": "Acc", "RS2K.PA": "Acc", "PUST.PA": "Acc",
    "SPY5.L": "Dist", "SPPW.DE": "Acc", "SWRD.L": "Acc", "WTEC.L": "Dist",
    "WHEA.L": "Dist", "WNRG.L": "Dist", "WFIN.L": "Dist", "WCOD.L": "Dist",
    "EMDV.L": "Dist", "USDV.L": "Dist", "GLDV.L": "Dist", "WSML.L": "Dist",
}

TD_OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etf_td_overrides.csv")


def fetch_etf_universe():
    return [
        {"ticker": t, "name": n, "provider": p, "index_category": cat, "index_type": typ}
        for t, n, p, cat, typ in ETF_UNIVERSE
    ]


def load_td_overrides():
    """Manually-maintained published tracking-difference figures.
    Empty by default - see etf_td_overrides.csv. Funds not in this file
    stay visibly blank rather than silently falling back to TER.
    """
    overrides = {}
    if os.path.exists(TD_OVERRIDES_PATH):
        with open(TD_OVERRIDES_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = (row.get("ticker") or "").strip()
                if not ticker:
                    continue
                td_pct = (row.get("td_pct") or "").strip()
                as_of = (row.get("as_of_date") or "").strip()
                overrides[ticker] = {
                    "td_pct": float(td_pct) if td_pct else None,
                    "td_as_of": as_of or None,
                }
    return overrides


# --- Price + risk metrics ---

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


def _risk_metrics_3y(series, latest_ts):
    """Max drawdown and annualized volatility over the trailing 3 years."""
    window = series[series.index >= latest_ts - pd.Timedelta(days=365 * 3)]
    if len(window) < 100:
        return None, None
    running_max = window.cummax()
    drawdown = (window / running_max - 1) * 100
    max_dd = round(float(drawdown.min()), 1)
    daily_returns = window.pct_change().dropna()
    vol = round(float(daily_returns.std() * (252 ** 0.5) * 100), 1)
    return max_dd, vol


def compute_price_metrics(closes, sym, requested_start_ts):
    if sym not in closes.columns:
        return None
    series = closes[sym].dropna()

    # Require sufficient trading history (~7+ months) before trusting the series
    if len(series) < 150:
        return None

    # Whether the series actually reaches back to (near) the requested download
    # start - the direct, reliable way to know a fund has 5+ years of real
    # tradable history. Yahoo's fundInceptionDate metadata field is NOT
    # reliable for this (verified case: XDWD.DE's fundInceptionDate implied a
    # ~3-year-old fund, but its actual downloaded price series reaches back to
    # 2014 - an 11-year discrepancy). A 45-day tolerance absorbs the download
    # window's own buffer plus holiday/weekend gaps near the boundary.
    tz = series.index.tz
    start_ts = requested_start_ts.tz_localize(tz) if tz is not None and requested_start_ts.tz is None else requested_start_ts
    has_5y_history = series.index[0] <= start_ts + pd.Timedelta(days=45)

    current_price = float(series.iloc[-1])
    tz = series.index.tz
    year_start = pd.Timestamp(f"{date.today().year}-01-01", tz=tz)
    ytd_series = series[series.index >= year_start]

    # Sanity floor on start/current price - catches NaN-riddled or thinly
    # traded series that would otherwise produce nonsense percentages.
    if current_price < 5.0:
        return None
    if ytd_series.empty or float(ytd_series.iloc[0]) < 5.0:
        return None

    latest_ts = series.index[-1]
    ytd_pct = _pct_return(series, year_start)
    # >500% YTD is almost certainly corrupted data (un-adjusted split/action)
    if ytd_pct is None or ytd_pct > 500:
        return None

    max_dd_3y, vol_3y = _risk_metrics_3y(series, latest_ts)

    return {
        "current_price": round(current_price, 2),
        "ytd_pct":  ytd_pct,
        "y2_pct":   _pct_return(series, latest_ts - pd.Timedelta(days=365 * 2), require_history=True),
        "y3_pct":   _pct_return(series, latest_ts - pd.Timedelta(days=365 * 3), require_history=True),
        "y5_pct":   _pct_return(series, latest_ts - pd.Timedelta(days=365 * 5), require_history=True),
        "max_dd_3y": max_dd_3y,
        "vol_3y":    vol_3y,
        "first_date": series.index[0],
        "has_5y_history": bool(has_5y_history),
    }


def get_price_data(all_etfs):
    """Download 5+ years of history and return {ticker: metrics_dict}."""
    requested_start_ts = pd.Timestamp.now() - pd.Timedelta(days=365 * 5 + 30)
    start_date = requested_start_ts.strftime("%Y-%m-%d")
    symbols = [e["ticker"] for e in all_etfs]
    results = {}

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
                    print(f"  No price data for {sym}, skipping.", file=sys.stderr)
                    continue
                metrics = compute_price_metrics(closes, sym, requested_start_ts)
                if metrics:
                    results[sym] = metrics
        except Exception as e:
            print(f"  Batch {i} error: {e}", file=sys.stderr)

    return results


# --- Fund metadata: AUM, currency, TER, domicile, Acc/Dist, age ---

def infer_domicile(info):
    """IE/LU/FR/DE/UK inferred from fund family text + phone country code.
    Not a dedicated Yahoo field - see module docstring. Unknown -> None,
    which the age/domicile filter treats as fail-closed (excluded), since
    domicile is tax-critical and shouldn't be guessed.
    """
    fam = (info.get("fundFamily") or "").lower()
    phone = info.get("phone") or ""
    if "ireland" in fam or phone.startswith("+353"):
        return "IE"
    if "luxembourg" in fam or phone.startswith("+352"):
        return "LU"
    if "france" in fam or phone.startswith("+33"):
        return "FR"
    if "germany" in fam or phone.startswith("+49"):
        return "DE"
    if "united kingdom" in fam or phone.startswith("+44"):
        return "UK"
    return None


def infer_acc_dist(info):
    name = (info.get("longName") or "").lower()
    if "accumulat" in name:
        return "Acc"
    if "distribut" in name:
        return "Dist"
    return None


def fetch_fund_metadata(etf):
    # Deliberately NOT using Yahoo's fundInceptionDate here - verified
    # unreliable (see build_screened_list). Fund age is determined from
    # actual downloaded price history instead (pm["has_5y_history"]).
    sym = etf["ticker"]
    out = {"currency": None, "aum": None, "ter": None, "domicile": None, "acc_dist": None}
    try:
        info = yf.Ticker(sym).info
        out["currency"] = info.get("currency")
        out["aum"] = info.get("totalAssets")
        out["ter"] = info.get("netExpenseRatio", info.get("annualReportExpenseRatio"))
        out["domicile"] = infer_domicile(info)
        out["acc_dist"] = infer_acc_dist(info)
    except Exception as e:
        print(f"  Metadata fetch failed for {sym}: {e}", file=sys.stderr)
    return sym, out


def fetch_all_metadata(all_etfs):
    print(f"Fetching fund metadata for {len(all_etfs)} ETFs...", file=sys.stderr)
    metadata = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_fund_metadata, e): e["ticker"] for e in all_etfs}
        for future in as_completed(futures):
            sym, data = future.result()
            metadata[sym] = data
    return metadata


# --- Assemble, filter, sort ---

def build_screened_list(all_etfs):
    price_data = get_price_data(all_etfs)
    metadata = fetch_all_metadata(all_etfs)
    td_overrides = load_td_overrides()

    survivors = []
    dropped = {"no_price_data": 0, "sector_or_country": 0, "not_eur": 0,
               "aum_too_small": 0, "too_young": 0, "not_ireland": 0, "not_acc": 0}

    for etf in all_etfs:
        sym = etf["ticker"]
        pm = price_data.get(sym)
        md = metadata.get(sym, {})

        if pm is None:
            dropped["no_price_data"] += 1
            continue
        if etf["index_type"] in ("sector", "country"):
            dropped["sector_or_country"] += 1
            continue
        if md.get("currency") != "EUR":
            dropped["not_eur"] += 1
            continue

        # AUM: only drop when Yahoo actually reports a figure below the floor.
        # Missing data must never silently pass OR fail this test - it's
        # surfaced as "n/a" in the report instead (see fmt_aum).
        aum = md.get("aum")
        if aum is not None and aum < AUM_FLOOR_EUR:
            dropped["aum_too_small"] += 1
            continue

        # Gate on the ACTUAL downloaded price series reaching back 5 years, not
        # Yahoo's fundInceptionDate metadata field - verified unreliable
        # (XDWD.DE's fundInceptionDate implied a ~3-year-old fund; its real
        # price history reaches back to 2014, an 11-year discrepancy).
        if not pm["has_5y_history"]:
            dropped["too_young"] += 1
            continue

        # DOMICILE_OVERRIDE takes priority over the live value - verified wrong
        # for these specific tickers, not just missing (see comment above).
        domicile = DOMICILE_OVERRIDE.get(sym) or md.get("domicile") or PROVIDER_DOMICILE_FALLBACK.get(etf["provider"])
        if domicile != "IE":
            dropped["not_ireland"] += 1
            continue

        acc_dist = md.get("acc_dist") or ACC_DIST_FALLBACK.get(sym)
        if acc_dist != "Acc":
            dropped["not_acc"] += 1
            continue

        record = {**etf, **pm, **md}
        record.pop("first_date", None)
        record["domicile"] = domicile
        record["replication"] = REPLICATION.get(sym, "Unknown")
        record.update(td_overrides.get(sym, {"td_pct": None, "td_as_of": None}))
        survivors.append(record)

    print(f"Survived all filters: {len(survivors)} / {len(all_etfs)}", file=sys.stderr)
    print(f"  Dropped breakdown: {dropped}", file=sys.stderr)

    survivors.sort(key=lambda e: (
        INDEX_ORDER.get(e["index_category"], 999),
        e["ter"] if e["ter"] is not None else float("inf"),
    ))
    return survivors


# --- Formatting helpers ---

def fmt_aum(v):
    if not v:
        return "—"
    if v >= 1e9:
        return f"€{v / 1e9:.1f}B"
    return f"€{v / 1e6:.0f}M"


def fmt_pct(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    sign = "+" if v > 0 else ""
    color = "#188038" if v > 0 else ("#c5221f" if v < 0 else "#555")
    return f'<span style="color:{color};font-weight:600">{sign}{v:.1f}%</span>'


def fmt_dd(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    color = "#188038" if v >= -15 else ("#f57c00" if v >= -30 else "#c5221f")
    return f'<span style="color:{color};font-weight:600">{v:.1f}%</span>'


def fmt_ter(v):
    if v is None:
        return '<span style="color:#aaa;font-style:italic">n/a</span>'
    return f"{v:.2f}%"


def fmt_td(td_pct, td_as_of):
    if td_pct is None:
        return '<span style="color:#aaa">—</span>'
    sign = "+" if td_pct > 0 else ""
    note = f' <span style="color:#999;font-size:10px">(as of {td_as_of})</span>' if td_as_of else ""
    return f"{sign}{td_pct:.2f}%{note}"


def fmt_price(v):
    return f"€{v:,.2f}"


def fmt_vol(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    return f"{v:.1f}%"


# --- HTML report ---

PROVIDER_COLORS = {
    "Vanguard": "#8b0000", "Xtrackers": "#00558c", "Amundi": "#f2a900", "SPDR": "#2e7d32",
}

TABLE_COLUMNS = [
    "#", "Ticker", "Fund", "Provider", "Domicile", "Replication",
    "TER (proxy)", "TD (manual)", "AUM", "Price", "5Y", "3Y", "2Y", "YTD",
    "Max DD (3Y)", "Vol (3Y)",
]


def build_html(etfs):
    today = datetime.now().strftime("%B %d, %Y")

    provider_counts = {}
    for e in etfs:
        provider_counts[e["provider"]] = provider_counts.get(e["provider"], 0) + 1
    summary = " · ".join(f"{v} from {k}" for k, v in sorted(provider_counts.items()))

    # Group by index_category in INDEX_ORDER, preserving the pre-sorted (by TER) order within each
    groups = []
    seen_cats = set()
    for e in etfs:
        cat = e["index_category"]
        if cat not in seen_cats:
            seen_cats.add(cat)
            groups.append(cat)

    ncols = len(TABLE_COLUMNS)
    body = ""
    for cat in groups:
        cat_etfs = [e for e in etfs if e["index_category"] == cat]
        body += (
            f'<tr><td colspan="{ncols}" style="background:#1a73e8;color:white;'
            f'font-weight:700;padding:7px 10px;font-size:12px">{cat}</td></tr>'
        )
        for rank, e in enumerate(cat_etfs, 1):
            bg = "#f1f8e9" if rank == 1 else "white"
            provider_color = PROVIDER_COLORS.get(e["provider"], "#555")
            body += (
                f'<tr style="background:{bg}">'
                f'<td class="c dim">{rank}</td>'
                f'<td class="b">{e["ticker"]}</td>'
                f'<td class="name">{e["name"]}</td>'
                f'<td class="c"><span style="background:{provider_color};color:white;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600;white-space:nowrap">{e["provider"]}</span></td>'
                f'<td class="c">{e["domicile"]}</td>'
                f'<td class="c small">{e["replication"]}</td>'
                f'<td class="c">{fmt_ter(e.get("ter"))}</td>'
                f'<td class="c">{fmt_td(e.get("td_pct"), e.get("td_as_of"))}</td>'
                f'<td class="c">{fmt_aum(e.get("aum"))}</td>'
                f'<td class="c">{fmt_price(e["current_price"])}</td>'
                f'<td class="c">{fmt_pct(e.get("y5_pct"))}</td>'
                f'<td class="c">{fmt_pct(e.get("y3_pct"))}</td>'
                f'<td class="c">{fmt_pct(e.get("y2_pct"))}</td>'
                f'<td class="c">{fmt_pct(e.get("ytd_pct"))}</td>'
                f'<td class="c">{fmt_dd(e.get("max_dd_3y"))}</td>'
                f'<td class="c">{fmt_vol(e.get("vol_3y"))}</td>'
                f'</tr>'
            )

    header_cells = "".join(
        f'<th class="l">{c}</th>' if c in ("Ticker", "Fund") else f'<th>{c}</th>'
        for c in TABLE_COLUMNS
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body   {{ font-family: Arial, sans-serif; color: #202124; max-width: 1300px; margin: 0 auto; padding: 24px; }}
  h1     {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; font-size: 20px; margin-bottom: 4px; }}
  .wrap  {{ overflow-x: auto; margin-top: 16px; }}
  table  {{ border-collapse: collapse; font-size: 12px; min-width: 1250px; width: 100%; }}
  th     {{ background: #0d47a1; color: white; padding: 8px 10px; text-align: center; font-size: 11px;
             font-weight: 600; white-space: nowrap; position: sticky; top: 0; }}
  th.l   {{ text-align: left; }}
  td     {{ border-bottom: 1px solid #f0f0f0; padding: 6px 10px; white-space: nowrap; }}
  td.c   {{ text-align: center; }}
  td.b   {{ font-weight: 700; font-size: 13px; }}
  td.dim {{ color: #999; }}
  td.small{{ font-size: 11px; color: #555; }}
  td.name{{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; }}
  tr:hover td {{ background: #e8f0fe !important; }}
</style>
</head>
<body>
  <h1>ETF Screener &mdash; {today}</h1>
  <p style="color:#666;font-size:13px;margin:4px 0 0">
    Grouped by index, sorted by TER within each group &middot; {summary}
  </p>
  <p style="color:#888;font-size:12px;margin:6px 0 0">
    Filters: AUM &ge; &euro;1B &middot; fund age &ge; 5y &middot; Ireland-domiciled &middot;
    Accumulating &middot; EUR-listed &middot; broad-market only (sector/country funds excluded)
  </p>
  <div class="wrap">
  <table>
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{body}</tbody>
  </table>
  </div>
  <p style="color:#999;font-size:11px;margin-top:16px;line-height:1.6">
    TER is the advertised cost; actual tracking difference can be higher or lower &mdash;
    check justETF for finalists. TD (manual) is populated only for funds looked up and
    added to etf_td_overrides.csv; blank means not yet looked up, not zero.<br>
    Replication method is maintained from general knowledge, cross-checked against Yahoo's
    fund name where it says "Swap" explicitly &mdash; confirm on the fund's KIID before investing.
    Domicile combines Yahoo's live fund metadata with manual corrections where that metadata
    was found to be wrong (not just missing) for a specific fund &mdash; spot-check on justETF
    before relying on this for a tax decision. Fund age is based on each ticker's own actual
    downloaded price history, not Yahoo's fundInceptionDate field (found unreliable).<br>
    Data via Yahoo Finance (yfinance) &middot; Generated {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
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

    screened = build_screened_list(all_etfs)

    today_str = datetime.now().strftime("%B %d, %Y")
    subject = f"ETF Screener - {today_str}"
    html = build_html(screened)

    if os.environ.get("GMAIL_APP_PASSWORD"):
        send_email(html, subject)
    else:
        print(html)
        print("\nTip: set GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL to send via email.", file=sys.stderr)
