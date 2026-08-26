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


NIKKEI_225 = [
    ("7203.T","Toyota Motor"),("9984.T","SoftBank Group"),("6758.T","Sony Group"),
    ("6861.T","Keyence"),("8035.T","Tokyo Electron"),("6954.T","Fanuc"),
    ("7974.T","Nintendo"),("8306.T","Mitsubishi UFJ Financial"),("9432.T","NTT"),
    ("6098.T","Recruit Holdings"),("4063.T","Shin-Etsu Chemical"),("8316.T","Sumitomo Mitsui Financial"),
    ("9983.T","Fast Retailing"),("7741.T","Hoya"),("4519.T","Chugai Pharmaceutical"),
    ("6902.T","Denso"),("8058.T","Mitsubishi Corp"),("8001.T","ITOCHU Corp"),
    ("6367.T","Daikin Industries"),("9022.T","Central Japan Railway"),("4568.T","Daiichi Sankyo"),
    ("4543.T","Terumo"),("4502.T","Takeda Pharmaceutical"),("7267.T","Honda Motor"),
    ("2914.T","Japan Tobacco"),("9020.T","East Japan Railway"),("8031.T","Mitsui & Co"),
    ("6501.T","Hitachi"),("7751.T","Canon"),("4901.T","Fujifilm Holdings"),
    ("7733.T","Olympus"),("5401.T","Nippon Steel"),("8411.T","Mizuho Financial"),
    ("6723.T","Renesas Electronics"),("4523.T","Eisai"),("3382.T","Seven & i Holdings"),
    ("8267.T","Aeon"),("2802.T","Ajinomoto"),("6762.T","TDK"),("6971.T","Kyocera"),
    ("6503.T","Mitsubishi Electric"),("6702.T","Fujitsu"),("7011.T","Mitsubishi Heavy Industries"),
    ("5020.T","Eneos Holdings"),("8766.T","Tokio Marine Holdings"),("8630.T","Sompo Holdings"),
    ("1925.T","Daiwa House Industry"),("8604.T","Nomura Holdings"),("4661.T","Oriental Land"),
    ("4452.T","Kao"),("3407.T","Asahi Kasei"),("4188.T","Mitsubishi Chemical Group"),
    ("4507.T","Shionogi"),("7832.T","Bandai Namco Holdings"),("4324.T","Dentsu Group"),
    ("6857.T","Advantest"),("9433.T","KDDI"),("9434.T","SoftBank Corp"),
    ("6920.T","Lasertec"),("7735.T","Screen Holdings"),("6146.T","Disco Corp"),
    ("8802.T","Mitsubishi Estate"),("4151.T","Kyowa Kirin"),("5108.T","Bridgestone"),
    ("6594.T","Nidec"),("7309.T","Shimano"),("3659.T","Nexon"),
    ("9064.T","Yamato Holdings"),("8309.T","Sumitomo Mitsui Trust"),
    ("4578.T","Otsuka Holdings"),("8750.T","Dai-ichi Life Holdings"),
    ("9101.T","Nippon Yusen"),("9104.T","Mitsui OSK Lines"),("9107.T","Kawasaki Kisen"),
    ("5019.T","Idemitsu Kosan"),("4704.T","Trend Micro"),("6770.T","Alps Alpine"),
    ("6503.T","Mitsubishi Electric"),("2768.T","Sojitz"),
]

