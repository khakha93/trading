import datetime
import streamlit as st
import pandas as pd
import yfinance as yf

from src.master import get_option_chain, get_underlying_info
from src.kis_client import fetch_stock_price
from src.pricing import black_scholes
from src.ui.ui_helpers import fetch_token, get_single_option_premium, should_search_ticker

def render_search_tab(rate_val):
    st.subheader("🔍 미국주식옵션 검색")

    # CSS를 주입하여 입력창에서 소문자를 타이핑하는 순간 즉시 대문자로 보이게 처리 (실시간 시각 변환)
    st.markdown("""
        <style>
        div[data-testid="stForm"] input {
            text-transform: uppercase;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.form(key="search_form", border=False):
        col_search1, col_search2 = st.columns([4, 1])
        search_ticker = col_search1.text_input(
            "기초자산 Ticker 입력 (예: AAPL, PG, TSLA, NVDA)",
            value="",
            key="search_ticker_input"
        ).upper().strip()

        col_search2.markdown("<div class='search-btn-spacer'></div>", unsafe_allow_html=True)
        search_clicked = col_search2.form_submit_button("종목 검색", type="primary", use_container_width=True)

    if "last_search_ticker" not in st.session_state:
        st.session_state.last_search_ticker = ""

    should_search = should_search_ticker(search_ticker, search_clicked=search_clicked)

    if should_search:
        with st.spinner("옵션 목록 및 현재가 로딩 중..."):
            st.session_state.last_search_ticker = search_ticker
            st.session_state.options_list = get_option_chain(search_ticker)
            st.session_state.queried_real_prices = {}
            st.session_state.user_queried_symbols = set()
            st.session_state.search_underlying_price = None
            st.session_state.search_underlying_info = None
            st.session_state.override_price_active = False
            st.session_state.override_price_val = None
            st.session_state.override_price_active_checkbox = False
            st.session_state.override_price_val_input = None

            if st.session_state.options_list:
                token = fetch_token()
                first_opt = st.session_state.options_list[0]
                underlying_info = get_underlying_info(first_opt["symbol"])
                if underlying_info and token:
                    st.session_state.search_underlying_info = underlying_info
                    try:
                        stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                        if stock_res and stock_res.get("rt_cd") == "0":
                            st.session_state.search_underlying_price = float(stock_res["output"]["last"])
                            st.session_state.search_underlying_info["prev_close"] = float(stock_res["output"]["base"])
                    except Exception:
                        pass

                    # Fetch prev_close and price fallback from yfinance
                    try:
                        stock = yf.Ticker(search_ticker)
                        prev_close_val = stock.fast_info.get("previousClose")
                        if prev_close_val:
                            if st.session_state.search_underlying_info is None:
                                st.session_state.search_underlying_info = {"exchange": "UNKNOWN", "ticker": search_ticker}
                            st.session_state.search_underlying_info["prev_close"] = float(prev_close_val)

                        if st.session_state.search_underlying_price is None:
                            spot_val = stock.fast_info.get("lastPrice")
                            if spot_val is not None:
                                st.session_state.search_underlying_price = float(spot_val)
                            else:
                                hist = stock.history(period="1d")
                                if not hist.empty:
                                    st.session_state.search_underlying_price = float(hist["Close"].iloc[-1])
                    except Exception:
                        pass
            
            # 장마감 상태인 경우, 옵션 종가 기준 시점의 기초자산 주가는 현재가(lastPrice)인 search_underlying_price가 됩니다.
            if st.session_state.search_underlying_price is not None and st.session_state.search_underlying_info is not None:
                import pytz
                est = pytz.timezone("America/New_York")
                ny_time = datetime.datetime.now(est)
                is_market_open = (ny_time.weekday() < 5 and 
                                  datetime.time(9, 30) <= ny_time.time() <= datetime.time(16, 0))
                is_market_closed = not is_market_open
                if is_market_closed:
                    st.session_state.search_underlying_info["prev_close"] = st.session_state.search_underlying_price
            else:
                st.session_state.search_underlying_price = None
                st.session_state.search_underlying_info = None

    if "options_list" in st.session_state and st.session_state.options_list:
        options = st.session_state.options_list

        spot_live = st.session_state.get("search_underlying_price")
        underlying_info = st.session_state.get("search_underlying_info")

        if spot_live is not None and underlying_info is not None and underlying_info.get("ticker") == search_ticker:
            # 1. Valuation Mode & Price Simulation control panel
            with st.expander("⚙️ 기초자산 평가 기준 및 주가 설정", expanded=True):
                st.markdown("<p style='font-size: 0.85rem; color: #8888aa; margin-bottom: 12px;'>평가 기준 모드(Mode A/B)와 기초자산 주가 설정을 한곳에서 제어합니다. 모드에 따라 주가 및 만기일 기준이 다르게 자동 적용됩니다.</p>", unsafe_allow_html=True)
                
                # 라디오 버튼을 통한 평가 모드 선택
                current_mode = st.session_state.get("valuation_mode", "Mode A")
                sel_index = 0 if current_mode == "Mode A" else 1
                
                # Callbacks for callbacks-based state updates to prevent StreamlitAPIException
                def on_val_mode_change():
                    selected_val = st.session_state.val_mode_selector_widget
                    new_mode = "Mode A" if "Mode A" in selected_val else "Mode B"
                    st.session_state.valuation_mode = new_mode
                    if new_mode == "Mode A":
                        st.session_state.override_price_active_checkbox = False
                        st.session_state.override_price_active = False

                val_mode_selector = st.radio(
                    "📊 평가 기준 모드 선택 (Valuation Mode)",
                    options=[
                        "Mode A: 전일 종가 스냅샷 (DTE 동결, 주가 = 전일 종가 고정)",
                        "Mode B: 프리마켓/시뮬레이션 반영 (실시간 시간 가치 감쇄 반영)"
                    ],
                    index=sel_index,
                    key="val_mode_selector_widget",
                    on_change=on_val_mode_change,
                    help="Mode A: 전일 장마감 시점의 주가와 만기일수를 기준으로 옵션 가치를 노출합니다.\nMode B: 오늘의 실시간 주가 또는 시뮬레이션 주가와 만기일수(1일 차감)를 기준으로 옵션 이론가를 산출합니다."
                )
                
                new_mode = st.session_state.valuation_mode

                st.markdown("---")

                is_mode_a = (new_mode == "Mode A")
                
                # 1. Checkbox positioned at the top of the simulation block
                override_active = st.checkbox(
                    "주가 수동 보정 활성화 (Mode B 전용)",
                    key="override_price_active_checkbox",
                    disabled=is_mode_a
                )
                st.session_state.override_price_active = override_active

                # 2. Input and Action controls aligned horizontally in three equal columns
                col_sim1, col_sim2, col_sim3 = st.columns([1, 1, 1])

                if "override_price_val_input" not in st.session_state or st.session_state.override_price_val_input is None:
                    st.session_state.override_price_val_input = spot_live

                # Mode A인 경우 주가를 전일 종가로 고정하여 보여주기 위해 입력기값을 강제 동기화
                prev_close_val = underlying_info.get("prev_close")
                if is_mode_a and prev_close_val:
                    st.session_state.override_price_val_input = prev_close_val

                sim_price = col_sim1.number_input(
                    "보정/시뮬레이션 주가 ($)",
                    min_value=0.01,
                    step=0.01,
                    key="override_price_val_input",
                    disabled=is_mode_a or not override_active
                )
                st.session_state.override_price_val = sim_price

                btn_prev_label = f"전일 종가로 맞추기 (${prev_close_val:.2f})" if prev_close_val else "전일 종가로 맞추기"

                def click_prev_close():
                    st.session_state.override_price_active_checkbox = True
                    if prev_close_val:
                        st.session_state.override_price_val_input = prev_close_val

                def click_restore_live():
                    st.session_state.override_price_active_checkbox = False
                    st.session_state.override_price_val_input = spot_live

                # Spacer to push buttons down to align perfectly with the number input field
                col_sim2.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
                col_sim2.button(
                    btn_prev_label,
                    use_container_width=True,
                    disabled=is_mode_a or not prev_close_val,
                    on_click=click_prev_close
                )

                col_sim3.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
                col_sim3.button(
                    "실시간 현재가 복원",
                    use_container_width=True,
                    disabled=is_mode_a,
                    on_click=click_restore_live
                )

            # 2. Display Price Banner
            if override_active:
                spot_banner = st.session_state.override_price_val
                st.markdown(f"""
                <div style="display: inline-block; border: 1.5px solid #FF8F00; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 143, 0, 0.08); color: #FF8F00; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 10px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 143, 0, 0.15);">
                    ⚠️ {search_ticker} 수동보정 적용: ${spot_banner:.2f} (실시간 현재가: ${spot_live:.2f})
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="display: inline-block; border: 1.5px solid #FF1744; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 23, 68, 0.08); color: #FF1744; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 10px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 23, 68, 0.15);">
                    📊 {search_ticker} 현재가: ${spot_live:.2f}
                </div>
                """, unsafe_allow_html=True)

        st.success(f"'{search_ticker}' 기초자산에 해당하는 미국옵션 {len(options)}개를 마스터 파일에서 불러왔습니다.")

        def format_expiry(date_str):
            if date_str == "Unknown":
                return "Unknown"
            try:
                exp_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.date.today()
                d_day = (exp_date - today).days
                if d_day < 0:
                    return f"{date_str} (D+{abs(d_day)})"
                else:
                    return f"{date_str} (D-{d_day})"
            except Exception:
                return date_str

        unique_expiries = sorted(list(set(opt["expiry_date"] for opt in options)))

        st.markdown("<div class='custom-card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin-top:0; font-family: Outfit;'>➕ 포트폴리오에 옵션 추가 (인터랙티브 옵션 그리드)</h4>", unsafe_allow_html=True)

        col_cfg1, col_cfg2, col_cfg3, col_cfg4 = st.columns([1.5, 1.5, 1.2, 0.8])
        sel_expiry = col_cfg1.selectbox("📅 만기일 선택 (Expiry Date)", unique_expiries, format_func=format_expiry)
        sort_method = col_cfg2.selectbox("📊 행사가 정렬 방식", ["행사가격 오름차순", "현재가에 가까운 순 (ATM 우선)"])
        sel_action = col_cfg3.selectbox("➡️ 일괄 포지션 설정", ["Long (매수)", "Short (매도)"], key="batch_pos")
        sel_qty = col_cfg4.number_input("🔢 일괄 수량 설정", min_value=1, max_value=1000, value=1, key="batch_qty")

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

        filtered_opts = [opt for opt in options if opt["expiry_date"] == sel_expiry]
        spot_live = st.session_state.get("search_underlying_price")
        override_active = st.session_state.get("override_price_active", False)
        override_val = st.session_state.get("override_price_val")
        
        val_mode = st.session_state.get("valuation_mode", "Mode A")
        prev_close_val = underlying_info.get("prev_close") if underlying_info else None
        
        if override_active and override_val:
            spot = override_val
        elif val_mode == "Mode A" and prev_close_val and prev_close_val > 0:
            spot = prev_close_val
        else:
            spot = spot_live

        # Detect spot price change to clear cached option premiums
        if "last_applied_spot" not in st.session_state:
            st.session_state.last_applied_spot = spot
        elif st.session_state.last_applied_spot != spot:
            st.session_state.last_applied_spot = spot
            st.session_state.queried_real_prices = {}

        closest_strike = None
        if spot and filtered_opts:
            all_strikes = [opt["strike"] for opt in filtered_opts]
            closest_strike = min(all_strikes, key=lambda k: abs(k - spot))

        strike_map = {}
        for opt in filtered_opts:
            strike = opt["strike"]
            if strike not in strike_map:
                strike_map[strike] = {"Call": None, "Put": None}
            strike_map[strike][opt["type"]] = opt

        sorted_strikes = list(strike_map.keys())
        if sort_method == "현재가에 가까운 순 (ATM 우선)":
            if spot:
                sorted_strikes = sorted(sorted_strikes, key=lambda k: abs(k - spot))
        else:
            sorted_strikes = sorted(sorted_strikes)

        if filter_preset == "전체 보기":
            pass
        elif filter_preset in ["ATM ± 5 행사가", "ATM ± 10 행사가", "ATM ± 20 행사가"]:
            window_map = {
                "ATM ± 5 행사가": 5,
                "ATM ± 10 행사가": 10,
                "ATM ± 20 행사가": 20
            }
            half_window = window_map[filter_preset]
            if spot and closest_strike and closest_strike in sorted_strikes:
                if sort_method == "현재가에 가까운 순 (ATM 우선)":
                    total_count = half_window * 2 + 1
                    sorted_strikes = sorted_strikes[:total_count]
                else:
                    try:
                        closest_idx = sorted_strikes.index(closest_strike)
                        start_idx = max(0, closest_idx - half_window)
                        end_idx = min(len(sorted_strikes), closest_idx + half_window + 1)
                        sorted_strikes = sorted_strikes[start_idx:end_idx]
                    except Exception:
                        pass
        elif filter_preset == "직접 입력 (고급)" and strike_filter_input:
            try:
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
                elif "~" in strike_filter_input or ("-" in strike_filter_input and not strike_filter_input.startswith("-")):
                    delimiter = "~" if "~" in strike_filter_input else "-"
                    parts = strike_filter_input.split(delimiter)
                    if len(parts) == 2:
                        left_str, right_str = parts[0].strip(), parts[1].strip()
                        min_val = float(left_str) if left_str else 0.0
                        max_val = float(right_str) if right_str else float("inf")
                        sorted_strikes = [s for s in sorted_strikes if min_val <= s <= max_val]
                else:
                    filter_vals = [float(v.strip()) for v in strike_filter_input.split(",") if v.strip()]
                    if filter_vals:
                        sorted_strikes = [s for s in sorted_strikes if any(abs(s - f) < 0.01 for f in filter_vals)]
            except ValueError:
                st.caption("⚠️ 올바른 필터 형식을 입력해 주세요. (예: '170-180', '>175', '170, 180')")

        # yfinance를 사용하여 15분 지연된 전체 옵션 체인의 변동성 정보 로드 및 캐싱
        cache_key = f"yf_opts_{search_ticker}_{sel_expiry}"
        if cache_key not in st.session_state:
            try:
                stock = yf.Ticker(search_ticker)
                opt_chain = stock.option_chain(sel_expiry)
                calls_dict = {row["strike"]: row for _, row in opt_chain.calls.iterrows()}
                puts_dict = {row["strike"]: row for _, row in opt_chain.puts.iterrows()}
                st.session_state[cache_key] = {"calls": calls_dict, "puts": puts_dict}
            except Exception as e:
                st.session_state[cache_key] = None
        
        yf_data = st.session_state.get(cache_key)

        # 실시간 ATM 옵션의 IV를 샘플링하여 보정 계수(Calibration Factor) 계산
        calibration_factor = 1.0
        avg_real_iv = 0.30
        
        today = datetime.date.today()
        try:
            exp_dt = datetime.datetime.strptime(sel_expiry, "%Y-%m-%d").date()
            remn_cnt = max(0, (exp_dt - today).days)
        except Exception:
            remn_cnt = 30
        t_annual = max(1, remn_cnt) / 365.0

        if spot and spot > 0 and closest_strike:
            # 3-Strike Sampling: ATM 및 상하 1개 행사가 (총 3개 행사가, 6개 옵션) 찾기
            all_strikes = sorted(list(set(opt["strike"] for opt in filtered_opts)))
            try:
                idx_atm = all_strikes.index(closest_strike)
            except ValueError:
                idx_atm = -1
                
            sampled_strikes = []
            if idx_atm != -1:
                if idx_atm > 0:
                    sampled_strikes.append(all_strikes[idx_atm - 1])
                sampled_strikes.append(closest_strike)
                if idx_atm < len(all_strikes) - 1:
                    sampled_strikes.append(all_strikes[idx_atm + 1])
            else:
                sampled_strikes = [closest_strike] if closest_strike else []
                
            # 샘플링한 행사가들의 콜/풋 옵션 필터링
            sampled_opts = []
            atm_call_opt = None
            atm_put_opt = None
            for s in sampled_strikes:
                s_call = None
                s_put = None
                for opt in filtered_opts:
                    if opt["strike"] == s:
                        if opt["type"] == "Call":
                            s_call = opt
                            if s == closest_strike:
                                atm_call_opt = opt
                        elif opt["type"] == "Put":
                            s_put = opt
                            if s == closest_strike:
                                atm_put_opt = opt
                if s_call:
                    sampled_opts.append(s_call)
                if s_put:
                    sampled_opts.append(s_put)

            # KIS API로 실시간 시세 조회 (캐싱 활용)
            if "queried_real_prices" not in st.session_state:
                st.session_state.queried_real_prices = {}

            kis_remn_cnt = None

            # 6개 샘플 옵션들에 대해 순차 조회 (캐싱 안 되어 있는 것만 조회)
            for opt in sampled_opts:
                sym = opt["symbol"]
                if sym not in st.session_state.queried_real_prices:
                    real_prem, temp_remn, details = get_single_option_premium(sym)
                    if real_prem > 0:
                        details["remn_cnt"] = temp_remn
                        st.session_state.queried_real_prices[sym] = details
                        if kis_remn_cnt is None:
                            kis_remn_cnt = temp_remn
                else:
                    cached_details = st.session_state.queried_real_prices[sym]
                    if kis_remn_cnt is None and "remn_cnt" in cached_details:
                        kis_remn_cnt = cached_details["remn_cnt"]

            # KIS에서 제공하는 정확한 잔존일수 정보로 만기(T) 동기화 및 모드별 보정 적용
            val_mode = st.session_state.get("valuation_mode", "Mode A")
            today_dte = kis_remn_cnt if kis_remn_cnt is not None else remn_cnt
            
            import pytz
            est = pytz.timezone("America/New_York")
            ny_time = datetime.datetime.now(est)
            is_market_open = (ny_time.weekday() < 5 and 
                              datetime.time(9, 30) <= ny_time.time() <= datetime.time(16, 0))
            is_market_closed = not is_market_open
            
            if val_mode == "Mode A":
                # Mode A: 전일 종가 스냅샷
                # 장마감 시에는 옵션 종가가 어제 기준이므로 DTE = 오늘 DTE + 1일
                final_dte = today_dte + (1 if is_market_closed else 0)
            else:
                # Mode B: 프리마켓/시뮬레이션 반영 (오늘 시점 가치평가)
                # DTE = 오늘 DTE
                final_dte = today_dte
                
            t_annual = max(0.05, final_dte) / 365.0

            # 실시간 IV 계산 및 3-Strike Linear Skew Fitting
            from src.pricing import implied_volatility
            
            call_points = []
            put_points = []
            
            real_ivs = []
            delayed_ivs = []
            prev_close_val = underlying_info.get("prev_close") if underlying_info else None
            
            real_iv_call = None
            real_iv_put = None

            for opt in sampled_opts:
                sym = opt["symbol"]
                strike = opt["strike"]
                opt_type = opt["type"]
                details = st.session_state.queried_real_prices.get(sym)
                
                if details and details.get("premium", 0.0) > 0.0:
                    real_price = details["premium"]
                    if override_active and override_val:
                        iv_spot = override_val
                    elif not details.get("is_mid") and prev_close_val and prev_close_val > 0:
                        iv_spot = prev_close_val
                    else:
                        iv_spot = spot_live
                        
                    iv = implied_volatility(real_price, iv_spot, strike, t_annual, rate_val, opt_type)
                    if iv > 0:
                        if opt_type == "Call":
                            call_points.append((strike - iv_spot, iv))
                            if strike == closest_strike:
                                real_iv_call = iv
                                real_ivs.append(iv)
                                if yf_data and closest_strike in yf_data["calls"]:
                                    delayed_ivs.append(max(0.01, yf_data["calls"][closest_strike]["impliedVolatility"]))
                                else:
                                    delayed_ivs.append(0.30)
                        else:
                            put_points.append((strike - iv_spot, iv))
                            if strike == closest_strike:
                                real_iv_put = iv
                                real_ivs.append(iv)
                                if yf_data and closest_strike in yf_data["puts"]:
                                    delayed_ivs.append(max(0.01, yf_data["puts"][closest_strike]["impliedVolatility"]))
                                else:
                                    delayed_ivs.append(0.30)

            # 선형 스큐 피팅 함수 정의
            def fit_linear_iv_skew(points):
                n = len(points)
                if n < 2:
                    if n == 1:
                        return 0.0, points[0][1]
                    return 0.0, 0.30
                sum_x = sum(p[0] for p in points)
                sum_y = sum(p[1] for p in points)
                mean_x = sum_x / n
                mean_y = sum_y / n
                num = 0.0
                den = 0.0
                for p in points:
                    dx = p[0] - mean_x
                    dy = p[1] - mean_y
                    num += dx * dy
                    den += dx * dx
                if den == 0.0:
                    return 0.0, mean_y
                m = num / den
                c = mean_y - m * mean_x
                return m, c

            # 콜/풋 각각 독립적으로 3개 점의 IV 피팅 도출
            m_call, c_call = fit_linear_iv_skew(call_points)
            m_put, c_put = fit_linear_iv_skew(put_points)
            
            avg_real_iv = sum(real_ivs) / len(real_ivs) if real_ivs else 0.30
            if c_call == 0.30 and avg_real_iv != 0.30:
                c_call = avg_real_iv
            if c_put == 0.30 and avg_real_iv != 0.30:
                c_put = avg_real_iv

            baseline_iv_call = real_iv_call if (real_iv_call and real_iv_call > 0) else avg_real_iv
            baseline_iv_put = real_iv_put if (real_iv_put and real_iv_put > 0) else avg_real_iv

            # Disable yfinance calibration when the market is closed OR for short-dated options (DTE < 5) to prevent extreme skew
            use_yf_calibration = not is_market_closed and final_dte >= 5

            if use_yf_calibration and real_ivs and delayed_ivs:
                avg_delayed_iv = sum(delayed_ivs) / len(delayed_ivs)
                if avg_delayed_iv > 0:
                    temp_factor = avg_real_iv / avg_delayed_iv
                    # Only accept yfinance IV calibration if the factor is within a reasonable range (0.5 to 2.0)
                    if 0.5 <= temp_factor <= 2.0 and avg_delayed_iv > 0.05:
                        calibration_factor = temp_factor
                    else:
                        calibration_factor = 1.0
                        yf_data = None
                else:
                    calibration_factor = 1.0
                    yf_data = None
            else:
                calibration_factor = 1.0
                yf_data = None

        val_mode = st.session_state.get("valuation_mode", "Mode A")
        grid_data = []
        user_queried = st.session_state.get("user_queried_symbols", set())

        for strike in sorted_strikes:
            call_opt = strike_map[strike]["Call"]
            put_opt = strike_map[strike]["Put"]
            is_atm = " (ATM)" if closest_strike and strike == closest_strike else ""

            call_theo_str = "N/A"
            call_real_str = "-"
            call_close_price_str = "-"
            call_symbol = ""
            call_expiry_code = ""
            
            if call_opt:
                call_symbol = call_opt["symbol"]
                call_expiry_code = call_opt["expiry"]
                
                bs_price = 0.0
                if spot and spot > 0:
                    if use_yf_calibration:
                        baseline_iv = baseline_iv_call
                        if yf_data and strike in yf_data["calls"]:
                            val = yf_data["calls"][strike]["impliedVolatility"]
                            if val == val:
                                baseline_iv = val
                        if baseline_iv < 0.05 or baseline_iv != baseline_iv:
                            baseline_iv = baseline_iv_call
                        calibrated_iv = max(0.0001, baseline_iv * calibration_factor)
                    else:
                        calibrated_iv = max(0.01, m_call * (strike - spot) + c_call)
                        
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, calibrated_iv, "Call")
                    call_theo_str = f"${bs_price:.2f}"
                    
                if "queried_real_prices" in st.session_state and call_symbol in st.session_state.queried_real_prices:
                    details = st.session_state.queried_real_prices[call_symbol]
                    label = "체결-장마감" if details.get("last", 0.0) > 0.0 else "정산-장마감"
                    if details.get("is_mid"):
                        call_close_price_str = f"${details['premium']:.2f}"
                        if closest_strike and strike == closest_strike:
                            call_real_str = f"${details['premium']:.2f} ({details['bid']:.2f} / {details['ask']:.2f})"
                        elif call_symbol in user_queried:
                            call_real_str = f"${details['premium']:.2f} ({details['bid']:.2f} / {details['ask']:.2f})"
                    else:
                        call_close_price_str = f"${details['premium']:.2f} ({label})"
                        if closest_strike and strike == closest_strike:
                            call_real_str = f"${details['premium']:.2f} ({label})"
                        elif call_symbol in user_queried:
                            call_real_str = f"${details['premium']:.2f} ({label})"

            put_theo_str = "N/A"
            put_real_str = "-"
            put_close_price_str = "-"
            put_symbol = ""
            put_expiry_code = ""
            
            if put_opt:
                put_symbol = put_opt["symbol"]
                put_expiry_code = put_opt["expiry"]
                
                bs_price = 0.0
                if spot and spot > 0:
                    if use_yf_calibration:
                        baseline_iv = baseline_iv_put
                        if yf_data and strike in yf_data["puts"]:
                            val = yf_data["puts"][strike]["impliedVolatility"]
                            if val == val:
                                baseline_iv = val
                        if baseline_iv < 0.05 or baseline_iv != baseline_iv:
                            baseline_iv = baseline_iv_put
                        calibrated_iv = max(0.0001, baseline_iv * calibration_factor)
                    else:
                        calibrated_iv = max(0.01, m_put * (strike - spot) + c_put)
                        
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, calibrated_iv, "Put")
                    put_theo_str = f"${bs_price:.2f}"
                    
                if "queried_real_prices" in st.session_state and put_symbol in st.session_state.queried_real_prices:
                    details = st.session_state.queried_real_prices[put_symbol]
                    label = "체결-장마감" if details.get("last", 0.0) > 0.0 else "정산-장마감"
                    if details.get("is_mid"):
                        put_close_price_str = f"${details['premium']:.2f}"
                        if closest_strike and strike == closest_strike:
                            put_real_str = f"${details['premium']:.2f} ({details['bid']:.2f} / {details['ask']:.2f})"
                        elif put_symbol in user_queried:
                            put_real_str = f"${details['premium']:.2f} ({details['bid']:.2f} / {details['ask']:.2f})"
                    else:
                        put_close_price_str = f"${details['premium']:.2f} ({label})"
                        if closest_strike and strike == closest_strike:
                            put_real_str = f"${details['premium']:.2f} ({label})"
                        elif put_symbol in user_queried:
                            put_real_str = f"${details['premium']:.2f} ({label})"

            grid_data.append({
                "선택 (Call)": False,
                "Call (실제)": call_real_str,
                "Call (이론)": call_theo_str,
                "Call (전일 마감)": call_close_price_str,
                "Call (예상)": call_theo_str,
                "행사가격 (Strike)": f"${strike:.2f}{is_atm}",
                "Put (이론)": put_theo_str,
                "Put (실제)": put_real_str,
                "Put (예상)": put_theo_str,
                "Put (전일 마감)": put_close_price_str,
                "선택 (Put)": False,
                "call_symbol": call_symbol,
                "put_symbol": put_symbol,
                "raw_strike": strike,
                "call_expiry_code": call_expiry_code,
                "put_expiry_code": put_expiry_code
            })

        df_grid = pd.DataFrame(grid_data)

        if not df_grid.empty:
            if val_mode == "Mode B":
                display_cols = ["선택 (Call)", "Call (전일 마감)", "Call (예상)", "행사가격 (Strike)", "Put (예상)", "Put (전일 마감)", "선택 (Put)"]
            else:
                display_cols = ["선택 (Call)", "Call (실제)", "Call (이론)", "행사가격 (Strike)", "Put (이론)", "Put (실제)", "선택 (Put)"]
                
            df_to_edit = df_grid[display_cols + ["call_symbol", "put_symbol", "raw_strike", "call_expiry_code", "put_expiry_code"]]

            st.write("👉 추가할 옵션들을 **'선택 (Call)'** 또는 **'선택 (Put)'** 컬럼에 체크해 주세요.")
            edited_df = st.data_editor(
                df_to_edit,
                column_config={
                    "선택 (Call)": st.column_config.CheckboxColumn(default=False),
                    "Call (실제)": st.column_config.TextColumn(disabled=True),
                    "Call (이론)": st.column_config.TextColumn(disabled=True),
                    "Call (전일 마감)": st.column_config.TextColumn(disabled=True),
                    "Call (예상)": st.column_config.TextColumn(disabled=True),
                    "행사가격 (Strike)": st.column_config.TextColumn(disabled=True),
                    "Put (이론)": st.column_config.TextColumn(disabled=True),
                    "Put (실제)": st.column_config.TextColumn(disabled=True),
                    "Put (예상)": st.column_config.TextColumn(disabled=True),
                    "Put (전일 마감)": st.column_config.TextColumn(disabled=True),
                    "선택 (Put)": st.column_config.CheckboxColumn(default=False),
                    "call_symbol": None,
                    "put_symbol": None,
                    "raw_strike": None,
                    "call_expiry_code": None,
                    "put_expiry_code": None
                },
                disabled=[
                    "Call (실제)", "Call (이론)", "Call (전일 마감)", "Call (예상)",
                    "행사가격 (Strike)",
                    "Put (이론)", "Put (실제)", "Put (예상)", "Put (전일 마감)"
                ],
                width="stretch",
                hide_index=True,
                height=500,
                key=f"option_editor_grid_{sel_expiry}"
            )

            col_btn1, col_btn2 = st.columns(2)

            if col_btn2.button("🔍 선택 종목 실시간 시세 조회", use_container_width=True):
                selected_calls = edited_df[edited_df["선택 (Call)"] == True]
                selected_puts = edited_df[edited_df["선택 (Put)"] == True]
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
                        if "user_queried_symbols" not in st.session_state:
                            st.session_state.user_queried_symbols = set()
                        for sym in symbols_to_query:
                            real_prem, _, details = get_single_option_premium(sym)
                            if "queried_real_prices" not in st.session_state:
                                st.session_state.queried_real_prices = {}
                            st.session_state.queried_real_prices[sym] = details
                            st.session_state.user_queried_symbols.add(sym)
                    st.success("실시간 시세 조회가 완료되었습니다!")
                    st.rerun()

            if col_btn1.button("🛒 선택한 옵션들을 바스켓에 일괄 추가", type="primary", use_container_width=True):
                selected_calls = edited_df[edited_df["선택 (Call)"] == True]
                selected_puts = edited_df[edited_df["선택 (Put)"] == True]

                if selected_calls.empty and selected_puts.empty:
                    st.warning("선택된 옵션이 없습니다. 추가할 옵션의 '선택 (Call)' 또는 '선택 (Put)'을 체크해 주세요.")
                else:
                    success_symbols = []
                    with st.spinner("시세 정보를 조회하고 포트폴리오에 추가하는 중..."):
                        # Sync portfolio underlying price and info with search tab
                        override_active = st.session_state.get("override_price_active", False)
                        override_val = st.session_state.get("override_price_val")
                        if override_active and override_val:
                            st.session_state.underlying_price = override_val
                        else:
                            st.session_state.underlying_price = st.session_state.get("search_underlying_price")
                        st.session_state.underlying_info = st.session_state.get("search_underlying_info")

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
                                    try:
                                        stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                                        if stock_res and stock_res.get("rt_cd") == "0":
                                            st.session_state.underlying_price = float(stock_res["output"]["last"])
                                            st.session_state.search_underlying_price = st.session_state.underlying_price
                                            st.session_state.search_underlying_info = underlying_info
                                    except Exception:
                                        pass

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
                                if "queried_real_prices" in st.session_state and sym in st.session_state.queried_real_prices:
                                    details = st.session_state.queried_real_prices[sym]
                                    premium = details["premium"]
                                    try:
                                        exp_dt = datetime.datetime.strptime(sel_expiry, "%Y-%m-%d").date()
                                        remn_cnt = max(0, (exp_dt - datetime.date.today()).days)
                                    except Exception:
                                        remn_cnt = 30
                                else:
                                    premium, remn_cnt, _ = get_single_option_premium(sym)

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

                        for _, row in selected_calls.iterrows():
                            if row["call_symbol"]:
                                add_option(row["call_symbol"], "Call", float(row["raw_strike"]), row["call_expiry_code"])

                        for _, row in selected_puts.iterrows():
                            if row["put_symbol"]:
                                add_option(row["put_symbol"], "Put", float(row["raw_strike"]), row["put_expiry_code"])

                    st.session_state.selected_ticker = search_ticker
                    st.success(f"성공적으로 바스켓에 추가/업데이트 되었습니다: {', '.join(success_symbols)}")
                    st.rerun()
        else:
            st.warning("해당 만기일에 상장된 옵션 계약이 없습니다.")

        st.markdown("</div>", unsafe_allow_html=True)

    elif "options_list" in st.session_state:
        st.warning(f"기초자산 '{search_ticker}'에 매칭되는 미국옵션 리스트가 마스터 파일에 없습니다. 대문자 티커를 확인하십시오.")
