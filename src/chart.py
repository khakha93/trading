import math
import os
from src.pricing import black_scholes, implied_volatility


def render_portfolio_payoff_chart(basket, underlying_price=None, rate=0.04, vol_change=0.0, days_to_expiry=None):
    """Plotly 기반 포트폴리오 합성 수익곡선 차트 생성"""
    import plotly.graph_objects as go

    if not basket:
        return go.Figure()

    strikes = [opt["strike"] for opt in basket]
    avg_iv = 0.30
    valid_ivs = [opt.get("iv", 0.30) for opt in basket if opt.get("iv", 0.0) > 0.0]
    if valid_ivs:
        avg_iv = sum(valid_ivs) / len(valid_ivs)

    max_dte = max(opt.get("remn_cnt", 30) for opt in basket)
    t_annual = max_dte / 365.0
    std_dev = avg_iv * math.sqrt(t_annual)

    S_current = underlying_price if underlying_price is not None else strikes[0]
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
        for opt in basket:
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

            if underlying_price is not None:
                t_target = min(days_to_expiry, opt["remn_cnt"]) / 365.0 if days_to_expiry is not None else 0.0
                if t_target > 0:
                    iv = opt.get("iv", 0.30)
                    sigma_target = max(iv + vol_change, 0.0001)
                    expected_val = black_scholes(s, k, t_target, rate, sigma_target, opt_type)

                    if act == "Long":
                        indiv_profit_pre = expected_val - prem
                    else:
                        indiv_profit_pre = prem - expected_val
                    total_profit_pre += indiv_profit_pre * qty * 100

        combined_payoffs.append(total_profit)
        if underlying_price is not None:
            combined_payoffs_pre.append(total_profit_pre)

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

    fig = go.Figure()

    fig.add_shape(type="line", x0=x_min, y0=0, x1=x_max, y1=0, line=dict(color="rgb(1, 2, 3)", width=1.5, dash="solid"))

    for idx, opt in enumerate(basket):
        fig.add_vline(x=opt["strike"], line=dict(color="rgb(1, 2, 3)", width=1.0, dash="dot"))
        dynamic_y = 1.0 - (idx * 0.05)
        fig.add_annotation(
            x=opt["strike"],
            y=dynamic_y,
            yref="paper",
            text=f" 행사가 ${opt['strike']:.2f} ({opt['type']})",
            showarrow=False,
            xanchor="right",
            yanchor="top",
            font=dict(color="rgb(1, 2, 3)", size=10, family="Inter")
        )

    beps_exp = find_beps(underlying_prices, combined_payoffs)
    for idx, bep in enumerate(beps_exp):
        fig.add_vline(
            x=bep,
            line=dict(color="#FFA726", width=1.5, dash="dot"),
            annotation_text=f" 만기 BEP (${bep:.2f})",
            annotation_position="bottom left",
            annotation_font=dict(color="#FFA726", size=10)
        )

    if underlying_price is not None:
        fig.add_vline(
            x=underlying_price,
            line=dict(color="#00E676", width=1.5, dash="dash"),
            annotation_text=f" 현재가 (${underlying_price:.2f})",
            annotation_position="top left",
            annotation_font=dict(color="#00E676")
        )

    if combined_payoffs_pre:
        fig.add_trace(go.Scatter(x=underlying_prices, y=combined_payoffs, mode="lines", name="만기 시 손익 (Expiration)", line=dict(color="#7F8C8D", width=2.8), hoverinfo="skip"))
        custom_data = [[p] for p in combined_payoffs]
        fig.add_trace(go.Scatter(
            x=underlying_prices,
            y=combined_payoffs_pre,
            mode="lines",
            name=f"만기 전 예상 손익 (D-{days_to_expiry}일)",
            line=dict(color="#0072FF", width=2.2),
            customdata=custom_data,
            hovertemplate="예상: %{y:$.2f}<br>만기: %{customdata[0]:$.2f}<extra></extra>"
        ))
    else:
        fig.add_trace(go.Scatter(x=underlying_prices, y=combined_payoffs, mode="lines", name="만기 시 손익 (Expiration)", line=dict(color="#7F8C8D", width=2.8)))

    fig.update_layout(
        template="streamlit",
        title=dict(text="📊 포트폴리오 합성 손익 곡선 (Interactive Chart)", font=dict(family="Outfit", size=18)),
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        legend=dict(font=dict(size=11), bgcolor="rgba(0, 0, 0, 0)"),
        margin=dict(l=40, r=40, t=50, b=40),
        xaxis=dict(title=dict(text="기초자산 가격 ($)"), tickfont=dict(size=11), showgrid=True, zeroline=False, showspikes=True, spikethickness=1.5, spikedash="dot", spikecolor="#0072FF", spikemode="toaxis+across"),
        yaxis=dict(title=dict(text="합성 손익 ($)"), tickfont=dict(size=11), showgrid=True, zeroline=False, showspikes=True, spikethickness=1.5, spikedash="dot", spikecolor="#0072FF", spikemode="toaxis+across", fixedrange=True),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(33, 33, 33, 0.85)", font_size=11, font_family="Inter, sans-serif", font_color="#FFFFFF", bordercolor="rgba(150, 150, 150, 0.3)")
    )

    return fig


