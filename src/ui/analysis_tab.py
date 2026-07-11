import datetime
import math
import pandas as pd
import streamlit as st

from src.chart import render_portfolio_payoff_chart
from src.pricing import black_scholes
from src.ui.ui_helpers import recalculate_ivs, sync_widgets, update_basket_prices


def render_basket_overview():
    if not st.session_state.basket:
        st.info("🧺 바스켓이 비어 있습니다. **'종목 검색 & 추가'** 탭에서 옵션을 검색하여 추가해 주세요.")
        return None

    # 바스켓 내의 고유 티커 목록 추출
    from src.ui.ui_helpers import get_ticker_from_symbol
    basket_tickers = sorted(list(set(get_ticker_from_symbol(opt["symbol"]) for opt in st.session_state.basket)))
    
    if not basket_tickers:
        st.info("🧺 바스켓에 유효한 옵션이 없습니다.")
        return None

    st.write("### 🧺 현재 포트폴리오 바스켓")

    # 드롭다운 필터의 기본 선택 인덱스 결정
    default_ticker = st.session_state.get("selected_ticker")
    if default_ticker in basket_tickers:
        default_idx = basket_tickers.index(default_ticker)
    else:
        default_idx = 0

    col_filter1, col_filter2 = st.columns([2, 5])
    sel_ticker = col_filter1.selectbox(
        "🎯 분석 대상 종목 선택 (Ticker)",
        basket_tickers,
        index=default_idx,
        key="selected_ticker_dropdown"
    )
    st.session_state.selected_ticker = sel_ticker

    # 선택된 티커의 기초자산 시세가 없거나 다른 경우 KIS API 또는 yfinance로 갱신 (자가 치유)
    if (st.session_state.underlying_price is None or 
        st.session_state.get("underlying_info", {}).get("ticker") != sel_ticker):
        
        st.session_state.analysis_price_override_active = False
        st.session_state.analysis_price_override_val = None
        st.session_state.analysis_price_override_active_checkbox = False
        st.session_state.analysis_price_override_val_input = None
        
        first_opt = next(opt for opt in st.session_state.basket if get_ticker_from_symbol(opt["symbol"]) == sel_ticker)
        from src.master import get_underlying_info
        from src.ui.ui_helpers import fetch_token
        import yfinance as yf
        
        underlying_info = get_underlying_info(first_opt["symbol"])
        token = fetch_token()
        if underlying_info and token:
            st.session_state.underlying_info = underlying_info
            try:
                with st.spinner(f"{sel_ticker} 실시간 주가 조회 중..."):
                    from src.kis_client import fetch_stock_price
                    stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                    if stock_res and stock_res.get("rt_cd") == "0":
                        st.session_state.underlying_price = float(stock_res["output"]["last"])
                        st.session_state.underlying_info["prev_close"] = float(stock_res["output"]["base"])
            except Exception:
                pass
            
            # Fetch previous close from yfinance as fallback
            try:
                stock = yf.Ticker(sel_ticker)
                prev_close_val = stock.fast_info.get("previousClose")
                if prev_close_val:
                    st.session_state.underlying_info["prev_close"] = float(prev_close_val)
                
                if st.session_state.underlying_price is None:
                    spot_val = stock.fast_info.get("lastPrice")
                    if spot_val is not None:
                        st.session_state.underlying_price = float(spot_val)
                    else:
                        hist = stock.history(period="1d")
                        if not hist.empty:
                            st.session_state.underlying_price = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        # 장마감 상태인 경우, 옵션 종가 기준 시점의 기초자산 주가는 현재가(lastPrice)인 underlying_price가 됩니다.
        if st.session_state.underlying_price is not None and st.session_state.underlying_info is not None:
            import pytz
            est = pytz.timezone("America/New_York")
            ny_time = datetime.datetime.now(est)
            is_market_open = (ny_time.weekday() < 5 and 
                              datetime.time(9, 30) <= ny_time.time() <= datetime.time(16, 0))
            is_market_closed = not is_market_open
            if is_market_closed:
                st.session_state.underlying_info["prev_close"] = st.session_state.underlying_price

    spot_live = st.session_state.underlying_price
    underlying_info = st.session_state.get("underlying_info")
    
    # 1. Price simulation control panel for Portfolio Analysis
    if spot_live is not None:
        with st.expander("📈 분석 기준 주가 시뮬레이션 및 조정 (장마감 대응)", expanded=False):
            st.markdown("<p style='font-size: 0.85rem; color: #8888aa; margin-bottom: 15px;'>장마감 시점이나 프리마켓 거래 시 옵션 거래 체결가와 실시간 주가 사이에 시간차가 생겨 분석이 왜곡될 수 있습니다. 분석 기준 주가를 수동으로 고정하거나 조정해 보세요.</p>", unsafe_allow_html=True)
            col_an_sim1, col_an_sim2 = st.columns([1, 1])
            
            override_active = col_an_sim1.checkbox(
                "분석 기준 주가 수동 설정 활성화",
                key="analysis_price_override_active_checkbox"
            )
            st.session_state.analysis_price_override_active = override_active
            
            if "analysis_price_override_val_input" not in st.session_state or st.session_state.analysis_price_override_val_input is None:
                st.session_state.analysis_price_override_val_input = spot_live
                
            sim_price = col_an_sim1.number_input(
                "시뮬레이션 분석 주가 ($)",
                min_value=0.01,
                step=0.01,
                key="analysis_price_override_val_input",
                disabled=not override_active
            )
            st.session_state.analysis_price_override_val = sim_price
            
            prev_close_val = underlying_info.get("prev_close") if underlying_info else None
            btn_prev_label = f"전일 종가로 맞추기 (${prev_close_val:.2f})" if prev_close_val else "전일 종가로 맞추기"
            
            if col_an_sim2.button(btn_prev_label, key="btn_prev_analysis", use_container_width=True, disabled=not prev_close_val):
                st.session_state.analysis_price_override_active_checkbox = True
                st.session_state.analysis_price_override_val_input = prev_close_val
                st.rerun()
                
            if col_an_sim2.button("실시간 현재가로 복원", key="btn_restore_analysis", use_container_width=True):
                st.session_state.analysis_price_override_active_checkbox = False
                st.session_state.analysis_price_override_val_input = spot_live
                st.rerun()

        # Define active spot price
        override_active = st.session_state.get("analysis_price_override_active", False)
        override_val = st.session_state.get("analysis_price_override_val")
        
        val_mode = st.session_state.get("valuation_mode", "Mode A")
        prev_close_val = underlying_info.get("prev_close") if underlying_info else None
        
        if override_active and override_val is not None:
            spot_active = override_val
        elif val_mode == "Mode A" and prev_close_val and prev_close_val > 0:
            spot_active = prev_close_val
        else:
            spot_active = spot_live
        
        # 2. Display Price Banner
        if override_active:
            st.markdown(f"""
            <div style="display: inline-block; border: 1.5px solid #FF8F00; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 143, 0, 0.08); color: #FF8F00; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 5px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 143, 0, 0.15);">
                ⚠️ 분석 기준가 (수동보정): ${spot_active:.2f} (실시간 현재가: ${spot_live:.2f})
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="display: inline-block; border: 1.5px solid #FF1744; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 23, 68, 0.08); color: #FF1744; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 5px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 23, 68, 0.15);">
                📊 {sel_ticker} 현재가: ${spot_live:.2f}
            </div>
            """, unsafe_allow_html=True)

    # 선택된 티커의 옵션만 필터링 (원본 인덱스 맵핑 포함)
    filtered_basket = []
    val_mode = st.session_state.get("valuation_mode", "Mode A")
    
    import pytz
    est = pytz.timezone("America/New_York")
    ny_time = datetime.datetime.now(est)
    is_market_open = (ny_time.weekday() < 5 and 
                      datetime.time(9, 30) <= ny_time.time() <= datetime.time(16, 0))
    is_market_closed = not is_market_open
    
    for orig_idx, opt in enumerate(st.session_state.basket):
        if get_ticker_from_symbol(opt["symbol"]) == sel_ticker:
            opt_copy = opt.copy()
            opt_copy["original_idx"] = orig_idx
            # opt["remn_cnt"] represents today's DTE
            if val_mode == "Mode A" and is_market_closed:
                # Mode A + Closed Market: use yesterday's DTE (today's DTE + 1)
                opt_copy["remn_cnt"] = opt["remn_cnt"] + 1
            else:
                # Mode B or Open Market: use today's DTE directly
                opt_copy["remn_cnt"] = opt["remn_cnt"]
            filtered_basket.append(opt_copy)

    cols_header = st.columns([2.5, 1.2, 1.2, 1.2, 1.2, 1.0])
    cols_header[0].write("**옵션 코드**")
    cols_header[1].write("**구분 (행사가)**")
    cols_header[2].write("**포지션**")
    cols_header[3].write("**수량**")
    cols_header[4].write("**시자가/평단가 ($)**")
    cols_header[5].write("**작업**")

    to_delete = []
    for opt in filtered_basket:
        orig_idx = opt["original_idx"]
        original_opt = st.session_state.basket[orig_idx]

        cols = st.columns([2.5, 1.2, 1.2, 1.2, 1.2, 1.0])
        cols[0].write(f"`{opt['symbol']}`")
        cols[1].write(f"{opt['type']} (${opt['strike']:.2f})")

        new_action = cols[2].selectbox(
            "포지션",
            ["Long", "Short"],
            index=0 if original_opt["action"] == "Long" else 1,
            key=f"action_{orig_idx}",
            label_visibility="collapsed",
        )
        original_opt["action"] = new_action

        new_qty = cols[3].number_input(
            "수량",
            min_value=1,
            max_value=1000,
            value=int(original_opt["quantity"]),
            key=f"qty_{orig_idx}",
            label_visibility="collapsed",
        )
        original_opt["quantity"] = new_qty

        new_prem = cols[4].number_input(
            "Premium",
            min_value=0.0,
            max_value=10000.0,
            value=float(original_opt["premium"]),
            step=0.01,
            format="%.2f",
            key=f"prem_{orig_idx}",
            label_visibility="collapsed",
        )
        original_opt["premium"] = new_prem

        if cols[5].button("삭제", key=f"del_{orig_idx}", use_container_width=True):
            to_delete.append(orig_idx)

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
        st.rerun()

    st.markdown("---")
    return filtered_basket


