# --- Windows SSL Bug Patch ---
import sys
import ssl

if sys.platform == 'win32':
    try:
        orig_load_windows_store_certs = ssl.SSLContext._load_windows_store_certs
        def patched_load_windows_store_certs(self, storename, purpose):
            try:
                orig_load_windows_store_certs(self, storename, purpose)
            except Exception:
                try:
                    import certifi
                    self.load_verify_locations(certifi.where())
                except Exception:
                    pass
        ssl.SSLContext._load_windows_store_certs = patched_load_windows_store_certs
    except Exception:
        pass
# -----------------------------

import streamlit as st
import pandas as pd
import numpy as np
import re
import os
import plotly.graph_objects as go

from src import config

config.load_settings(secrets=getattr(st, "secrets", None))

APP_KEY = config.APP_KEY
APP_SECRET = config.APP_SECRET

from src.kis_client import get_access_token, fetch_option_price, fetch_stock_price, get_effective_premium
from src.master import download_master_file, get_option_chain, get_underlying_info
from src.pricing import black_scholes, implied_volatility

# Page configuration
st.set_page_config(
    page_title="미국주식옵션 시뮬레이터",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Mode / Premium CSS styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Title styling */
    .main-title {
        font-family: 'Outfit', sans-serif;
        background: linear-gradient(135deg, #00C6FF, #0072FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.3rem;
        margin-bottom: 0.2rem;
    }
    
    .subtitle {
        color: #8888aa;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }
    
    /* Custom container card */
    .custom-card {
        background-color: #1E1E24;
        border: 1px solid #2D2D35;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    /* Status indicator */
    .status-ok {
        color: #00E676;
        font-weight: bold;
    }
    .status-error {
        color: #FF1744;
        font-weight: bold;
    }
    
    /* Styled buttons */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* ================================================================ */
    /* Plotly shapes - 테마 상태를 직접 감지하는 완벽한 CSS 스타일링  $$$     */
    /* ================================================================ */

    /* 공통 스타일 지정 (두께 및 실선 고정) */
    .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
    .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
    .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
    .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
        stroke-opacity: 0.85 !important;
        stroke-width: 1px !important;
        vector-effect: non-scaling-stroke !important;
        shape-rendering: geometricPrecision !important;
    }

    /* 1) 사용자가 [다크 모드]일 때 -> 세로선을 밝은 연회색(#E0E0E0)으로 적용 */
    [data-theme="dark"] .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
    [data-theme="dark"] .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
    [data-theme="dark"] .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
    [data-theme="dark"] .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
        stroke: #D1D5DB !important;
        fill: #D1D5DB !important; /* 글자 색상 채우기 */
    }

    /* 2) 사용자가 [라이트(화이트) 모드]일 때 -> 세로선을 대비감이 명확한 짙은 차콜색(#2C3E50)으로 적용 */
    [data-theme="light"] .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
    [data-theme="light"] .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
    [data-theme="light"] .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
    [data-theme="light"] .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
        stroke: #5A626A !important;
        fill: #5A626A !important; /* 글자 색상 채우기 */
    }

</style>
""", unsafe_allow_html=True)

# ----------------- Helper Functions -----------------

def sync_widgets(src_key, dst_key):
    """지정된 두 세션 상태 키의 위젯 값을 실시간으로 동기화"""
    st.session_state[dst_key] = st.session_state[src_key]

def check_api_keys():
    if not APP_KEY or not APP_SECRET or APP_KEY == "your_app_key_here" or APP_SECRET == "your_app_secret_here":
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
    
    # Find underlying symbol from first option code
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
            
    # Fetch options
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
        # Calculate implied volatility
        iv = implied_volatility(
            market_price=opt["premium"],
            S=S_current,
            K=opt["strike"],
            T=t_current,
            r=rate,
            option_type=opt["type"]
        )
        if iv <= 0.0:
            iv = 0.30  # fallback
        opt["iv"] = iv

def find_beps(prices, payoffs):
    beps_list = []
    for i in range(len(payoffs) - 1):
        y1, y2 = payoffs[i], payoffs[i+1]
        x1, x2 = prices[i], prices[i+1]
        if y1 * y2 < 0:
            bep_x = x1 - y1 * (x2 - x1) / (y2 - y1)
            beps_list.append(bep_x)
        elif y1 == 0:
            beps_list.append(x1)
    return sorted(list(set(round(b, 2) for b in beps_list)))

# ----------------- Session State Init -----------------

if 'basket' not in st.session_state:
    st.session_state.basket = []
if 'underlying_price' not in st.session_state:
    st.session_state.underlying_price = None
if 'underlying_info' not in st.session_state:
    st.session_state.underlying_info = None
if 'token' not in st.session_state:
    st.session_state.token = None
if 'queried_real_prices' not in st.session_state:
    st.session_state.queried_real_prices = {}

# Initialize master file
try:
    download_master_file()
except Exception as e:
    st.error(f"마스터 파일 관리 오류: {e}")

# ----------------- Sidebar -----------------

st.sidebar.markdown("<h2 style='font-family: Outfit; font-weight: 700; margin-bottom: 15px;'>⚙️ 설정 & 시뮬레이터</h2>", unsafe_allow_html=True)

# API Status Card (Dynamic HTML status badge with CSS pulse animation)
if check_api_keys():
    status_card_html = """
    <div style="border: 1.5px solid #00E676; border-radius: 12px; padding: 12px 15px; background-color: rgba(0, 230, 118, 0.05); font-family: Outfit; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0, 230, 118, 0.05);">
        <div style="font-size: 0.75rem; color: #8888aa; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">📡 API CONNECTION STATUS</div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="height: 10px; width: 10px; background-color: #00E676; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #00E676; animation: statusPulse 1.5s infinite;"></span>
            <span style="color: #00E676; font-weight: 700; font-size: 0.95rem;">Live Connected (정상)</span>
        </div>
    </div>
    <style>
        @keyframes statusPulse {
            0% { transform: scale(0.95); opacity: 0.7; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.7; }
        }
    </style>
    """
else:
    status_card_html = """
    <div style="border: 1.5px solid #FF1744; border-radius: 12px; padding: 12px 15px; background-color: rgba(255, 23, 68, 0.05); font-family: Outfit; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(255, 23, 68, 0.05);">
        <div style="font-size: 0.75rem; color: #8888aa; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">📡 API CONNECTION STATUS</div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="height: 10px; width: 10px; background-color: #FF1744; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #FF1744;"></span>
            <span style="color: #FF1744; font-weight: 700; font-size: 0.95rem;">Disconnected (연결 안 됨)</span>
        </div>
    </div>
    """
st.sidebar.markdown(status_card_html, unsafe_allow_html=True)

if not check_api_keys():
    st.sidebar.warning("프로젝트 루트의 `.env` 파일에 APP_KEY와 APP_SECRET을 입력해 주세요.")
else:
    # Sidebar Refresh Button (HTS style sync button)
    if st.sidebar.button("🔄 실시간 시세 동기화 (Refresh)", use_container_width=True):
        if st.session_state.basket:
            with st.sidebar.spinner("실시간 시세 동기화 중..."):
                update_basket_prices()
                # Use current rate from number input or session state
                current_rate = st.session_state.get('rate_num', 4.0) / 100.0
                recalculate_ivs(current_rate)
            st.sidebar.success("시세 동기화 완료!")
            st.rerun()
        else:
            st.sidebar.info("바스켓에 등록된 옵션이 없습니다.")

# Expiry date bounds for slider
max_dte = 30
if st.session_state.basket:
    max_dte = max(opt.get("remn_cnt", 30) for opt in st.session_state.basket)

# Initialize sidebar session state keys if not present
if 'dte_slider' not in st.session_state:
    st.session_state.dte_slider = int(max_dte)
if 'dte_num' not in st.session_state:
    st.session_state.dte_num = int(max_dte)
    
if 'vol_slider' not in st.session_state:
    st.session_state.vol_slider = 0.0
if 'vol_num' not in st.session_state:
    st.session_state.vol_num = 0.0
    
if 'rate_slider' not in st.session_state:
    st.session_state.rate_slider = 4.0
if 'rate_num' not in st.session_state:
    st.session_state.rate_num = 4.0

# Initialize sidebar session state keys if not present
if 'dte_slider' not in st.session_state:
    st.session_state.dte_slider = int(max_dte)
if 'dte_num' not in st.session_state:
    st.session_state.dte_num = int(max_dte)
    
if 'vol_slider' not in st.session_state:
    st.session_state.vol_slider = 0.0
if 'vol_num' not in st.session_state:
    st.session_state.vol_num = 0.0
    
if 'rate_slider' not in st.session_state:
    st.session_state.rate_slider = 4.0
if 'rate_num' not in st.session_state:
    st.session_state.rate_num = 4.0

# Clip DTE state if max_dte has changed due to basket updates
if st.session_state.dte_slider > int(max_dte):
    st.session_state.dte_slider = int(max_dte)
if st.session_state.dte_num > int(max_dte):
    st.session_state.dte_num = int(max_dte)

# Sliders & Numbers in Sidebar (Global params only)
st.sidebar.write("### 🎛️ 시뮬레이션 파라미터")

# 1. Implied Volatility Change (IV)
st.sidebar.write("**⚡ 내재변동성(IV) 변화율 (%p)**")
st.sidebar.slider("IV 슬라이더", min_value=-50.0, max_value=50.0, key="vol_slider", on_change=sync_widgets, args=("vol_slider", "vol_num"), label_visibility="collapsed")
vol_input_val = st.sidebar.number_input("IV 정밀 입력 (%p)", min_value=-50.0, max_value=50.0, step=0.1, key="vol_num", on_change=sync_widgets, args=("vol_num", "vol_slider"), label_visibility="collapsed")
vol_change_val = vol_input_val / 100.0

# 2. Risk-free Rate
st.sidebar.write("**💵 무위험 이자율 (%)**")
st.sidebar.slider("이자율 슬라이더", min_value=0.0, max_value=10.0, key="rate_slider", on_change=sync_widgets, args=("rate_slider", "rate_num"), label_visibility="collapsed")
rate_input_val = st.sidebar.number_input("이자율 정밀 입력 (%)", min_value=0.0, max_value=10.0, step=0.01, key="rate_num", on_change=sync_widgets, args=("rate_num", "rate_slider"), label_visibility="collapsed")
rate_val = rate_input_val / 100.0

st.sidebar.markdown("---")
st.sidebar.info("💡 **팁**: 대화형 Plotly 그래프 위에 마우스를 올리면 각 지점의 구체적인 만기 손익과 만기 전 예상 손익 정보를 툴팁으로 확인할 수 있습니다.")

# ----------------- Main Layout -----------------

st.markdown("<div class='main-title'>미국옵션 합성 수익곡선 분석기</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>한국투자증권 OpenAPI 미국옵션 실시간 연동 시뮬레이터</div>", unsafe_allow_html=True)

# Display tabs as a native Streamlit layout
tab2, tab1 = st.tabs(["🔍 종목 검색 & 추가", "📊 포트폴리오 분석 & 시뮬레이션"])

# ==================== Tab 1: Analysis & Simulation ====================
with tab1:
    if not st.session_state.basket:
        st.info("🧺 바스켓이 비어 있습니다. **'종목 검색 & 추가'** 탭에서 옵션을 검색하여 추가해 주세요.")
    else:
        # Show and manage basket
        st.write("### 🧺 현재 포트폴리오 바스켓")
        
        # Display underlying info
        if st.session_state.underlying_price is not None:
            underlying_ticker = st.session_state.underlying_info.get("ticker", "")
            st.markdown(f"**기초자산 현재가 ({underlying_ticker})**: `${st.session_state.underlying_price:.2f}`")
            
        cols_header = st.columns([2.5, 1.2, 1.2, 1.2, 1.2, 1.0])
        cols_header[0].write("**옵션 코드**")
        cols_header[1].write("**구분 (행사가)**")
        cols_header[2].write("**포지션**")
        cols_header[3].write("**수량**")
        cols_header[4].write("**시자가/평단가 ($)**")
        cols_header[5].write("**작업**")
        
        to_delete = []
        
        for idx, opt in enumerate(st.session_state.basket):
            cols = st.columns([2.5, 1.2, 1.2, 1.2, 1.2, 1.0])
            cols[0].write(f"`{opt['symbol']}`")
            cols[1].write(f"{opt['type']} (${opt['strike']:.2f})")
            
            # Position select
            new_action = cols[2].selectbox(
                "포지션", ["Long", "Short"],
                index=0 if opt["action"] == "Long" else 1,
                key=f"action_{idx}",
                label_visibility="collapsed"
            )
            opt["action"] = new_action
            
            # Quantity select
            new_qty = cols[3].number_input(
                "수량", min_value=1, max_value=1000,
                value=int(opt["quantity"]),
                key=f"qty_{idx}",
                label_visibility="collapsed"
            )
            opt["quantity"] = new_qty
            
            # Premium override select
            new_prem = cols[4].number_input(
                "Premium", min_value=0.0, max_value=10000.0,
                value=float(opt["premium"]),
                step=0.01,
                format="%.2f",
                key=f"prem_{idx}",
                label_visibility="collapsed"
            )
            opt["premium"] = new_prem
            
            # Delete button
            if cols[5].button("삭제", key=f"del_{idx}", use_container_width=True):
                to_delete.append(idx)
                
        if to_delete:
            for idx in sorted(to_delete, reverse=True):
                st.session_state.basket.pop(idx)
            st.rerun()
            
        # Action Buttons
        btn_col1, btn_col2, btn_col3 = st.columns([1.5, 1.5, 5])
        if btn_col1.button("🔄 실시간 시세 갱신", type="primary", use_container_width=True):
            update_basket_prices()
            st.success("실시간 시세를 불러왔습니다!")
            st.rerun()
            
        if btn_col2.button("🗑️ 바스켓 초기화", type="secondary", use_container_width=True):
            st.session_state.basket = []
            st.session_state.underlying_price = None
            st.session_state.underlying_info = None
            st.rerun()
            
        st.markdown("---")
        
        # 🎯 분석 목표 주가 및 DTE 시뮬레이션 제어판 (가로 2열 배치)
        if st.session_state.underlying_price is not None:
            min_strike = st.session_state.underlying_price * 0.7
            max_strike = st.session_state.underlying_price * 1.3
            if st.session_state.basket:
                strikes_basket = [o["strike"] for o in st.session_state.basket]
                min_strike = min(min_strike, min(strikes_basket) * 0.8)
                max_strike = max(max_strike, max(strikes_basket) * 1.2)
                
            if 'target_slider' not in st.session_state:
                st.session_state.target_slider = float(st.session_state.underlying_price)
            if 'target_num' not in st.session_state:
                st.session_state.target_num = float(st.session_state.underlying_price)
                
            # Clip if out of bounds due to underlying price changes
            if st.session_state.target_slider < float(min_strike) or st.session_state.target_slider > float(max_strike):
                st.session_state.target_slider = float(st.session_state.underlying_price)
            if st.session_state.target_num < float(min_strike) or st.session_state.target_num > float(max_strike):
                st.session_state.target_num = float(st.session_state.underlying_price)
                
            # Draw simulation settings in columns above the chart
            st.markdown("<h4 style='font-family: Outfit; margin-top: 15px; margin-bottom: 5px;'>⚙️ 수익곡선 상세 시뮬레이션 제어</h4>", unsafe_allow_html=True)
            col_sim1, col_sim2 = st.columns(2)
            
            with col_sim1:
                st.markdown("**⏱️ 잔존만기 일수 (DTE)**")
                st.slider("DTE 슬라이더", min_value=0, max_value=int(max_dte), key="dte_slider", on_change=sync_widgets, args=("dte_slider", "dte_num"), label_visibility="collapsed")
                days_to_expiry_val = st.number_input("DTE 정밀 입력 (일)", min_value=0, max_value=int(max_dte), step=1, key="dte_num", on_change=sync_widgets, args=("dte_num", "dte_slider"), label_visibility="collapsed")
                
            with col_sim2:
                st.markdown("**🎯 분석 목표 주가 ($)**")
                st.slider("목표주가 슬라이더", min_value=float(min_strike), max_value=float(max_strike), key="target_slider", on_change=sync_widgets, args=("target_slider", "target_num"), label_visibility="collapsed")
                target_underlying_val = st.number_input("목표주가 정밀 입력 ($)", min_value=float(min_strike), max_value=float(max_strike), step=0.01, key="target_num", on_change=sync_widgets, args=("target_num", "target_slider"), label_visibility="collapsed")
        else:
            target_underlying_val = None
            days_to_expiry_val = int(max_dte)
            
        # Calculate IV for each option to simulate pre-expiration payoff and statistical bands
        if st.session_state.underlying_price is not None:
            recalculate_ivs(rate_val)
            
        # Payoff plot calculations
        strikes = [opt["strike"] for opt in st.session_state.basket]
        
        # Calculate 95% Confidence Interval based on average IV
        avg_iv = 0.30
        valid_ivs = [opt.get("iv", 0.30) for opt in st.session_state.basket if opt.get("iv", 0.0) > 0.0]
        if valid_ivs:
            avg_iv = sum(valid_ivs) / len(valid_ivs)
            
        max_dte = max(opt.get("remn_cnt", 30) for opt in st.session_state.basket)
        t_annual = max_dte / 365.0
        
        import math
        std_dev = avg_iv * math.sqrt(t_annual)
        
        S_current = st.session_state.underlying_price if st.session_state.underlying_price is not None else strikes[0]
        
        ci_lower = S_current * math.exp(-1.96 * std_dev)
        ci_upper = S_current * math.exp(1.96 * std_dev)
        
        strike_lower = min(strikes) * 0.95
        strike_upper = max(strikes) * 1.05
        
        # Final hybrid min/max
        x_min = min(ci_lower, strike_lower, S_current * 0.9)
        x_max = max(ci_upper, strike_upper, S_current * 1.1)
        
        underlying_prices = [x_min + (x_max - x_min) * i / 149 for i in range(150)]
        
        combined_payoffs = []
        combined_payoffs_pre = []
            
        for s in underlying_prices:
            total_profit = 0.0
            total_profit_pre = 0.0
            for opt in st.session_state.basket:
                k = opt["strike"]
                prem = opt["premium"]
                qty = opt["quantity"]
                act = opt["action"]
                opt_type = opt["type"]
                
                # 1. Expiration payoff
                if opt_type == "Call" or opt_type.upper() == "C":
                    indiv_profit = max(s - k, 0.0) - prem
                else:
                    indiv_profit = max(k - s, 0.0) - prem
                    
                if act == "Short":
                    indiv_profit = -indiv_profit
                total_profit += indiv_profit * qty * 100 # Multiplied by 100 multiplier for US Options
                
                # 2. Pre-expiration payoff
                if st.session_state.underlying_price is not None:
                    t_target = min(days_to_expiry_val, opt["remn_cnt"]) / 365.0
                    iv = opt.get("iv", 0.30)
                    sigma_target = max(iv + vol_change_val, 0.0001)
                    expected_val = black_scholes(s, k, t_target, rate_val, sigma_target, opt_type)
                    
                    if act == "Long":
                        indiv_profit_pre = expected_val - prem
                    else:
                        indiv_profit_pre = prem - expected_val
                    total_profit_pre += indiv_profit_pre * qty * 100
                    
            combined_payoffs.append(total_profit)
            if st.session_state.underlying_price is not None:
                combined_payoffs_pre.append(total_profit_pre)
                
        # Draw Plotly graph
        fig = go.Figure()
        
        # Horizontal 0 line (Profit/Loss boundary) - Cool slate-gray dashed line
        fig.add_shape(
            type="line",
            x0=x_min, y0=0, x1=x_max, y1=0,
            line=dict(color="rgb(1, 2, 3)", width=1.5, dash="solid")
        )
        
        # Strike vertical lines - Using trigger color for dynamic CSS theme-adaptive styling
        # for opt in st.session_state.basket:
        #     fig.add_shape(
        #         type="line",
        #         x0=opt["strike"], 
        #         x1=opt["strike"], 
        #         y0=0,             # 차트 맨 바닥
        #         y1=1,             # 차트 맨 꼭대기
        #         yref="paper",     # Y축 기준을 데이터 값이 아닌 차트 도화지(paper) 비율로 설정
        #         line=dict(color="rgb(1, 2, 3)", width=1.5, dash="dot")
        #     )
        # for opt in st.session_state.basket:
        #     fig.add_vline(
        #         x=opt["strike"],
        #         # CSS 가로채기를 위해 rgb(1,2,3) 유지 및 두께는 1로 설정 (CSS에서 최종 제어)
        #         line=dict(color="rgb(1, 2, 3)", width=1.0, dash="dot"),
                
        #         # 🌟 Annotation(텍스트 라벨) 설정
        #         annotation_text=f" 행사가 ${opt['strike']:.2f}",
        #         annotation_position="top right", # 선 우측 상단에 글자 배치
                
        #         # 글자 색상도 CSS에서 동적으로 가로챌 수 있도록 고유한 trigger color 주입
        #         annotation_font=dict(color="rgb(1, 2, 3)", size=10, family="Inter")
        #     )
        
        # Strike vertical lines - 선과 Annotation을 분리하여 겹침 방지 (계단식 높이 조절)
        for idx, opt in enumerate(st.session_state.basket):
            # 1. 세로선 그리기
            fig.add_vline(
                x=opt["strike"],
                line=dict(color="rgb(1, 2, 3)", width=1.0, dash="dot")
            )
            
            # 2. 겹치지 않는 Annotation 따로 추가하기
            # 순번에 따라 5%씩 높이를 떨어뜨려 글자가 겹치지 않고 계단식으로 정렬됩니다.
            dynamic_y = 1.0 - (idx * 0.05) 
            
            fig.add_annotation(
                x=opt["strike"],            # X축은 행사가격 위치 고정
                y=dynamic_y,                # Y축은 순번에 따라 다이내믹하게 조절
                yref="paper",               # 차트 꼭대기(1.0) 기준 비율로 Y축 설정
                
                text=f" 행사가 ${opt['strike']:.2f} ({opt['type']})",
                showarrow=False,            # 화살표는 숨김
                xanchor="right",             # 선의 오른쪽에 글자 시작점 정렬
                yanchor="top",
                
                # CSS 가로채기를 위해 글자 색상에 동일한 rgb(1,2,3) 주입
                font=dict(color="rgb(1, 2, 3)", size=10, family="Inter")
            )


        # Expiry BEPs
        beps_exp = find_beps(underlying_prices, combined_payoffs)
        for idx, bep in enumerate(beps_exp):
            fig.add_vline(
                x=bep,
                line=dict(color="#FFA726", width=1.5, dash="dot"),
                annotation_text=f" 만기 BEP (${bep:.2f})",
                annotation_position="bottom left",
                annotation_font=dict(color="#FFA726", size=10)
            )
            
        # Current Price vertical line
        if st.session_state.underlying_price is not None:
            fig.add_vline(
                x=st.session_state.underlying_price,
                line=dict(color="#00E676", width=1.5, dash="dash"),
                annotation_text=f" 현재가 (${st.session_state.underlying_price:.2f})",
                annotation_position="top left",
                annotation_font=dict(color="#00E676")
            )
            
        # Draw Expiration and Pre-expiration curves with unified hover snapping to Pre-expiration
        if combined_payoffs_pre:
            # Expiration curve will ignore direct hover triggers to prevent drawing spikes to it
            fig.add_trace(go.Scatter(
                x=underlying_prices,
                y=combined_payoffs,
                mode='lines',
                name='만기 시 손익 (Expiration)',
                line=dict(color='#7F8C8D', width=2.8),
                hoverinfo="skip"
            ))
            
            # Pre-expiration curve embeds Expiration data in customdata to show both in its tooltip
            custom_data = [[p] for p in combined_payoffs]
            fig.add_trace(go.Scatter(
                x=underlying_prices,
                y=combined_payoffs_pre,
                mode='lines',
                name=f'만기 전 예상 손익 (D-{days_to_expiry_val}일)',
                line=dict(color='#0072FF', width=2.2),
                customdata=custom_data,
                hovertemplate="예상: %{y:$.2f}<br>만기: %{customdata[0]:$.2f}<extra></extra>"
            ))
        else:
            # Fallback if pre-expiration data is not calculated
            fig.add_trace(go.Scatter(
                x=underlying_prices,
                y=combined_payoffs,
                mode='lines',
                name='만기 시 손익 (Expiration)',
                line=dict(color='#7F8C8D', width=2.8)
            ))
            
        fig.update_layout(
            template="streamlit",  # $$$ Streamlit의 현재 테마(화이트/다크)를 Plotly에 동기화
            title=dict(
                text="📊 포트폴리오 합성 손익 곡선 (Interactive Chart)",
                font=dict(family="Outfit", size=18)
            ),
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(0, 0, 0, 0)",
            legend=dict(
                font=dict(size=11),
                bgcolor="rgba(0, 0, 0, 0)"
            ),
            margin=dict(l=40, r=40, t=50, b=40),
            xaxis=dict(
                title=dict(text="기초자산 가격 ($)"),
                tickfont=dict(size=11),
                showgrid=True,
                zeroline=False,
                showspikes=True,
                spikethickness=1.5,
                spikedash="dot",
                spikecolor="#0072FF",  # Matching vibrant royal blue
                spikemode="toaxis+across"
            ),
            yaxis=dict(
                title=dict(text="합성 손익 ($)"),
                tickfont=dict(size=11),
                showgrid=True,
                zeroline=False,
                showspikes=True,
                spikethickness=1.5,
                spikedash="dot",
                spikecolor="#0072FF",  # Matching vibrant royal blue
                spikemode="toaxis+across",
                fixedrange=True
            ),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="rgba(33, 33, 33, 0.85)",
                font_size=11,
                font_family="Inter, sans-serif",
                font_color="#FFFFFF",
                bordercolor="rgba(150, 150, 150, 0.3)"
            )
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
        
        # Scenario analysis details
        if target_underlying_val is not None and st.session_state.underlying_price is not None:
            st.markdown("---")
            st.subheader(f"🎯 목표 주가 ${target_underlying_val:.2f} 시나리오 분석 (만기 {days_to_expiry_val}일 전)")
            
            analysis_data = []
            total_exp_profit = 0.0
            
            for opt in st.session_state.basket:
                k = opt["strike"]
                prem = opt["premium"]
                qty = opt["quantity"]
                act = opt["action"]
                opt_type = opt["type"]
                
                t_target = min(days_to_expiry_val, opt["remn_cnt"]) / 365.0
                iv = opt.get("iv", 0.30)
                sigma_target = max(iv + vol_change_val, 0.0001)
                expected_val = black_scholes(target_underlying_val, k, t_target, rate_val, sigma_target, opt_type)
                
                if act == "Long":
                    indiv_profit_pre = expected_val - prem
                else:
                    indiv_profit_pre = prem - expected_val
                    
                opt_profit = indiv_profit_pre * qty * 100
                total_exp_profit += opt_profit
                
                analysis_data.append({
                    "옵션 코드": opt["symbol"],
                    "포지션": "매수 (Long)" if act == "Long" else "매도 (Short)",
                    "행사가": f"${k:.2f}",
                    "현재가 (Premium)": f"${prem:.2f}",
                    "예상 옵션가": f"${expected_val:.2f}",
                    "계약당 손익": f"${indiv_profit_pre:+.2f}",
                    "수량": f"{qty} 계약",
                    "총 예상 손익": f"${opt_profit:+.2f}"
                })
                
            df_analysis = pd.DataFrame(analysis_data)
            st.dataframe(df_analysis, width="stretch")
            
            # Show summary
            profit_color = "#00E676" if total_exp_profit >= 0 else "#FF1744"
            st.markdown(f"""
            <div class="custom-card" style="text-align: center;">
                <h4 style="margin: 0; color: #8888aa; font-family: Outfit;">포트폴리오 총 예상 손익 시나리오</h4>
                <h2 style="margin: 10px 0 0 0; color: {profit_color}; font-family: Outfit; font-weight: 800; font-size: 2.5rem;">
                    ${total_exp_profit:+.2f}
                </h2>
            </div>
            """, unsafe_allow_html=True)

# ==================== Tab 2: Search & Add Options ====================
with tab2:
    st.subheader("🔍 미국주식옵션 검색")
    
    col_search1, col_search2 = st.columns([4, 1])
    search_ticker = col_search1.text_input(
        "기초자산 Ticker 입력 (예: AAPL, PG, TSLA, NVDA)",
        value="AAPL",
        key="search_ticker_input"
    ).upper().strip()
    
    # Store ticker in session state
    if 'last_search_ticker' not in st.session_state:
        st.session_state.last_search_ticker = ""
        
    search_clicked = col_search2.button("종목 검색", type="primary", use_container_width=True)
    
    if search_clicked or st.session_state.last_search_ticker != search_ticker:
        with st.spinner("옵션 목록 및 현재가 로딩 중..."):
            st.session_state.last_search_ticker = search_ticker
            st.session_state.options_list = get_option_chain(search_ticker)
            st.session_state.queried_real_prices = {} # Reset real prices cache
            
            # Fetch underlying stock price for the searched ticker
            if st.session_state.options_list:
                token = fetch_token()
                first_opt = st.session_state.options_list[0]
                underlying_info = get_underlying_info(first_opt["symbol"])
                if underlying_info and token:
                    st.session_state.underlying_info = underlying_info
                    try:
                        stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                        if stock_res and stock_res.get("rt_cd") == "0":
                            st.session_state.underlying_price = float(stock_res["output"]["last"])
                    except Exception:
                        pass
            else:
                st.session_state.underlying_price = None
                st.session_state.underlying_info = None
            
    if 'options_list' in st.session_state and st.session_state.options_list:
        options = st.session_state.options_list
        
        # Display underlying price in Tab 2 as a styled badge matching the image reference
        if st.session_state.underlying_price is not None and st.session_state.underlying_info is not None and st.session_state.underlying_info.get("ticker") == search_ticker:
            st.markdown(f"""
            <div style="display: inline-block; border: 1.5px solid #FF1744; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 23, 68, 0.08); color: #FF1744; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 10px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 23, 68, 0.15);">
                📊 {search_ticker} 현재가: ${st.session_state.underlying_price:.2f}
            </div>
            """, unsafe_allow_html=True)
            
        st.success(f"'{search_ticker}' 기초자산에 해당하는 미국옵션 {len(options)}개를 마스터 파일에서 불러왔습니다.")
        
        # Define expiry date formatter with D-day
        import datetime
        def format_expiry(date_str):
            if date_str == "Unknown":
                return "Unknown"
            try:
                exp_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.date.today()
                d_day = (exp_date - today).days
                return f"{date_str} (D-{d_day})"
            except Exception:
                return date_str

        unique_expiries = sorted(list(set(opt["expiry_date"] for opt in options)))
        
        st.markdown("<div class='custom-card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin-top:0; font-family: Outfit;'>➕ 포트폴리오에 옵션 추가 (인터랙티브 옵션 그리드)</h4>", unsafe_allow_html=True)
        
        # 1. Select Expiry, Sorting, Position, and Quantity (Top configuration area)
        col_cfg1, col_cfg2, col_cfg3, col_cfg4 = st.columns([1.5, 1.5, 1.2, 0.8])
        sel_expiry = col_cfg1.selectbox("📅 만기일 선택 (Expiry Date)", unique_expiries, format_func=format_expiry)
        sort_method = col_cfg2.selectbox("📊 행사가 정렬 방식", ["행사가격 오름차순", "현재가에 가까운 순 (ATM 우선)"])
        sel_action = col_cfg3.selectbox("➡️ 일괄 포지션 설정", ["Long (매수)", "Short (매도)"], key="batch_pos")
        sel_qty = col_cfg4.number_input("🔢 일괄 수량 설정", min_value=1, max_value=1000, value=1, key="batch_qty")
        
        # 2. Hybrid Strike Filter (Preset for Mobile, Text for Desktop)
        col_filter1, col_filter2 = st.columns([1.5, 2.5])
        filter_preset = col_filter1.selectbox(
            "🔍 행사가 필터 방식",
            ["ATM ± 10 행사가", "ATM ± 5 행사가", "ATM ± 20 행사가", "전체 보기", "직접 입력 (고급)"],
            index=0,
            key="strike_filter_preset"
        )
        
        strike_filter_input = ""
        if filter_preset == "직접 입력 (고급)":
            strike_filter_input = col_filter2.text_input(
                "📝 필터식 입력 (예: 170-185, >175, 170,180)",
                value="",
                key="strike_filter_text"
            ).strip()
        else:
            col_filter2.markdown("<div style='padding-top:25px; color:#8888aa; font-size:0.9rem;'>💡 모바일 터치 환경에서는 간편 프리셋 조작을 권장합니다.</div>", unsafe_allow_html=True)
        
        # Filter options for the selected expiry
        filtered_opts = [opt for opt in options if opt["expiry_date"] == sel_expiry]
        
        # Find ATM strike
        spot = st.session_state.underlying_price
        closest_strike = None
        if spot and filtered_opts:
            all_strikes = [opt["strike"] for opt in filtered_opts]
            closest_strike = min(all_strikes, key=lambda k: abs(k - spot))
            
        # Group filtered options by strike (T-shape Call/Strike/Put layout)
        strike_map = {}
        for opt in filtered_opts:
            strike = opt["strike"]
            if strike not in strike_map:
                strike_map[strike] = {"Call": None, "Put": None}
            strike_map[strike][opt["type"]] = opt
            
        # Sort strikes based on chosen sort method
        sorted_strikes = list(strike_map.keys())
        if sort_method == "현재가에 가까운 순 (ATM 우선)":
            if spot:
                sorted_strikes = sorted(sorted_strikes, key=lambda k: abs(k - spot))
        else:
            sorted_strikes = sorted(sorted_strikes)
            
        # Apply Hybrid Strike Filter (Presets vs Custom text input)
        if filter_preset == "전체 보기":
            pass # Keep all strikes
        elif filter_preset in ["ATM ± 5 행사가", "ATM ± 10 행사가", "ATM ± 20 행사가"]:
            window_map = {
                "ATM ± 5 행사가": 5,
                "ATM ± 10 행사가": 10,
                "ATM ± 20 행사가": 20
            }
            half_window = window_map[filter_preset]
            if spot and closest_strike and closest_strike in sorted_strikes:
                if sort_method == "현재가에 가까운 순 (ATM 우선)":
                    # In distance-sorted list, closest options are at the beginning
                    total_count = half_window * 2 + 1
                    sorted_strikes = sorted_strikes[:total_count]
                else:
                    # In ascending-sorted list, slice centered around closest strike
                    try:
                        closest_idx = sorted_strikes.index(closest_strike)
                        start_idx = max(0, closest_idx - half_window)
                        end_idx = min(len(sorted_strikes), closest_idx + half_window + 1)
                        sorted_strikes = sorted_strikes[start_idx:end_idx]
                    except Exception:
                        pass
        elif filter_preset == "직접 입력 (고급)" and strike_filter_input:
            try:
                # 1. Inequality operators
                if strike_filter_input.startswith(">="):
                    val = float(strike_filter_input[2:].strip())
                    sorted_strikes = [s for s in sorted_strikes if s >= val]
                elif strike_filter_input.startswith("<="):
                    val = float(strike_filter_input[2:].strip())
                    sorted_strikes = [s for s in sorted_strikes if s <= val]
                elif strike_filter_input.startswith(">"):
                    val = float(strike_filter_input[1:].strip())
                    sorted_strikes = [s for s in sorted_strikes if s > val]
                elif strike_filter_input.startswith("<"):
                    val = float(strike_filter_input[1:].strip())
                    sorted_strikes = [s for s in sorted_strikes if s < val]
                # 2. Ranges (using '~' or '-')
                elif "~" in strike_filter_input or ("-" in strike_filter_input and not strike_filter_input.startswith("-")):
                    delimiter = "~" if "~" in strike_filter_input else "-"
                    parts = strike_filter_input.split(delimiter)
                    if len(parts) == 2:
                        left_str, right_str = parts[0].strip(), parts[1].strip()
                        min_val = float(left_str) if left_str else 0.0
                        max_val = float(right_str) if right_str else float('inf')
                        sorted_strikes = [s for s in sorted_strikes if min_val <= s <= max_val]
                # 3. Comma-separated list (fallback)
                else:
                    filter_vals = [float(v.strip()) for v in strike_filter_input.split(",") if v.strip()]
                    if filter_vals:
                        sorted_strikes = [s for s in sorted_strikes if any(abs(s - f) < 0.01 for f in filter_vals)]
            except ValueError:
                st.caption("⚠️ 올바른 필터 형식을 입력해 주세요. (예: '170-180', '>175', '170, 180')")
            
        # Prepare DataFrame rows for T-shape option chain grid
        grid_data = []
        today = datetime.date.today()
        for strike in sorted_strikes:
            call_opt = strike_map[strike]["Call"]
            put_opt = strike_map[strike]["Put"]
            
            is_atm = " (ATM)" if closest_strike and strike == closest_strike else ""
            
            # Expiry DTE for pricing
            try:
                exp_dt = datetime.datetime.strptime(sel_expiry, "%Y-%m-%d").date()
                remn_cnt = max(0, (exp_dt - today).days)
            except Exception:
                remn_cnt = 30
            t_annual = max(1, remn_cnt) / 365.0
            
            # Call Price calculation
            call_price_str = "N/A"
            call_symbol = ""
            call_expiry_code = ""
            if call_opt:
                call_symbol = call_opt["symbol"]
                call_expiry_code = call_opt["expiry"]
                if 'queried_real_prices' in st.session_state and call_symbol in st.session_state.queried_real_prices:
                    real_price = st.session_state.queried_real_prices[call_symbol]
                    call_price_str = f"${real_price:.2f} (실시간)"
                elif spot and spot > 0:
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, 0.30, "Call")
                    call_price_str = f"${bs_price:.2f}"
                    
            # Put Price calculation
            put_price_str = "N/A"
            put_symbol = ""
            put_expiry_code = ""
            if put_opt:
                put_symbol = put_opt["symbol"]
                put_expiry_code = put_opt["expiry"]
                if 'queried_real_prices' in st.session_state and put_symbol in st.session_state.queried_real_prices:
                    real_price = st.session_state.queried_real_prices[put_symbol]
                    put_price_str = f"${real_price:.2f} (실시간)"
                elif spot and spot > 0:
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, 0.30, "Put")
                    put_price_str = f"${bs_price:.2f}"
                    
            grid_data.append({
                "선택 (Call)": False,
                "Call 가격 (이론가)": call_price_str,
                "행사가격 (Strike)": f"${strike:.2f}{is_atm}",
                "Put 가격 (이론가)": put_price_str,
                "선택 (Put)": False,
                "call_symbol": call_symbol,
                "put_symbol": put_symbol,
                "raw_strike": strike,
                "call_expiry_code": call_expiry_code,
                "put_expiry_code": put_expiry_code
            })
            
        df_grid = pd.DataFrame(grid_data)
        
        # Display st.data_editor
        if not df_grid.empty:
            st.write("👉 추가할 옵션들을 **'선택 (Call)'** 또는 **'선택 (Put)'** 컬럼에 체크해 주세요.")
            
            edited_df = st.data_editor(
                df_grid,
                column_config={
                    "선택 (Call)": st.column_config.CheckboxColumn(default=False),
                    "Call 가격 (이론가)": st.column_config.TextColumn(disabled=True),
                    "행사가격 (Strike)": st.column_config.TextColumn(disabled=True),
                    "Put 가격 (이론가)": st.column_config.TextColumn(disabled=True),
                    "선택 (Put)": st.column_config.CheckboxColumn(default=False),
                    "call_symbol": None, # Hide completely
                    "put_symbol": None,  # Hide completely
                    "raw_strike": None,  # Hide completely
                    "call_expiry_code": None,
                    "put_expiry_code": None
                },
                disabled=["Call 가격 (이론가)", "행사가격 (Strike)", "Put 가격 (이론가)"],
                width="stretch",
                hide_index=True,
                height=500,
                key=f"option_editor_grid_{sel_expiry}" # Unique key per expiry to refresh state
            )
            
            # Define controls for action execution (Actions at bottom, settings at top)
            col_btn1, col_btn2 = st.columns(2)
            
            # Action 1: Query Real Price for selected options
            if col_btn2.button("🔍 선택 종목 실시간 시세 조회", use_container_width=True):
                selected_calls = edited_df[edited_df["선택 (Call)"] == True]
                selected_puts = edited_df[edited_df["선택 (Put)"] == True]
                
                # Gather all selected option symbols
                symbols_to_query = []
                for _, row in selected_calls.iterrows():
                    if row["call_symbol"]:
                        symbols_to_query.append(row["call_symbol"])
                for _, row in selected_puts.iterrows():
                    if row["put_symbol"]:
                        symbols_to_query.append(row["put_symbol"])
                        
                if not symbols_to_query:
                    st.warning("먼저 시세를 조회할 옵션(Call 또는 Put)의 '선택' 체크박스를 체크해 주세요.")
                else:
                    with st.spinner("선택한 옵션들의 실시간 현재가를 조회하는 중..."):
                        for sym in symbols_to_query:
                            real_prem, _ = get_single_option_premium(sym)
                            if 'queried_real_prices' not in st.session_state:
                                st.session_state.queried_real_prices = {}
                            st.session_state.queried_real_prices[sym] = real_prem
                    st.success("실시간 시세 조회가 완료되었습니다! 표에 '(실)'로 반영됩니다.")
                    st.rerun()
            
            # Action 2: Add selected options to basket
            if col_btn1.button("🛒 선택한 옵션들을 바스켓에 일괄 추가", type="primary", use_container_width=True):
                selected_calls = edited_df[edited_df["선택 (Call)"] == True]
                selected_puts = edited_df[edited_df["선택 (Put)"] == True]
                
                if selected_calls.empty and selected_puts.empty:
                    st.warning("선택된 옵션이 없습니다. 추가할 옵션의 '선택 (Call)' 또는 '선택 (Put)'을 체크해 주세요.")
                else:
                    success_symbols = []
                    with st.spinner("시세 정보를 조회하고 포트폴리오에 추가하는 중..."):
                        # Ensure underlying price is loaded
                        if st.session_state.underlying_price is None:
                            token = fetch_token()
                            first_symbol = None
                            for _, row in selected_calls.iterrows():
                                if row["call_symbol"]:
                                    first_symbol = row["call_symbol"]
                                    break
                            if not first_symbol:
                                for _, row in selected_puts.iterrows():
                                    if row["put_symbol"]:
                                        first_symbol = row["put_symbol"]
                                        break
                                        
                            if first_symbol:
                                underlying_info = get_underlying_info(first_symbol)
                                if underlying_info and token:
                                    st.session_state.underlying_info = underlying_info
                                    stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                                    if stock_res and stock_res.get("rt_cd") == "0":
                                        st.session_state.underlying_price = float(stock_res["output"]["last"])
                                        
                        # Helper for adding option
                        def add_option(sym, opt_type, opt_strike, opt_expiry_code):
                            action = "Long" if "Long" in sel_action else "Short"
                            qty = int(sel_qty)
                            duplicate = False
                            for item in st.session_state.basket:
                                if item["symbol"] == sym:
                                    item["action"] = action
                                    item["quantity"] = qty
                                    duplicate = True
                                    success_symbols.append(f"{sym} (업데이트)")
                                    break
                            if not duplicate:
                                if 'queried_real_prices' in st.session_state and sym in st.session_state.queried_real_prices:
                                    premium = st.session_state.queried_real_prices[sym]
                                    try:
                                        exp_dt = datetime.datetime.strptime(sel_expiry, "%Y-%m-%d").date()
                                        remn_cnt = max(0, (exp_dt - datetime.date.today()).days)
                                    except Exception:
                                        remn_cnt = 30
                                else:
                                    premium, remn_cnt = get_single_option_premium(sym)
                                    
                                st.session_state.basket.append({
                                    "symbol": sym,
                                    "ticker": search_ticker,
                                    "type": opt_type,
                                    "strike": opt_strike,
                                    "expiry": opt_expiry_code,
                                    "expiry_date": sel_expiry,
                                    "action": action,
                                    "quantity": qty,
                                    "premium": premium,
                                    "remn_cnt": remn_cnt
                                })
                                success_symbols.append(sym)
                                
                        # Process checked Call options
                        for _, row in selected_calls.iterrows():
                            if row["call_symbol"]:
                                add_option(row["call_symbol"], "Call", float(row["raw_strike"]), row["call_expiry_code"])
                                
                        # Process checked Put options
                        for _, row in selected_puts.iterrows():
                            if row["put_symbol"]:
                                add_option(row["put_symbol"], "Put", float(row["raw_strike"]), row["put_expiry_code"])
                                
                    st.success(f"성공적으로 바스켓에 추가/업데이트 되었습니다: {', '.join(success_symbols)}")
                    st.rerun()
        else:
            st.warning("해당 만기일에 상장된 옵션 계약이 없습니다.")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
    elif 'options_list' in st.session_state:
        st.warning(f"기초자산 '{search_ticker}'에 매칭되는 미국옵션 리스트가 마스터 파일에 없습니다. 대문자 티커를 확인하십시오.")
