import math
import pandas as pd
import streamlit as st

from src.chart import render_portfolio_payoff_chart
from src.pricing import black_scholes
from src.ui.ui_helpers import recalculate_ivs, sync_widgets, update_basket_prices


def render_basket_overview():
    if not st.session_state.basket:
        st.info("🧺 바스켓이 비어 있습니다. **'종목 검색 & 추가'** 탭에서 옵션을 검색하여 추가해 주세요.")
        return False

    st.write("### 🧺 현재 포트폴리오 바스켓")

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

        new_action = cols[2].selectbox(
            "포지션",
            ["Long", "Short"],
            index=0 if opt["action"] == "Long" else 1,
            key=f"action_{idx}",
            label_visibility="collapsed",
        )
        opt["action"] = new_action

        new_qty = cols[3].number_input(
            "수량",
            min_value=1,
            max_value=1000,
            value=int(opt["quantity"]),
            key=f"qty_{idx}",
            label_visibility="collapsed",
        )
        opt["quantity"] = new_qty

        new_prem = cols[4].number_input(
            "Premium",
            min_value=0.0,
            max_value=10000.0,
            value=float(opt["premium"]),
            step=0.01,
            format="%.2f",
            key=f"prem_{idx}",
            label_visibility="collapsed",
        )
        opt["premium"] = new_prem

        if cols[5].button("삭제", key=f"del_{idx}", use_container_width=True):
            to_delete.append(idx)

    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            st.session_state.basket.pop(idx)
        st.rerun()

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
    return True


def render_simulation_controls(max_dte, min_strike, max_strike, vol_change_val, rate_val):
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

    return days_to_expiry_val, target_underlying_val


def render_analysis_chart_and_summary(vol_change_val, rate_val, days_to_expiry_val, target_underlying_val):
    if st.session_state.underlying_price is not None:
        recalculate_ivs(rate_val)

    strikes = [opt["strike"] for opt in st.session_state.basket]
    avg_iv = 0.30
    valid_ivs = [opt.get("iv", 0.30) for opt in st.session_state.basket if opt.get("iv", 0.0) > 0.0]
    if valid_ivs:
        avg_iv = sum(valid_ivs) / len(valid_ivs)

    max_dte = max(opt.get("remn_cnt", 30) for opt in st.session_state.basket)
    t_annual = max_dte / 365.0
    std_dev = avg_iv * math.sqrt(t_annual)

    S_current = st.session_state.underlying_price if st.session_state.underlying_price is not None else strikes[0]
    ci_lower = S_current * math.exp(-1.96 * std_dev)
    ci_upper = S_current * math.exp(1.96 * std_dev)

    strike_lower = min(strikes) * 0.95
    strike_upper = max(strikes) * 1.05

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

            if opt_type == "Call" or opt_type.upper() == "C":
                indiv_profit = max(s - k, 0.0) - prem
            else:
                indiv_profit = max(k - s, 0.0) - prem

            if act == "Short":
                indiv_profit = -indiv_profit
            total_profit += indiv_profit * qty * 100

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

    fig = render_portfolio_payoff_chart(
        basket=st.session_state.basket,
        underlying_price=st.session_state.underlying_price,
        rate=rate_val,
        vol_change=vol_change_val,
        days_to_expiry=days_to_expiry_val,
    )
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})

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

        profit_color = "#00E676" if total_exp_profit >= 0 else "#FF1744"
        st.markdown(f"""
        <div class="custom-card" style="text-align: center;">
            <h4 style="margin: 0; color: #8888aa; font-family: Outfit;">포트폴리오 총 예상 손익 시나리오</h4>
            <h2 style="margin: 10px 0 0 0; color: {profit_color}; font-family: Outfit; font-weight: 800; font-size: 2.5rem;">
                ${total_exp_profit:+.2f}
            </h2>
        </div>
        """, unsafe_allow_html=True)