def get_simulation_price_range(filtered_basket, rate_val):
    """차트에 표시할 주가 시뮬레이션 범위 (x_min, x_max) 계산"""
    if not filtered_basket:
        return 0.0, 100.0

    override_active = st.session_state.get("analysis_price_override_active", False)
    override_val = st.session_state.get("analysis_price_override_val")
    spot_live = st.session_state.get("underlying_price")
    spot_active = override_val if (override_active and override_val is not None) else spot_live

    if spot_active is not None:
        recalculate_ivs(rate_val)

    strikes = [opt["strike"] for opt in filtered_basket]
    avg_iv = 0.30
    valid_ivs = [opt.get("iv", 0.30) for opt in filtered_basket if opt.get("iv", 0.0) > 0.0]
    if valid_ivs:
        avg_iv = sum(valid_ivs) / len(valid_ivs)

    max_dte = max(opt.get("remn_cnt", 30) for opt in filtered_basket)
    t_annual = max_dte / 365.0
    std_dev = avg_iv * math.sqrt(t_annual)

    S_current = spot_active if spot_active is not None else strikes[0]
    ci_lower = S_current * math.exp(-1.96 * std_dev)
    ci_upper = S_current * math.exp(1.96 * std_dev)

    strike_lower = min(strikes) * 0.95
    strike_upper = max(strikes) * 1.05

    x_min = min(ci_lower, strike_lower, S_current * 0.9)
    x_max = max(ci_upper, strike_upper, S_current * 1.1)

    return float(x_min), float(x_max)


