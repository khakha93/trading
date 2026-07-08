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


def get_single_option_premium(symbol):
    token = fetch_token()
    if not token:
        return 1.0, 30
    try:
        price_res = fetch_option_price(token, symbol)
        if price_res and price_res.get("rt_cd") == "0":
            output = price_res.get("output1", {})
            premium = get_effective_premium(output)
            remn_cnt_str = output.get("remn_cnt", "").strip()
            remn_cnt = int(remn_cnt_str) if remn_cnt_str.isdigit() else 30
            return premium, remn_cnt
    except Exception as e:
        st.warning(f"'{symbol}' 시세 조회 중 오류 발생: {e}. 기본값으로 설정합니다.")
    return 1.0, 30


def update_basket_prices():
    token = fetch_token()
    if not token or not st.session_state.basket:
        return

    first_opt = st.session_state.basket[0]
    underlying_info = get_underlying_info(first_opt["symbol"])
    if underlying_info:
        st.session_state.underlying_info = underlying_info
        try:
            stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
            if stock_res and stock_res.get("rt_cd") == "0":
                st.session_state.underlying_price = float(stock_res["output"]["last"])
        except Exception as e:
            st.error(f"기초자산 시세 조회 실패: {e}")

    for opt in st.session_state.basket:
        try:
            price_res = fetch_option_price(token, opt["symbol"])
            if price_res and price_res.get("rt_cd") == "0":
                output = price_res.get("output1", {})
                premium = get_effective_premium(output)
                opt["premium"] = premium
                remn_cnt_str = output.get("remn_cnt", "").strip()
                if remn_cnt_str.isdigit():
                    opt["remn_cnt"] = int(remn_cnt_str)
            else:
                st.error(f"'{opt['symbol']}' API 조회 실패: {price_res.get('msg1') if price_res else '응답 없음'}")
        except Exception as e:
            st.error(f"'{opt['symbol']}' 시세 갱신 중 오류 발생: {e}")


def recalculate_ivs(rate):
    S_current = st.session_state.underlying_price
    if S_current is None or S_current <= 0:
        return
    for opt in st.session_state.basket:
        t_current = float(opt.get("remn_cnt", 30)) / 365.0
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
        "token": None,
        "queried_real_prices": {},
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
