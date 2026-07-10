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

    if "options_list" in st.session_state and st.session_state.options_list:
        options = st.session_state.options_list

        if st.session_state.underlying_price is not None and st.session_state.underlying_info is not None and st.session_state.underlying_info.get("ticker") == search_ticker:
            st.markdown(f"""
            <div style="display: inline-block; border: 1.5px solid #FF1744; border-radius: 20px; padding: 6px 18px; background-color: rgba(255, 23, 68, 0.08); color: #FF1744; font-family: Outfit; font-weight: 700; font-size: 1.05rem; margin-top: 10px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(255, 23, 68, 0.15);">
                📊 {search_ticker} 현재가: ${st.session_state.underlying_price:.2f}
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
        spot = st.session_state.underlying_price
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
            # ATM 콜/풋 옵션 코드 찾기
            atm_call_opt = None
            atm_put_opt = None
            for opt in filtered_opts:
                if opt["strike"] == closest_strike:
                    if opt["type"] == "Call":
                        atm_call_opt = opt
                    elif opt["type"] == "Put":
                        atm_put_opt = opt

            # KIS API로 실시간 시세 조회 (캐싱 활용)
            if "queried_real_prices" not in st.session_state:
                st.session_state.queried_real_prices = {}

            if atm_call_opt and atm_call_opt["symbol"] not in st.session_state.queried_real_prices:
                real_prem_call, _ = get_single_option_premium(atm_call_opt["symbol"])
                if real_prem_call > 0:
                    st.session_state.queried_real_prices[atm_call_opt["symbol"]] = real_prem_call

            if atm_put_opt and atm_put_opt["symbol"] not in st.session_state.queried_real_prices:
                real_prem_put, _ = get_single_option_premium(atm_put_opt["symbol"])
                if real_prem_put > 0:
                    st.session_state.queried_real_prices[atm_put_opt["symbol"]] = real_prem_put

            # 실시간 IV 계산 및 yfinance 지연 IV와 비교
            from src.pricing import implied_volatility
            real_ivs = []
            delayed_ivs = []

            if atm_call_opt:
                real_price = st.session_state.queried_real_prices.get(atm_call_opt["symbol"])
                if real_price and real_price > 0:
                    real_iv_call = implied_volatility(real_price, spot, closest_strike, t_annual, rate_val, "Call")
                    if real_iv_call > 0:
                        real_ivs.append(real_iv_call)
                        if yf_data and closest_strike in yf_data["calls"]:
                            delayed_ivs.append(max(0.01, yf_data["calls"][closest_strike]["impliedVolatility"]))
                        else:
                            delayed_ivs.append(0.30)

            if atm_put_opt:
                real_price = st.session_state.queried_real_prices.get(atm_put_opt["symbol"])
                if real_price and real_price > 0:
                    real_iv_put = implied_volatility(real_price, spot, closest_strike, t_annual, rate_val, "Put")
                    if real_iv_put > 0:
                        real_ivs.append(real_iv_put)
                        if yf_data and closest_strike in yf_data["puts"]:
                            delayed_ivs.append(max(0.01, yf_data["puts"][closest_strike]["impliedVolatility"]))
                        else:
                            delayed_ivs.append(0.30)

            if real_ivs and delayed_ivs:
                avg_real_iv = sum(real_ivs) / len(real_ivs)
                avg_delayed_iv = sum(delayed_ivs) / len(delayed_ivs)
                if avg_delayed_iv > 0:
                    calibration_factor = avg_real_iv / avg_delayed_iv

        grid_data = []
        for strike in sorted_strikes:
            call_opt = strike_map[strike]["Call"]
            put_opt = strike_map[strike]["Put"]
            is_atm = " (ATM)" if closest_strike and strike == closest_strike else ""

            call_price_str = "N/A"
            call_symbol = ""
            call_expiry_code = ""
            if call_opt:
                call_symbol = call_opt["symbol"]
                call_expiry_code = call_opt["expiry"]
                if "queried_real_prices" in st.session_state and call_symbol in st.session_state.queried_real_prices:
                    real_price = st.session_state.queried_real_prices[call_symbol]
                    call_price_str = f"${real_price:.2f} (실시간)"
                elif spot and spot > 0:
                    baseline_iv = 0.30
                    if yf_data and strike in yf_data["calls"]:
                        baseline_iv = yf_data["calls"][strike]["impliedVolatility"]
                    if baseline_iv < 0.01:
                        baseline_iv = avg_real_iv
                    calibrated_iv = max(0.0001, baseline_iv * calibration_factor)
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, calibrated_iv, "Call")
                    call_price_str = f"${bs_price:.2f}"

            put_price_str = "N/A"
            put_symbol = ""
            put_expiry_code = ""
            if put_opt:
                put_symbol = put_opt["symbol"]
                put_expiry_code = put_opt["expiry"]
                if "queried_real_prices" in st.session_state and put_symbol in st.session_state.queried_real_prices:
                    real_price = st.session_state.queried_real_prices[put_symbol]
                    put_price_str = f"${real_price:.2f} (실시간)"
                elif spot and spot > 0:
                    baseline_iv = 0.30
                    if yf_data and strike in yf_data["puts"]:
                        baseline_iv = yf_data["puts"][strike]["impliedVolatility"]
                    if baseline_iv < 0.01:
                        baseline_iv = avg_real_iv
                    calibrated_iv = max(0.0001, baseline_iv * calibration_factor)
                    bs_price = black_scholes(spot, strike, t_annual, rate_val, calibrated_iv, "Put")
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
                    "call_symbol": None,
                    "put_symbol": None,
                    "raw_strike": None,
                    "call_expiry_code": None,
                    "put_expiry_code": None
                },
                disabled=["Call 가격 (이론가)", "행사가격 (Strike)", "Put 가격 (이론가)"],
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
                        for sym in symbols_to_query:
                            real_prem, _ = get_single_option_premium(sym)
                            if "queried_real_prices" not in st.session_state:
                                st.session_state.queried_real_prices = {}
                            st.session_state.queried_real_prices[sym] = real_prem
                    st.success("실시간 시세 조회가 완료되었습니다! 표에 '(실)'로 반영됩니다.")
                    st.rerun()

            if col_btn1.button("🛒 선택한 옵션들을 바스켓에 일괄 추가", type="primary", use_container_width=True):
                selected_calls = edited_df[edited_df["선택 (Call)"] == True]
                selected_puts = edited_df[edited_df["선택 (Put)"] == True]

                if selected_calls.empty and selected_puts.empty:
                    st.warning("선택된 옵션이 없습니다. 추가할 옵션의 '선택 (Call)' 또는 '선택 (Put)'을 체크해 주세요.")
                else:
                    success_symbols = []
                    with st.spinner("시세 정보를 조회하고 포트폴리오에 추가하는 중..."):
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