def render_simulation_controls(filtered_basket, max_dte, rate_val):
    st.markdown("<h4 style='font-family: Outfit; margin-top: 15px; margin-bottom: 5px;'>⚙️ 수익곡선 상세 시뮬레이션 제어</h4>", unsafe_allow_html=True)
    col_sim1, col_sim2, col_sim3 = st.columns(3)

    # Ensure max_dte is at least 1 for the slider to have min_value < max_value
    max_dte_val = max(1, int(max_dte))

    # Initialize or sanitize DTE session states
    if "dte_slider" not in st.session_state:
        st.session_state.dte_slider = max_dte_val
    if "dte_num" not in st.session_state:
        st.session_state.dte_num = max_dte_val

    if st.session_state.dte_slider > max_dte_val:
        st.session_state.dte_slider = max_dte_val
    if st.session_state.dte_num > max_dte_val:
        st.session_state.dte_num = max_dte_val

    # Initialize or sanitize IV session states
    if "vol_slider" not in st.session_state:
        st.session_state.vol_slider = 0.0
    if "vol_num" not in st.session_state:
        st.session_state.vol_num = 0.0

    with col_sim1:
        current_dte = st.session_state.dte_slider
        target_date = datetime.date.today() + datetime.timedelta(days=int(current_dte))
        target_date_str = target_date.strftime("%Y-%m-%d")
        st.markdown(f"**⏱️ 시뮬레이션 시점 (DTE: {current_dte}일 후, 날짜: `{target_date_str}`)**")
        st.slider("DTE 슬라이더", min_value=0, max_value=max_dte_val, key="dte_slider", on_change=sync_widgets, args=("dte_slider", "dte_num"), label_visibility="collapsed")
        days_to_expiry_val = st.number_input("DTE 정밀 입력 (일)", min_value=0, max_value=max_dte_val, step=1, key="dte_num", on_change=sync_widgets, args=("dte_num", "dte_slider"), label_visibility="collapsed")

    # 차트 시각화 범위에 맞추어 목표주가 슬라이더 범위 결정 (x_min, x_max)
    x_min, x_max = get_simulation_price_range(filtered_basket, rate_val)
    if x_min >= x_max:
        x_max = x_min + 1.0

    # Determine default target value
    override_active = st.session_state.get("analysis_price_override_active", False)
    override_val = st.session_state.get("analysis_price_override_val")
    spot_live = st.session_state.get("underlying_price")
    spot_active = override_val if (override_active and override_val is not None) else spot_live

    default_val = spot_active
    if default_val is None:
        if filtered_basket:
            default_val = filtered_basket[0]["strike"]
        else:
            default_val = (x_min + x_max) / 2.0
    default_val = max(x_min, min(x_max, float(default_val)))

    # Initialize or sanitize target session states
    if "target_slider" not in st.session_state:
        st.session_state.target_slider = default_val
    if "target_num" not in st.session_state:
        st.session_state.target_num = default_val

    if st.session_state.target_slider < x_min or st.session_state.target_slider > x_max:
        st.session_state.target_slider = default_val
    if st.session_state.target_num < x_min or st.session_state.target_num > x_max:
        st.session_state.target_num = default_val

    with col_sim2:
        spot = spot_active
        if spot and spot > 0:
            target_val = st.session_state.target_slider
            pct_change = (target_val - spot) / spot * 100
            st.markdown(f"**🎯 분석 목표 주가 ($) (기초자산 대비 `{pct_change:+.2f}%`)**")
        else:
            st.markdown("**🎯 분석 목표 주가 ($)**")
        st.slider("목표주가 슬라이더", min_value=x_min, max_value=x_max, key="target_slider", on_change=sync_widgets, args=("target_slider", "target_num"), label_visibility="collapsed")
        target_underlying_val = st.number_input("목표주가 정밀 입력 ($)", min_value=x_min, max_value=x_max, step=0.01, key="target_num", on_change=sync_widgets, args=("target_num", "target_slider"), label_visibility="collapsed")

    with col_sim3:
        st.markdown("**⚡ 내재변동성(IV) 변화율 (%p)**")
        st.slider("IV 슬라이더", min_value=-50.0, max_value=50.0, key="vol_slider", on_change=sync_widgets, args=("vol_slider", "vol_num"), label_visibility="collapsed")
        vol_input_val = st.number_input("IV 정밀 입력 (%p)", min_value=-50.0, max_value=50.0, step=0.1, key="vol_num", on_change=sync_widgets, args=("vol_num", "vol_slider"), label_visibility="collapsed")
        vol_change_val = vol_input_val / 100.0

    return days_to_expiry_val, target_underlying_val, vol_change_val


