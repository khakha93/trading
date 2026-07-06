import sys
import re
import argparse
from src.config import APP_KEY, APP_SECRET
from src.pricing import black_scholes, implied_volatility
from src.kis_client import get_access_token, fetch_option_price, fetch_stock_price, get_effective_premium
from src.master import download_master_file, parse_option_chain, get_underlying_info
from src.chart import plot_combined_payoff_diagram

def print_option_info(data, symbol):
    """조회한 옵션 시세 정보 포맷팅 출력"""
    if data.get("rt_cd") != "0":
        print(f"[-] API 응답 오류 (rt_cd={data.get('rt_cd')}): {data.get('msg1')}")
        return
        
    output = data.get("output1", {})
    if not output:
        print("[-] 응답 상세 데이터(output1)가 비어 있습니다.")
        return

    print("=" * 50)
    print(f"★ [미국주식옵션 시세조회] 종목코드: {symbol} ★")
    print("=" * 50)
    print(f"  - 현재가: {output.get('last_price', '').strip()}")
    print(f"  - 전일대비: {output.get('prev_diff_price', '').strip()} ({output.get('prev_diff_rate', '').strip()}%)")
    print(f"  - 시가: {output.get('open_price', '').strip()}")
    print(f"  - 고가: {output.get('high_price', '').strip()}")
    print(f"  - 저가: {output.get('low_price', '').strip()}")
    print("-" * 50)
    print(f"  - 매수1호가: {output.get('bid_price', '').strip()} (수량: {output.get('bid_qntt', '').strip()})")
    print(f"  - 매도1호가: {output.get('ask_price', '').strip()} (수량: {output.get('ask_qntt', '').strip()})")
    print(f"  - 총매수잔량: {output.get('tot_bid_qntt', '').strip()} / 총매도잔량: {output.get('tot_ask_qntt', '').strip()}")
    print(f"  - 누적거래수량: {output.get('vol', '').strip()}")
    print("-" * 50)
    print(f"  - 만기일: {output.get('expr_date', '').strip()} (잔존일수: {output.get('remn_cnt', '').strip()}일)")
    print(f"  - 거래소: {output.get('exch_cd', '').strip()} ({output.get('crc_cd', '').strip()})")
    print(f"  - 틱사이즈: {output.get('tick_size', '').strip()} / 증거금: {output.get('trst_mgn', '').strip()}")
    print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한국투자증권 API 미국주식옵션 정보 조회 및 합성 시각화")
    parser.add_argument("symbol_or_ticker", type=str, nargs='?', help="조회할 옵션코드(예: 1PGN26 C145.0) 또는 기초자산 티커(예: AAPL, PG)")
    parser.add_argument("-p", "--payoff", nargs="+", help="합성 만기수익곡선 그리기. '코드:포지션:수량' 구조로 복수 입력 가능 (예: '코드:buy:1' '코드:sell:1')")
    parser.add_argument("-d", "--days-to-expiry", type=int, help="만기 전 특정 시점의 잔존일수 (예: 만기 5일 전이면 5 입력)")
    parser.add_argument("-v", "--vol-change", type=float, default=0.0, help="변동성(IV) 변화율 (예: +5%p 이면 5 또는 0.05 입력, -3%p 이면 -3 또는 -0.03 입력)")
    parser.add_argument("-r", "--rate", type=float, default=4.0, help="무위험 이자율 %% (예: 4.0%% 이면 4.0 입력, 기본값: 4.0%%)")
    parser.add_argument("-s", "--target-underlying", type=float, help="예상가 산출을 위한 만기 전 특정 시점의 기초자산 가격 ($)")
    args = parser.parse_args()
    
    # 변동성 변화 및 무위험 이자율 입력치 정규화 (백분율 처리)
    vol_change = args.vol_change
    if abs(vol_change) >= 0.5:
        vol_change /= 100.0
        
    rate = args.rate
    if rate >= 0.5:
        rate /= 100.0
        
    # 1. 만기수익곡선 합성 시각화 모드 (-p / --payoff 옵션 지정 시)
    if args.payoff:
        if not APP_KEY or not APP_SECRET or APP_KEY == "your_app_key_here" or APP_SECRET == "your_app_secret_here":
            print("[-] API 키가 설정되지 않았습니다.")
            print("[-] config.env.template을 복사하여 config.env 또는 .env 파일을 생성하고")
            print("    발급받으신 APP_KEY와 APP_SECRET을 입력해 주세요.")
            sys.exit(1)
            
        print("[*] 합성 수익곡선 분석 모드 실행")
        token = get_access_token()
        
        option_positions = []
        ticker = None
        
        for idx, arg in enumerate(args.payoff):
            parts = arg.split(":")
            symbol = parts[0].strip()
            
            action = "buy"
            quantity = 1
            
            if len(parts) == 2:
                p2 = parts[1].strip().lower()
                if p2 in ["buy", "sell", "b", "s"]:
                    action = "sell" if p2 in ["sell", "s"] else "buy"
                else:
                    try:
                        quantity = int(p2)
                    except ValueError:
                        pass
            elif len(parts) >= 3:
                p2 = parts[1].strip().lower()
                p3 = parts[2].strip()
                action = "sell" if p2 in ["sell", "s"] else "buy"
                try:
                    quantity = int(p3)
                except ValueError:
                    pass
            
            match = re.match(r"(?:\d?)([A-Z]+)([A-Z]\d{2})\s+([CP])([\d\.]+)", symbol)
            if not match:
                print(f"[-] 잘못된 옵션코드 규격입니다: '{symbol}'")
                print("    한국투자증권 규격에 맞는 코드를 사용해 주세요 (예: 1PGN26 C145.0)")
                sys.exit(1)
                
            opt_ticker, _, option_type, strike_str = match.groups()
            opt_type = "Call" if option_type == 'C' else "Put"
            strike = float(strike_str)
            
            if ticker is None:
                ticker = opt_ticker
            elif ticker != opt_ticker:
                print(f"[-] 경고: 서로 다른 기초자산의 합성 옵션입니다 ({ticker} vs {opt_ticker})")
                print("    동일한 기초자산의 옵션들로 조합해 주세요.")
                sys.exit(1)
                
            print(f"[*] [{idx+1}/{len(args.payoff)}] '{symbol}' 시세 조회 중...")
            price_res = fetch_option_price(token, symbol)
            
            if price_res.get("rt_cd") != "0":
                print(f"[-] 시세 수집 실패 (rt_cd={price_res.get('rt_cd')}): {price_res.get('msg1')}")
                sys.exit(1)
                
            output = price_res.get("output1", {})
            premium = get_effective_premium(output)
            if premium <= 0:
                print(f"[-] '{symbol}' 현재가 정보가 존재하지 않거나 유효하지 않습니다.")
                sys.exit(1)
                
            remn_cnt_str = output.get("remn_cnt", "").strip()
            remn_cnt = int(remn_cnt_str) if remn_cnt_str.isdigit() else 30
            
            option_positions.append({
                "symbol": symbol,
                "ticker": opt_ticker,
                "type": opt_type,
                "strike": strike,
                "premium": premium,
                "action": action,
                "quantity": quantity,
                "remn_cnt": remn_cnt
            })
            
        underlying_price = None
        if args.days_to_expiry is not None or args.target_underlying is not None:
            underlying_info = get_underlying_info(option_positions[0]["symbol"])
            if underlying_info:
                print(f"[*] 기초자산({underlying_info['ticker']})의 실시간 시세를 조회하는 중...")
                stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                if stock_res and stock_res.get("rt_cd") == "0":
                    underlying_price = float(stock_res["output"]["last"])
                    print(f"[*] 기초자산 현재가: ${underlying_price:.2f}")
                else:
                    msg = stock_res.get("msg1") if stock_res else "응답 없음"
                    print(f"[-] 기초자산 시세 조회 실패: {msg}")
                    sys.exit(1)
            else:
                print("[-] 마스터 파일에서 기초자산 정보를 찾을 수 없습니다.")
                sys.exit(1)
                
        plot_combined_payoff_diagram(
            ticker=ticker,
            option_positions=option_positions,
            days_to_expiry=args.days_to_expiry,
            vol_change=vol_change,
            rate=rate,
            underlying_price=underlying_price,
            target_underlying=args.target_underlying
        )
        sys.exit(0)
        
    # 2. 일반 단일 시세 및 체인 조회 모드 (positional argument)
    if not args.symbol_or_ticker:
        parser.print_help()
        sys.exit(1)
        
    input_val = args.symbol_or_ticker.strip()
    is_ticker = re.match(r"^[a-zA-Z]{1,5}$", input_val) is not None
    
    if is_ticker:
        download_master_file()
        parse_option_chain(input_val.upper())
    else:
        if not APP_KEY or not APP_SECRET or APP_KEY == "your_app_key_here" or APP_SECRET == "your_app_secret_here":
            print("[-] API 키가 설정되지 않았습니다.")
            print("[-] config.env.template을 복사하여 config.env 또는 .env 파일을 생성하고")
            print("    발급받으신 APP_KEY와 APP_SECRET을 입력해 주세요.")
            sys.exit(1)
            
        token = get_access_token()
        print("[*] 시세를 조회합니다...")
        result = fetch_option_price(token, input_val)
        
        if args.days_to_expiry is not None or args.target_underlying is not None:
            if result.get("rt_cd") != "0":
                print(f"[-] 시세 수집 실패 (rt_cd={result.get('rt_cd')}): {result.get('msg1')}")
                sys.exit(1)
                
            output = result.get("output1", {})
            if output:
                remn_cnt_str = output.get("remn_cnt", "").strip()
                remn_cnt = int(remn_cnt_str) if remn_cnt_str.isdigit() else 30
                
                underlying_info = get_underlying_info(input_val)
                if underlying_info:
                    print(f"[*] 기초자산({underlying_info['ticker']})의 실시간 시세를 조회하는 중...")
                    stock_res = fetch_stock_price(token, underlying_info["exchange"], underlying_info["ticker"])
                    if stock_res and stock_res.get("rt_cd") == "0":
                        underlying_price = float(stock_res["output"]["last"])
                        
                        match = re.match(r"(?:\d?)([A-Z]+)([A-Z]\d{2})\s+([CP])([\d\.]+)", input_val)
                        if match:
                            _, _, option_type, strike_str = match.groups()
                            opt_type = "Call" if option_type == 'C' else "Put"
                            strike = float(strike_str)
                            
                            premium = get_effective_premium(output)
                            
                            t_current = remn_cnt / 365.0
                            iv = implied_volatility(premium, underlying_price, strike, t_current, rate, opt_type)
                            if iv <= 0.0:
                                iv = 0.30
                                
                            print("\n" + "=" * 55)
                            print(f"★ [만기 전 옵션 예상가 분석] 종목: {input_val} ★")
                            print("=" * 55)
                            print(f"  - 기초자산({underlying_info['ticker']}) 현재가: ${underlying_price:.2f}")
                            print(f"  - 옵션 기준가(Mid/Last): ${premium:.2f}")
                            print(f"  - 산출된 내재변동성(IV): {iv:.2%}")
                            
                            if args.days_to_expiry is not None:
                                target_d = min(args.days_to_expiry, remn_cnt)
                                t_target = target_d / 365.0
                                sigma_target = max(iv + vol_change, 0.0001)
                                
                                target_s = args.target_underlying if args.target_underlying is not None else underlying_price
                                expected_val = black_scholes(target_s, strike, t_target, rate, sigma_target, opt_type)
                                profit = expected_val - premium
                                
                                print(f"  - 만기 {target_d}일 전 예상 가격 (기초자산 ${target_s:.2f} 일 때):")
                                print(f"    => 예상 옵션가: ${expected_val:.2f} (예상손익: ${profit:+.2f}, 수익률: {profit/premium:+.1%})")
                            print("=" * 55 + "\n")
                        else:
                            print("[-] 옵션 코드를 파싱할 수 없습니다.")
                    else:
                        msg = stock_res.get("msg1") if stock_res else "응답 없음"
                        print(f"[-] 기초자산 시세 조회 실패: {msg}")
                else:
                    print("[-] 마스터 파일에서 기초자산 정보를 찾을 수 없습니다.")
            else:
                print("[-] 응답 상세 데이터(output1)가 비어 있습니다.")
        else:
            print_option_info(result, input_val)
