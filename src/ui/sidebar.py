import os
import streamlit as st

from src import config
from src.ui.ui_helpers import (
    check_api_keys,
    recalculate_ivs,
    sync_widgets,
    update_basket_prices,
)


def render_sidebar():
    st.sidebar.markdown("<h2 style='font-family: Outfit; font-weight: 700; margin-bottom: 15px;'>⚙️ 설정 & 시뮬레이터</h2>", unsafe_allow_html=True)

    if st.session_state.get("master_status") == "loading":
        st.sidebar.info("옵션 마스터 데이터를 백그라운드에서 불러오는 중입니다. 화면은 바로 열립니다.")
    elif not os.path.exists(config.MASTER_FILE):
        st.sidebar.warning("옵션 마스터 데이터가 없어 일부 옵션 검색 기능이 제한될 수 있습니다.")

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

    if "default_risk_free_rate" not in st.session_state:
        # 최초 앱 구동 시 딱 한 번만 미국 3개월 국채 금리(^IRX) 실시간 조회 및 캐싱 (Rerun 성능 확보)
        try:
            import yfinance as yf
            irx = yf.Ticker("^IRX")
            hist = irx.history(period="1d")
            if not hist.empty:
                st.session_state.default_risk_free_rate = float(hist["Close"].iloc[-1])
            else:
                st.session_state.default_risk_free_rate = 4.0
        except Exception:
            st.session_state.default_risk_free_rate = 4.0

    default_rate = st.session_state.default_risk_free_rate

    if "rate_slider" not in st.session_state:
        st.session_state.rate_slider = default_rate
    if "rate_num" not in st.session_state:
        st.session_state.rate_num = default_rate

    st.sidebar.write("### 🎛️ 글로벌 설정")
    
    st.sidebar.write("**💵 무위험 이자율 (%)**")
    st.sidebar.slider("이자율 슬라이더", min_value=0.0, max_value=10.0, key="rate_slider", on_change=sync_widgets, args=("rate_slider", "rate_num"), label_visibility="collapsed")
    rate_input_val = st.sidebar.number_input("이자율 정밀 입력 (%)", min_value=0.0, max_value=10.0, step=0.01, key="rate_num", on_change=sync_widgets, args=("rate_num", "rate_slider"), label_visibility="collapsed")
    rate_val = rate_input_val / 100.0
    return rate_val
