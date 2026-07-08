import os
import datetime
import urllib.request
import zipfile
import ssl
import re
from src.config import MASTER_FILE, MASTER_ZIP, MASTER_URL


def download_master_file():
    """해외주식옵션 종목 마스터 파일 자동 다운로드 및 압축 해제"""
    today_str = datetime.date.today().strftime("%Y%m%d")

    need_download = True
    if os.path.exists(MASTER_FILE):
        file_mtime = datetime.date.fromtimestamp(os.path.getmtime(MASTER_FILE)).strftime("%Y%m%d")
        if file_mtime == today_str:
            need_download = False

    if not need_download:
        return True

    print("[*] 해외주식옵션 종목 마스터 파일이 없거나 최신이 아닙니다. 다운로드를 시작합니다...")
    try:
        ssl_context = ssl._create_unverified_context()
        os.makedirs("data", exist_ok=True)

        with urllib.request.urlopen(MASTER_URL, context=ssl_context, timeout=15) as response:
            with open(MASTER_ZIP, "wb") as f:
                f.write(response.read())

        with zipfile.ZipFile(MASTER_ZIP, 'r') as zip_ref:
            zip_ref.extractall("data")
        if os.path.exists(MASTER_ZIP):
            os.remove(MASTER_ZIP)
        print("[*] 마스터 파일 다운로드 및 압축 해제 성공!")
        return True
    except Exception as e:
        print(f"[-] 마스터 파일 다운로드 중 오류 발생: {e}")
        print("[-] 기존 로컬 마스터 파일을 계속 사용합니다.")
        return os.path.exists(MASTER_FILE)

def get_option_chain(ticker):
    """마스터 파일에서 티커와 매칭되는 미국옵션 리스트 파싱 및 반환"""
    if not os.path.exists(MASTER_FILE):
        return []
        
    options = []
    try:
        with open(MASTER_FILE, 'r', encoding='cp949', errors='ignore') as f:
            for line in f:
                if len(line) < 344:
                    continue
                line_ticker = line[248:254].strip()
                if line_ticker.upper() == ticker.upper():
                    symbol = line[:32].strip()
                    
                    match = re.match(r"(?:\d?)([A-Z]+)([A-Z]\d{2})\s+([CP])([\d\.]+)", symbol)
                    if match:
                        _, expiry, option_type, strike = match.groups()
                        opt_type = "Call" if option_type == 'C' else "Put"
                        
                        raw_date = line[37:45].strip()
                        if len(raw_date) == 8 and raw_date.isdigit():
                            expiry_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                        else:
                            expiry_date = "Unknown"
                            
                        options.append({
                            "symbol": symbol,
                            "expiry": expiry,
                            "expiry_date": expiry_date,
                            "type": opt_type,
                            "strike": float(strike)
                        })
                    else:
                        options.append({
                            "symbol": symbol,
                            "expiry": "Unknown",
                            "expiry_date": "Unknown",
                            "type": "Unknown",
                            "strike": 0.0
                        })
    except Exception as e:
        print(f"[-] 마스터 파일 파싱 중 오류 발생: {e}")
        
    options.sort(key=lambda x: (x["expiry_date"], x["strike"], x["type"]))
    return options

def parse_option_chain(ticker):
    """마스터 파일에서 티커와 매칭되는 미국옵션 리스트 파싱 및 출력"""
    print(f"[*] 마스터 파일({MASTER_FILE})에서 '{ticker}' 옵션 목록을 검색하는 중...")
    
    if not os.path.exists(MASTER_FILE):
        print(f"[-] 마스터 파일({MASTER_FILE})이 존재하지 않습니다.")
        sys.exit(1)
        
    options = get_option_chain(ticker)

    if not options:
        print(f"[-] '{ticker}'에 해당하는 옵션 종목을 찾지 못했습니다.")
        return

    print("\n" + "=" * 80)
    print(f"★ [{ticker}] US Stock Option Chain ★")
    print("=" * 80)
    print(f"{'Expiry':^10} | {'Type':^10} | {'Strike':^12} | {'KIS Option Code (Copy & Paste)'}")
    print("-" * 80)
    for opt in options:
        print(f"{opt['expiry']:^10} | {opt['type']:^10} | {opt['strike']:>10.2f} | {opt['symbol']}")
    print("-" * 80)
    print(f"Total {len(options)} option contracts found.")
    print("Copy the option code and run the command below to query quotes:")
    print(f"Example: python trading_option.py \"{options[0]['symbol']}\"")
    print("=" * 80)

def get_underlying_info(symbol):
    """
    마스터 파일에서 옵션 코드에 해당하는 기초자산의 거래소 코드와 티커를 찾습니다.
    """
    if not os.path.exists(MASTER_FILE):
        return None
        
    options_to_try = [symbol]
    if not symbol.startswith('1'):
        options_to_try.append('1' + symbol)
        
    try:
        with open(MASTER_FILE, 'r', encoding='cp949', errors='ignore') as f:
            for line in f:
                if len(line) < 344:
                    continue
                for opt in options_to_try:
                    if line.startswith(opt):
                        exchange = line[238:248].strip()
                        ticker = line[248:254].strip()
                        return {"exchange": exchange, "ticker": ticker}
    except Exception as e:
        print(f"[-] 마스터 파일 읽기 중 오류 발생: {e}")
    return None
