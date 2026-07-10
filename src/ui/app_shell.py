import streamlit as st

from src import config
from src.ui.analysis_tab import render_analysis_chart_and_summary, render_basket_overview, render_simulation_controls
from src.ui.search_tab import render_search_tab as render_search_tab_ui
from src.ui.sidebar import render_sidebar
from src.ui.ui_helpers import ensure_master_file_ready, initialize_session_state
from src.ui.ui_styles import inject_app_styles, render_app_header


def configure_app() -> None:
    config.load_settings(secrets=getattr(st, "secrets", None))
    st.set_page_config(
        page_title="미국주식옵션 시뮬레이터",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_app_styles()
    initialize_session_state()
    ensure_master_file_ready()


def render_analysis_tab(rate_val) -> None:
    filtered_basket = render_basket_overview()
    if not filtered_basket:
        return

    max_dte = 30
    max_dte = max(opt.get("remn_cnt", 30) for opt in filtered_basket)

    days_to_expiry_val, target_underlying_val, vol_change_val = render_simulation_controls(
        filtered_basket,
        max_dte,
        rate_val,
    )
    render_analysis_chart_and_summary(filtered_basket, vol_change_val, rate_val, days_to_expiry_val, target_underlying_val)


def render_search_tab(rate_val) -> None:
    render_search_tab_ui(rate_val)


def render_app() -> None:
    configure_app()

    rate_val = render_sidebar()
    render_app_header()

    tab2, tab1 = st.tabs(["🔍 종목 검색 & 추가", "📊 포트폴리오 분석 & 시뮬레이션"])

    with tab1:
        render_analysis_tab(rate_val)

    with tab2:
        render_search_tab(rate_val)
