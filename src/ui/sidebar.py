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
    else:
        if st.sidebar.button("🔄 실시간 시세 동기화 (Refresh)", use_container_width=True):
            if st.session_state.basket:
                with st.sidebar.spinner("실시간 시세 동기화 중..."):
                    update_basket_prices()
                    current_rate = st.session_state.get("rate_num", 4.0) / 100.0
                    recalculate_ivs(current_rate)
                st.sidebar.success("시세 동기화 완료!")
                st.rerun()
            else:
                st.sidebar.info("바스켓에 등록된 옵션이 없습니다.")

    max_dte = 30
    if st.session_state.basket:
        max_dte = max(opt.get("remn_cnt", 30) for opt in st.session_state.basket)

    if "dte_slider" not in st.session_state:
        st.session_state.dte_slider = int(max_dte)
    if "dte_num" not in st.session_state:
        st.session_state.dte_num = int(max_dte)

    if "vol_slider" not in st.session_state:
        st.session_state.vol_slider = 0.0
    if "vol_num" not in st.session_state:
        st.session_state.vol_num = 0.0

    if "rate_slider" not in st.session_state:
        st.session_state.rate_slider = 4.0
    if "rate_num" not in st.session_state:
        st.session_state.rate_num = 4.0

    if st.session_state.dte_slider > int(max_dte):
        st.session_state.dte_slider = int(max_dte)
    if st.session_state.dte_num > int(max_dte):
        st.session_state.dte_num = int(max_dte)

    st.sidebar.write("### 🎛️ 시뮬레이션 파라미터")

    st.sidebar.write("**⚡ 내재변동성(IV) 변화율 (%p)**")
    st.sidebar.slider("IV 슬라이더", min_value=-50.0, max_value=50.0, key="vol_slider", on_change=sync_widgets, args=("vol_slider", "vol_num"), label_visibility="collapsed")
    vol_input_val = st.sidebar.number_input("IV 정밀 입력 (%p)", min_value=-50.0, max_value=50.0, step=0.1, key="vol_num", on_change=sync_widgets, args=("vol_num", "vol_slider"), label_visibility="collapsed")
    vol_change_val = vol_input_val / 100.0

    st.sidebar.write("**💵 무위험 이자율 (%)**")
    st.sidebar.slider("이자율 슬라이더", min_value=0.0, max_value=10.0, key="rate_slider", on_change=sync_widgets, args=("rate_slider", "rate_num"), label_visibility="collapsed")
    rate_input_val = st.sidebar.number_input("이자율 정밀 입력 (%)", min_value=0.0, max_value=10.0, step=0.01, key="rate_num", on_change=sync_widgets, args=("rate_num", "rate_slider"), label_visibility="collapsed")
    rate_val = rate_input_val / 100.0

    st.sidebar.markdown("---")
    st.sidebar.info("💡 **팁**: 대화형 Plotly 그래프 위에 마우스를 올리면 각 지점의 구체적인 만기 손익과 만기 전 예상 손익 정보를 툴팁으로 확인할 수 있습니다.")

    return vol_change_val, rate_val
