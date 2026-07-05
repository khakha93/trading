import os
import sys
import argparse
import requests
from dotenv import load_dotenv

# 설정 파일 로드 (.env 또는 config.env 우선 탐색)
if os.path.exists('.env'):
    load_dotenv('.env')
elif os.path.exists('config.env'):
    load_dotenv('config.env')
else:
    load_dotenv()

# 한국투자증권 Open API 설정값
BASE_URL = "https://openapi.koreainvestment.com:9443"  # 해외옵션 시세조회는 실전투자만 지원
APP_KEY = os.getenv("APP_KEY")
APP_SECRET = os.getenv("APP_SECRET")
CUST_TYPE = os.getenv("CUST_TYPE", "P")  # 개인 'P', 법인 'B'

def get_access_token():
    """한국투자증권 OAuth 2.0 접근 토큰 발급"""
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        res_json = response.json()
        if "access_token" in res_json:
            return res_json["access_token"]
        else:
            print(f"[-] 토큰 발급 실패 응답: {res_json}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[-] 토큰 발급 API 호출 오류: {e}")
        if response is not None:
            print(f"[-] 응답 내용: {response.text}")
        sys.exit(1)

def fetch_option_price(token, symbol):
    """해외옵션 종목 현재가 조회"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/quotations/opt-price"
    
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFO55010000",  # 해외옵션종목현재가 실전투자 TR
        "custtype": CUST_TYPE,
    }
    
    params = {
        "SRS_CD": symbol
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[-] 시세 조회 API 호출 오류: {e}")
        if response is not None:
            print(f"[-] 응답 내용: {response.text}")
        sys.exit(1)

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
    print("[안내] 수신한 현재가는 종목 마스터 파일(fostkcode.mst)의 계산 소수점(sCalcDesz)")
    print("       설정에 따라 소수점 위치 조절이 필요할 수 있습니다.")
    print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한국투자증권 API 미국주식옵션 시세조회")
    parser.add_argument("symbol", type=str, help="조회할 옵션 종목 코드 (예: AAPL  240719C00180000)")
    args = parser.parse_args()
    
    # API 키 검증
    if not APP_KEY or not APP_SECRET or APP_KEY == "your_app_key_here" or APP_SECRET == "your_app_secret_here":
        print("[-] API 키가 설정되지 않았습니다.")
        print("[-] config.env.template을 복사하여 config.env 또는 .env 파일을 생성하고")
        print("    발급받으신 APP_KEY와 APP_SECRET을 입력해 주세요.")
        sys.exit(1)
        
    print("[*] Access Token을 발급받는 중...")
    token = get_access_token()
    print("[*] 토큰 발급 성공. 시세를 조회합니다...")
    
    result = fetch_option_price(token, args.symbol)
    print_option_info(result, args.symbol)