HANG_SENG = [
    ("0001.HK","CK Hutchison"),("0002.HK","CLP Holdings"),("0003.HK","HK & China Gas"),
    ("0005.HK","HSBC Holdings"),("0006.HK","Power Assets"),("0011.HK","Hang Seng Bank"),
    ("0012.HK","Henderson Land"),("0016.HK","Sun Hung Kai Properties"),("0017.HK","New World Development"),
    ("0019.HK","Swire Pacific"),("0027.HK","Galaxy Entertainment"),("0066.HK","MTR Corporation"),
    ("0083.HK","Sino Land"),("0101.HK","Hang Lung Properties"),("0175.HK","Geely Automobile"),
    ("0267.HK","CITIC"),("0288.HK","WH Group"),("0291.HK","China Resources Beer"),
    ("0316.HK","Orient Overseas International"),("0388.HK","Hong Kong Exchanges"),
    ("0489.HK","Dongfeng Motor"),("0688.HK","China Overseas Land"),("0700.HK","Tencent Holdings"),
    ("0762.HK","China Unicom HK"),("0823.HK","Link REIT"),("0857.HK","PetroChina H"),
    ("0868.HK","Xinyi Glass"),("0883.HK","CNOOC"),("0939.HK","China Construction Bank H"),
    ("0941.HK","China Mobile"),("0960.HK","Longfor Group"),("0968.HK","Xinyi Solar"),
    ("0992.HK","Lenovo Group"),("1038.HK","CK Infrastructure"),("1044.HK","Hengan International"),
    ("1088.HK","China Shenhua H"),("1093.HK","CSPC Pharmaceutical"),("1109.HK","China Resources Land"),
    ("1113.HK","CK Asset Holdings"),("1177.HK","Sino Biopharmaceutical"),("1211.HK","BYD H"),
    ("1299.HK","AIA Group"),("1378.HK","China Hongqiao"),("1398.HK","ICBC H"),
    ("1810.HK","Xiaomi"),("1876.HK","Budweiser APAC"),("1928.HK","Sands China"),
    ("1997.HK","Wharf REIC"),("2007.HK","Country Garden"),("2018.HK","AAC Technologies"),
    ("2020.HK","ANTA Sports"),("2269.HK","WuXi Biologics"),("2313.HK","Shenzhou International"),
    ("2318.HK","Ping An Insurance H"),("2319.HK","China Mengniu Dairy"),("2331.HK","Li Ning"),
    ("2382.HK","Sunny Optical"),("2388.HK","BOC Hong Kong"),("2628.HK","China Life H"),
    ("3328.HK","Bank of Communications H"),("3690.HK","Meituan"),("3988.HK","Bank of China H"),
    ("6098.HK","Country Garden Services"),("6862.HK","Haidilao"),
    ("9618.HK","JD.com HK"),("9633.HK","Nongfu Spring"),("9988.HK","Alibaba HK"),
    ("9999.HK","NetEase HK"),("1209.HK","CR Mixc Lifestyle"),
]

KOSPI_100 = [
    ("005930.KS","Samsung Electronics"),("000660.KS","SK Hynix"),("207940.KS","Samsung Biologics"),
    ("005380.KS","Hyundai Motor"),("035420.KS","NAVER"),("000270.KS","Kia"),
    ("028260.KS","Samsung C&T"),("051910.KS","LG Chem"),("006400.KS","Samsung SDI"),
    ("373220.KS","LG Energy Solution"),("035720.KS","Kakao"),("003670.KS","POSCO Holdings"),
    ("017670.KS","SK Telecom"),("030200.KS","KT Corp"),("012330.KS","Hyundai Mobis"),
    ("086790.KS","Hana Financial Group"),("105560.KS","KB Financial Group"),
    ("055550.KS","Shinhan Financial Group"),("316140.KS","Woori Financial Group"),
    ("032830.KS","Samsung Life Insurance"),("018260.KS","Samsung SDS"),
    ("009150.KS","Samsung Electro-Mechanics"),("010130.KS","Korea Zinc"),
    ("033780.KS","KT&G"),("066570.KS","LG Electronics"),("000810.KS","Samsung Fire & Marine"),
    ("034220.KS","LG Display"),("010950.KS","S-Oil"),("090430.KS","Amorepacific"),
    ("032640.KS","LG Uplus"),("015760.KS","Korea Electric Power"),("009830.KS","Hanwha Solutions"),
    ("097950.KS","CJ CheilJedang"),("180640.KS","Hanwha Aerospace"),("267250.KS","HD Hyundai"),
    ("000720.KS","Hyundai E&C"),("003550.KS","LG Corp"),("034730.KS","SK Inc"),
    ("000880.KS","Hanwha Corp"),("352820.KS","HYBE"),("293490.KS","Kakao Bank"),
    ("086280.KS","Hyundai Glovis"),("003490.KS","Korean Air"),("138040.KS","Meritz Financial"),
    ("036570.KS","NCsoft"),("009540.KS","HD Hyundai Heavy Industries"),("011200.KS","HMM"),
    ("047050.KS","POSCO Future M"),("051900.KS","LG H&H"),("004020.KS","Hyundai Steel"),
    ("021240.KS","Coway"),("006800.KS","Mirae Asset Securities"),("024110.KS","IBK"),
    ("096770.KS","SK Innovation"),("078930.KS","GS Holdings"),("001040.KS","CJ Corp"),
    ("161390.KS","Hankook Tire"),("004170.KS","Shinsegae"),("036460.KS","Korea Gas Corp"),
    ("023530.KS","Lotte Shopping"),("068270.KS","Celltrion"),("323410.KS","Kakao Pay"),
    ("096530.KS","SK Biopharmaceuticals"),
]