def render_analysis_chart_and_summary(filtered_basket, vol_change_val, rate_val, days_to_expiry_val, target_underlying_val):
    override_active = st.session_state.get("analysis_price_override_active", False)
    override_val = st.session_state.get("analysis_price_override_val")
    spot_live = st.session_state.get("underlying_price")
    spot_active = override_val if (override_active and override_val is not None) else spot_live

    if spot_active is not None:
        recalculate_ivs(rate_val)

    fig = render_portfolio_payoff_chart(
        basket=filtered_basket,
        underlying_price=spot_active,
        rate=rate_val,
        vol_change=vol_change_val,
        days_to_expiry=days_to_expiry_val,
    )
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})
    st.info("💡 **팁**: 대화형 Plotly 그래프 위에 마우스를 올리면 각 지점의 구체적인 만기 손익과 만기 전 예상 손익 정보를 툴팁으로 확인할 수 있습니다. 마우스 스크롤을 통해 차트 확대/축소(Zoom)도 가능합니다.")

    if target_underlying_val is not None and spot_active is not None:
        st.markdown("---")
        spot = spot_active
        pct_change = (target_underlying_val - spot) / spot * 100
        st.subheader(f"🎯 목표 주가 ${target_underlying_val:.2f} ({pct_change:+.2f}%) 시나리오 분석 (만기 {days_to_expiry_val}일 전)")

        analysis_data = []
        total_exp_profit = 0.0

        for opt in filtered_basket:
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