def plot_combined_payoff_diagram(ticker, option_positions, days_to_expiry=None, vol_change=0.0, rate=0.04, underlying_price=None, target_underlying=None):
    """복수 옵션 합성 포트폴리오의 수익곡선 시각화 (만기 시점 & 만기 전 특정 시점 비교)"""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[-] matplotlib이 설치되어 있지 않아 수익곡선을 그릴 수 없습니다.")
        return

    print("\n[*] 합성 수익곡선(Combined Payoff Diagram)을 생성하는 중...")
    
    strikes = [opt["strike"] for opt in option_positions]
    min_val = min(strikes)
    max_val = max(strikes)
    if underlying_price is not None:
        min_val = min(min_val, underlying_price)
        max_val = max(max_val, underlying_price)
        
    # X축 범위: 최저 행사가의 -20% ~ 최고 행사가의 +20%
    x_min = min_val * 0.8
    x_max = max_val * 1.2
    
    # 150개의 포인트 생성 (순수 파이썬)
    steps = 150
    underlying_prices = [x_min + (x_max - x_min) * i / (steps - 1) for i in range(steps)]
    
    combined_payoffs = []
    combined_payoffs_pre = []
    
    # 만기 전 분석 시 개별 옵션의 내재변동성(IV) 계산
    if days_to_expiry is not None and underlying_price is not None:
        for opt in option_positions:
            t_current = float(opt["remn_cnt"]) / 365.0
            opt["iv"] = implied_volatility(
                market_price=opt["premium"],
                S=underlying_price,
                K=opt["strike"],
                T=t_current,
                r=rate,
                option_type=opt["type"]
            )
            if opt["iv"] <= 0.0:
                opt["iv"] = 0.30  # fallback
            print(f"[*] 옵션 '{opt['symbol']}' 산출 IV: {opt['iv']:.2%}")
            
    for s in underlying_prices:
        total_profit = 0.0
        total_profit_pre = 0.0
        for opt in option_positions:
            k = opt["strike"]
            prem = opt["premium"]
            qty = opt["quantity"]
            act = opt["action"]
            opt_type = opt["type"]
            
            # 1. 만기 시 손익 계산
            if opt_type == "Call" or opt_type.upper() == "C":
                indiv_profit = max(s - k, 0.0) - prem
            else:
                indiv_profit = max(k - s, 0.0) - prem
                
            if act == "sell":
                indiv_profit = -indiv_profit
            total_profit += indiv_profit * qty
            
            # 2. 만기 전 특정 시점 손익 계산
            if days_to_expiry is not None and underlying_price is not None:
                t_target = min(days_to_expiry, opt["remn_cnt"]) / 365.0
                sigma_target = max(opt["iv"] + vol_change, 0.0001)
                expected_val = black_scholes(s, k, t_target, rate, sigma_target, opt_type)
                
                if act == "buy":
                    indiv_profit_pre = expected_val - prem
                else:
                    indiv_profit_pre = prem - expected_val
                total_profit_pre += indiv_profit_pre * qty
                
        combined_payoffs.append(total_profit)
        if days_to_expiry is not None and underlying_price is not None:
            combined_payoffs_pre.append(total_profit_pre)
            
    # 특정 기초자산 가격에서의 개별 옵션 예상가 및 포트폴리오 손익 상세 출력
    if target_underlying is not None and days_to_expiry is not None and underlying_price is not None:
        print("\n" + "=" * 90)
        print(f"★ 만기 {days_to_expiry}일 전 기초자산 가격 ${target_underlying:.2f}일 때의 포트폴리오 분석 ★")
        print("=" * 90)
        print(f"{'Option Code':^16} | {'Pos':^4} | {'Strike':^8} | {'Current Prem':^12} | {'Expected Prem':^13} | {'Exp. Profit (per unit)':^22}")
        print("-" * 90)
        
        total_exp_profit = 0.0
        for opt in option_positions:
            k = opt["strike"]
            prem = opt["premium"]
            qty = opt["quantity"]
            act = opt["action"]
            opt_type = opt["type"]
            
            t_target = min(days_to_expiry, opt["remn_cnt"]) / 365.0
            sigma_target = max(opt["iv"] + vol_change, 0.0001)
            expected_val = black_scholes(target_underlying, k, t_target, rate, sigma_target, opt_type)
            
            if act == "buy":
                indiv_profit_pre = expected_val - prem
                pos_str = "Long"
            else:
                indiv_profit_pre = prem - expected_val
                pos_str = "Short"
                
            opt_profit = indiv_profit_pre * qty
            total_exp_profit += opt_profit
            
            print(f"{opt['symbol']:<16} | {pos_str:^4} | {k:>8.2f} | ${prem:>11.2f} | ${expected_val:>12.2f} | ${indiv_profit_pre:>+21.2f}")
            
        print("-" * 90)
        print(f"포트폴리오 예상 총 손익: ${total_exp_profit:>+11.2f}")
        print("=" * 90 + "\n")

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

    # 차트 플롯
    plt.figure(figsize=(11, 6.5))
    
    # 0선 기준
    plt.axhline(0, color='black', linestyle='--', linewidth=1.2)
    
    # 행사가 가이드 세로선
    for k in sorted(list(set(strikes))):
        plt.axvline(k, color='blue', linestyle=':', alpha=0.5, label=f'Strike K={k:.1f}' if f'Strike K={k:.1f}' not in plt.gca().get_legend_handles_labels()[1] else "")
        
    # 기초자산 현재가 가이드 세로선
    if underlying_price is not None:
        plt.axvline(underlying_price, color='green', linestyle='--', alpha=0.5, label=f'Current Stock Price (${underlying_price:.2f})')

    # BEP 손익분기점 세로선 및 라벨링
    beps = find_beps(underlying_prices, combined_payoffs)
    for idx, bep in enumerate(beps):
        plt.axvline(bep, color='red', linestyle='-.', alpha=0.5, label='Expiry BEP' if idx == 0 else "")
        plt.text(bep, plt.ylim()[0] + (plt.ylim()[1] - plt.ylim()[0]) * 0.05, f" Expiry BEP\n ${bep:.2f}", color='red', fontsize=9)
        
    if days_to_expiry is not None and underlying_price is not None:
        beps_pre = find_beps(underlying_prices, combined_payoffs_pre)
        for idx, bep in enumerate(beps_pre):
            plt.axvline(bep, color='orange', linestyle='-.', alpha=0.6, label='Pre-Expiry BEP' if idx == 0 else "")
            plt.text(bep, plt.ylim()[0] + (plt.ylim()[1] - plt.ylim()[0]) * 0.18, f" Target BEP\n ${bep:.2f}", color='orange', fontsize=9)

    # 합성 수익곡선 그리기
    if days_to_expiry is not None and underlying_price is not None:
        plt.plot(underlying_prices, combined_payoffs, label='Payoff at Expiration', color='grey', linestyle='--', linewidth=1.5)
        plt.plot(underlying_prices, combined_payoffs_pre, label=f'Expected Payoff ({days_to_expiry} days to expiry)', color='purple', linewidth=3)
        plt.fill_between(underlying_prices, combined_payoffs_pre, 0, where=[p > 0 for p in combined_payoffs_pre], color='green', alpha=0.15)
        plt.fill_between(underlying_prices, combined_payoffs_pre, 0, where=[p < 0 for p in combined_payoffs_pre], color='red', alpha=0.15)
    else:
        plt.plot(underlying_prices, combined_payoffs, label='Combined Portfolio Payoff', color='purple', linewidth=3)
        plt.fill_between(underlying_prices, combined_payoffs, 0, where=[p > 0 for p in combined_payoffs], color='green', alpha=0.15)
        plt.fill_between(underlying_prices, combined_payoffs, 0, where=[p < 0 for p in combined_payoffs], color='red', alpha=0.15)
    
    # 타이틀 구성 (옵션 요약)
    title_parts = []
    for opt in option_positions:
        act_sign = "+" if opt["action"] == "buy" else "-"
        title_parts.append(f"{act_sign}{opt['quantity']}{opt['type']}({opt['strike']:.1f})")
    strategy_str = ", ".join(title_parts)
    
    title_text = f"Option Portfolio Payoff - {ticker}\nStrategy: [{strategy_str}]"
    if days_to_expiry is not None:
        title_text += f"\nPre-Expiration Target: {days_to_expiry} days to expiry (Vol change: {vol_change:+.1%}, Rate: {rate:.1%})"
        
    plt.title(title_text, fontsize=12, fontweight='bold')
    plt.xlabel("Underlying Asset Price ($)", fontsize=11)
    plt.ylabel("Combined Profit / Loss ($)", fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend(loc='upper left', fontsize=10)
    
    # 차트 저장
    os.makedirs("output", exist_ok=True)
    output_img = os.path.join("output", "payoff_diagram.png")
    plt.savefig(output_img, dpi=150, bbox_inches='tight')
    print(f"[*] 합성 수익곡선 이미지가 '{output_img}'로 저장되었습니다.")
    
    try:
        plt.show()
    except Exception as e:
        print(f"[-] GUI 창을 띄울 수 없습니다. (디스플레이 서버 미지원): {e}")
