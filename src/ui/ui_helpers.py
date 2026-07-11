import os
import threading
import streamlit as st

from src import config
from src.kis_client import get_access_token, fetch_option_price, fetch_stock_price, get_effective_premium
from src.master import download_master_file, get_underlying_info
from src.pricing import implied_volatility


def sync_widgets(src_key, dst_key):
    """지정된 두 세션 상태 키의 위젯 값을 실시간으로 동기화"""
    st.session_state[dst_key] = st.session_state[src_key]


def check_api_keys(app_key=None, app_secret=None):
    app_key = app_key or config.APP_KEY
    app_secret = app_secret or config.APP_SECRET
    if not app_key or not app_secret or app_key == "your_app_key_here" or app_secret == "your_app_secret_here":
        return False
    return True


def fetch_token():
    try:
        st.session_state.token = get_access_token()
    except Exception as e:
        st.error(f"API 접근 토큰 발급 중 오류 발생: {e}")
    return st.session_state.token

def safe_float(val):
    if not val:
        return 0.0
    try:
        return float(str(val).strip())
    except ValueError:
        return 0.0


def get_single_option_premium(symbol):
    token = None
    try:
        token = fetch_token()
    except Exception:
        pass

    premium = 0.0
    remn_cnt = 30
    details = {"bid": 0.0, "ask": 0.0, "last": 0.0, "premium": 0.0, "is_mid": False}

    # 1. Try KIS API first
    if token:
        try:
            price_res = fetch_option_price(token, symbol)
            if price_res and price_res.get("rt_cd") == "0":
                output = price_res.get("output1", {})
                premium = get_effective_premium(output)
                remn_cnt_str = output.get("remn_cnt", "").strip()
                remn_cnt = int(remn_cnt_str) if remn_cnt_str.isdigit() else 30
                
                bid = safe_float(output.get('bid_price'))
                ask = safe_float(output.get('ask_price'))
                last = safe_float(output.get('last_price'))
                details = {
                    "bid": bid,
                    "ask": ask,
                    "last": last,
                    "premium": premium,
                    "is_mid": (bid > 0 and ask > 0),
                    "remn_cnt": remn_cnt
                }
        except Exception:
            pass

    # 2. Fallback to yfinance if KIS API query fails or returns invalid price
    if premium <= 0.0:
        try:
            opt = None
            if "options_list" in st.session_state and st.session_state.options_list:
                for o in st.session_state.options_list:
                    if o["symbol"] == symbol:
                        opt = o
                        break
            if not opt and "basket" in st.session_state and st.session_state.basket:
                for o in st.session_state.basket:
                    if o["symbol"] == symbol:
                        opt = o
                        break
            if not opt:
                from src.master import get_option_chain
                ticker = get_ticker_from_symbol(symbol)
                if ticker:
                    options = get_option_chain(ticker)
                    for o in options:
                        if o["symbol"] == symbol:
                            opt = o
                            break

            if opt and opt.get("expiry_date") and opt["expiry_date"] != "Unknown":
                ticker = get_ticker_from_symbol(symbol)
                expiry_date = opt["expiry_date"]
                opt_type = opt["type"]
                strike = opt["strike"]

                import yfinance as yf
                stock = yf.Ticker(ticker)
                opt_chain = stock.option_chain(expiry_date)
                df = opt_chain.calls if opt_type == "Call" else opt_chain.puts
                row = df[df["strike"] == strike]
                if not row.empty:
                    premium = float(row.iloc[0]["lastPrice"])
                    bid = float(row.iloc[0].get("bid", 0.0))
                    ask = float(row.iloc[0].get("ask", 0.0))
                    import datetime
                    try:
                        exp_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
                        remn_cnt = max(0, (exp_dt - datetime.date.today()).days)
                    except Exception:
                        pass
                    
                    details = {
                        "bid": bid,
                        "ask": ask,
                        "last": premium,
                        "premium": premium,
                        "is_mid": (bid > 0 and ask > 0),
                        "remn_cnt": remn_cnt
                    }
        except Exception:
            pass

    # 3. Final fallback
    if premium <= 0.0:
        premium = 1.0
        remn_cnt = 30
        details = {"bid": 0.0, "ask": 0.0, "last": 1.0, "premium": 1.0, "is_mid": False, "remn_cnt": remn_cnt}

    return premium, remn_cnt, details