CSI_300 = [
    # Shanghai (SS)
    ("600519.SS","Kweichow Moutai"),("601318.SS","Ping An Insurance"),("600036.SS","China Merchants Bank"),
    ("601398.SS","ICBC"),("600900.SS","China Yangtze Power"),("601988.SS","Bank of China"),
    ("600309.SS","Wanhua Chemical"),("601628.SS","China Life Insurance"),("600276.SS","Hengrui Medicine"),
    ("600887.SS","Yili Group"),("601166.SS","Industrial Bank"),("601012.SS","LONGi Green Energy"),
    ("600690.SS","Haier Smart Home"),("601601.SS","China Pacific Insurance"),
    ("601939.SS","China Construction Bank A"),("600016.SS","Minsheng Banking"),
    ("600030.SS","CITIC Securities"),("600000.SS","Shanghai Pudong Development Bank"),
    ("601888.SS","China Tourism Group Duty Free"),("600104.SS","SAIC Motor"),
    ("601857.SS","PetroChina A"),("600028.SS","Sinopec A"),("600031.SS","Sany Heavy Industry"),
    ("601919.SS","COSCO Shipping"),("600585.SS","Anhui Conch Cement"),
    ("601390.SS","China Railway Group"),("601728.SS","China Telecom A"),
    ("601225.SS","Shaanxi Coal Industry"),("600019.SS","Baoshan Iron & Steel"),
    ("601100.SS","CRRC Corp A"),("601111.SS","Air China"),("601238.SS","Guangzhou Automobile"),
    ("601211.SS","Guotai Junan Securities"),("601688.SS","Huatai Securities"),
    ("600346.SS","Hengli Petrochemical"),("601800.SS","China Communications Construction"),
    ("600048.SS","Poly Developments"),("603288.SS","Haitian Flavouring"),
    ("603259.SS","WuXi AppTec A"),("600438.SS","Tongwei"),("601998.SS","China CITIC Bank"),
    ("600547.SS","Shandong Gold Mining"),("600011.SS","Huaneng Power"),
    ("601600.SS","Chalco"),("600050.SS","China Unicom A"),("600196.SS","Fosun Pharmaceutical"),
    ("601669.SS","Power Construction Corp"),("600618.SS","Shanghai Chlor-Alkali"),
    # Shenzhen (SZ)
    ("000858.SZ","Wuliangye Yibin"),("000001.SZ","Ping An Bank"),("002594.SZ","BYD A"),
    ("300750.SZ","CATL"),("000333.SZ","Midea Group"),("002415.SZ","Hikvision"),
    ("002714.SZ","Muyuan Foods"),("000651.SZ","Gree Electric"),("300760.SZ","Mindray Medical"),
    ("000568.SZ","Luzhou Laojiao"),("002304.SZ","Jiangsu Yanghe Brewery"),
    ("300274.SZ","Sungrow Power"),("002475.SZ","Luxshare Precision"),("000002.SZ","China Vanke"),
    ("300015.SZ","Aier Eye Hospital"),("000725.SZ","BOE Technology"),
    ("300059.SZ","East Money Information"),("002230.SZ","iFlytek"),
    ("002236.SZ","Dahua Technology"),("300124.SZ","Inovance Technology"),
    ("002241.SZ","Goertek"),("300122.SZ","Zhifei Biological Products"),
    ("001979.SZ","China Merchants Shekou"),("002027.SZ","Focus Media"),
    ("300498.SZ","Wens Foodstuffs"),("002142.SZ","Bank of Ningbo"),
    ("300014.SZ","EVE Energy"),("000100.SZ","TCL Technology"),
    ("002352.SZ","S.F. Holding"),("002049.SZ","Unigroup Guoxin"),
    ("002372.SZ","Zhejiang NHU"),("300433.SZ","Lansi Technology"),
]