def update_basket_prices():
    if not st.session_state.basket:
        return

    token = None
    try:
        token = fetch_token()
    except Exception:
        pass

    first_opt = st.session_state.basket[0]
    underlying_ticker = get_ticker_from_symbol(first_opt["symbol"])
    if underlying_ticker:
        underlying_price = None
        underlying_info = get_underlying_info(first_opt["symbol"])
        
        # Try KIS API first
        if token and underlying_info:
            st.session_state.underlying_info = underlying_info
            try:
                stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                if stock_res and stock_res.get("rt_cd") == "0":
                    underlying_price = float(stock_res["output"]["last"])
            except Exception:
                pass

        # Try yfinance fallback for stock price
        if underlying_price is None:
            try:
                import yfinance as yf
                stock = yf.Ticker(underlying_ticker)
                spot_val = stock.fast_info.get("lastPrice")
                if spot_val is not None:
                    underlying_price = float(spot_val)
                else:
                    hist = stock.history(period="1d")
                    if not hist.empty:
                        underlying_price = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        if underlying_price is not None:
            st.session_state.underlying_price = underlying_price
            if underlying_info:
                st.session_state.underlying_info = underlying_info
            else:
                st.session_state.underlying_info = {"exchange": "UNKNOWN", "ticker": underlying_ticker}

    for opt in st.session_state.basket:
        try:
            premium, remn_cnt, _ = get_single_option_premium(opt["symbol"])
            opt["premium"] = premium
            opt["remn_cnt"] = remn_cnt
        except Exception as e:
            st.error(f"'{opt['symbol']}' 시세 갱신 중 오류 발생: {e}")


def recalculate_ivs(rate):
    # Determine the stock price at which the options premiums in the basket were set.
    # If the market is closed, we should solve for IV using the previous day's close price (prev_close) if available,
    # so that the solved IV is not distorted by today's after-hours/pre-market stock price movements.
    
    info = st.session_state.get("underlying_info")
    prev_close = info.get("prev_close") if info else None
    
    override_active = st.session_state.get("analysis_price_override_active", False)
    override_val = st.session_state.get("analysis_price_override_val")
    spot_live = st.session_state.get("underlying_price")
    
    if override_active and override_val is not None:
        S_current = override_val
    elif prev_close is not None and prev_close > 0:
        S_current = prev_close
    else:
        S_current = spot_live

    if S_current is None or S_current <= 0:
        return
    for opt in st.session_state.basket:
        # If we solve IV using yesterday's close stock price (prev_close), the options premium is also from yesterday,
        # so we must use yesterday's DTE (today's DTE + 1) to avoid solving IV with T near 0.
        if S_current == prev_close and prev_close is not None and prev_close > 0:
            import pytz
            import datetime
            est = pytz.timezone("America/New_York")
            ny_time = datetime.datetime.now(est)
            is_market_open = (ny_time.weekday() < 5 and 
                              datetime.time(9, 30) <= ny_time.time() <= datetime.time(16, 0))
            is_market_closed = not is_market_open
            opt_dte = opt["remn_cnt"] + (1 if is_market_closed else 0)
        else:
            opt_dte = opt["remn_cnt"]
            
        t_current = float(max(0.05, opt_dte)) / 365.0
        iv = implied_volatility(
            market_price=opt["premium"],
            S=S_current,
            K=opt["strike"],
            T=t_current,
            r=rate,
            option_type=opt["type"]
        )
        if iv <= 0.0:
            iv = 0.30
        opt["iv"] = iv


def find_beps(prices, payoffs):
    beps_list = []
    for i in range(len(payoffs) - 1):
        y1, y2 = payoffs[i], payoffs[i + 1]
        x1, x2 = prices[i], prices[i + 1]
        if y1 * y2 < 0:
            bep_x = x1 - y1 * (x2 - x1) / (y2 - y1)
            beps_list.append(bep_x)
        elif y1 == 0:
            beps_list.append(x1)
    return sorted(list(set(round(b, 2) for b in beps_list)))


def initialize_session_state():
    defaults = {
        "basket": [],
        "underlying_price": None,
        "underlying_info": None,
        "search_underlying_price": None,
        "search_underlying_info": None,
        "token": None,
        "queried_real_prices": {},
        "user_queried_symbols": set(),
        "valuation_mode": "Mode A",
        "master_download_started": False,
        "master_status": "idle",
        "last_search_ticker": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def should_search_ticker(search_ticker: str, *, search_clicked: bool = False) -> bool:
    if not search_ticker:
        return False
    if search_clicked:
        return True
    if "last_search_ticker" not in st.session_state:
        return False
    previous_ticker = st.session_state.get("last_search_ticker")
    if previous_ticker is None:
        return False
    return previous_ticker != search_ticker


def ensure_master_file_ready():
    if st.session_state.get("master_download_started"):
        return

    st.session_state.master_download_started = True
    if os.path.exists(config.MASTER_FILE):
        st.session_state.master_status = "ready"
        return

    st.session_state.master_status = "loading"

    def _download_master_file():
        try:
            download_master_file()
        except Exception:
            pass

    threading.Thread(target=_download_master_file, daemon=True).start()


def get_ticker_from_symbol(symbol: str) -> str:
    """옵션 기호(Symbol) 문자열에서 종목 티커(Ticker) 추출"""
    import re
    # 만기월코드(1글자)와 만기연도(2자리 숫자)에 해당하는 접미사(예: N26)를 매칭하여 
    # 앞쪽의 순수 티커 부분(예: TSLA)만 정확히 캡처합니다.
    match = re.match(r"(?:\d?)([A-Z]+)(?:[A-Z]\d{2})", symbol)
    if match:
        return match.group(1).upper()
    return ""