def fetch_nikkei225():
    return [{"ticker": t, "name": n, "index": "Nikkei 225"} for t, n in NIKKEI_225]

def fetch_hang_seng():
    return [{"ticker": t, "name": n, "index": "Hang Seng"} for t, n in HANG_SENG]

def fetch_kospi100():
    return [{"ticker": t, "name": n, "index": "KOSPI 100"} for t, n in KOSPI_100]

def fetch_csi300():
    return [{"ticker": t, "name": n, "index": "CSI 300"} for t, n in CSI_300]


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

    # Filter 1: require sufficient trading history (~7+ months)
    if len(series) < 150:
        return None

    current_price = float(series.iloc[-1])
    tz = series.index.tz
    year_start = pd.Timestamp(f"{date.today().year}-01-01", tz=tz)
    ytd_series = series[series.index >= year_start]

    # Filter 2: current price must be >= $5 (excludes penny stocks)
    if current_price < 5.0:
        return None

    # Filter 3: start-of-year price must also be >= $5
    # Without this, stocks that recovered FROM penny-stock levels show false +1000%+ YTD
    if ytd_series.empty or float(ytd_series.iloc[0]) < 5.0:
        return None

    latest_ts = series.index[-1]
    high_52w = float(series.max())

    ytd_pct = _pct_return(series, year_start)
    # Filter 4: >500% YTD is almost certainly corrupted data (un-adjusted reverse split)
    if ytd_pct is None or ytd_pct > 500:
        return None

    return {
        "current_price": round(current_price, 2),
        "ytd_pct":    ytd_pct,
        "m6_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=182)),
        "m3_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=91)),
        "m1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=30)),
        "w1_pct":     _pct_return(series, latest_ts - pd.Timedelta(days=7)),
        "vs_52w_pct": round(((current_price - high_52w) / high_52w) * 100, 1),
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
            # auto_adjust=False: use Yahoo's own pre-computed Adj Close, which handles
            # splits and dividends more reliably than yfinance's in-library recalculation.
            raw = yf.download(batch, start=start_date, progress=False, auto_adjust=False)
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Adj Close"]
            elif "Adj Close" in raw.columns:
                closes = raw[["Adj Close"]].rename(columns={"Adj Close": batch[0]})
            else:
                closes = raw
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
        currency = {"DAX": "€", "Nikkei 225": "¥", "Hang Seng": "HK$", "KOSPI 100": "₩", "CSI 300": "¥"}.get(s["index"], "$")
        price_str = f"{currency}{s['current_price']:,.0f}" if s["index"] in ("Nikkei 225", "KOSPI 100") else f"{currency}{s['current_price']:,.2f}"
        idx_colors = {
            "DAX": "#1565c0", "S&P 500": "#2e7d32", "NASDAQ 100": "#6a1b9a", "NASDAQ": "#e65100",
            "Nikkei 225": "#b71c1c", "Hang Seng": "#00695c", "KOSPI 100": "#1a237e", "CSI 300": "#e65100",
        }
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
    all_tickers = (
        fetch_sp500() + fetch_nasdaq100() + fetch_dax() + fetch_nasdaq_top500() +
        fetch_nikkei225() + fetch_hang_seng() + fetch_kospi100() + fetch_csi300()
    )
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
