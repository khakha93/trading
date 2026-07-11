import os
import sys
import json
import datetime
import requests
import time
from src.config import BASE_URL, APP_KEY, APP_SECRET, CUST_TYPE, CACHE_FILE

def get_access_token():
    """한국투자증권 OAuth 2.0 접근 토큰 발급 (캐싱 지원)"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            
            expired_at_str = cache.get("expired_at")
            if expired_at_str:
                expired_at = datetime.datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")
                if expired_at > datetime.datetime.now() + datetime.timedelta(seconds=60):
                    return cache["access_token"]
        except Exception:
            pass

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
            access_token = res_json["access_token"]
            expires_in = int(res_json.get("expires_in", 7200))
            
            expired_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
            cache_data = {
                "access_token": access_token,
                "expired_at": expired_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
            
            return access_token
        else:
            print(f"[-] 토큰 발급 실패 응답: {res_json}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[-] 토큰 발급 API 호출 오류: {e}")
        if 'response' in locals() and response is not None:
            print(f"[-] 응답 내용: {response.text}")
        sys.exit(1)


def fetch_option_price(token, symbol):
    """해외옵션 종목 현재가 조회 (자가치유 토큰 갱신 포함)"""
    def do_call(t):
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {t}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": "HHDFO55010000",
            "custtype": CUST_TYPE,
        }
        params = {"SRS_CD": symbol}
        time.sleep(1.0)
        return requests.get(url, headers=headers, params=params)

    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/quotations/opt-price"
    response = None
    try:
        response = do_call(token)
        try:
            res_json = response.json()
            if res_json.get("msg_cd") == "EGW00123" or "만료" in res_json.get("msg1", ""):
                print("[!] 토큰이 KIS 서버에서 만료되었습니다. 캐시를 비우고 재발급합니다.")
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
                new_token = get_access_token()
                response = do_call(new_token)
        except Exception:
            pass
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[-] 시세 조회 API 호출 오류: {e}")
        if response is not None:
            print(f"[-] 응답 내용: {response.text}")
        return None

def fetch_stock_price(token, exchange, symbol):
    """해외주식 종목 현재가 조회 (자가치유 토큰 갱신 및 정밀 디버깅 포함)"""
    def do_call(t):
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {t}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": "HHDFS00000300",
            "custtype": CUST_TYPE
        }
        params = {
            "AUTH": "",
            "EXCD": exchange.upper(),
            "SYMB": symbol
        }
        time.sleep(1.0)
        return requests.get(url, headers=headers, params=params)

    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/price"
    response = None
    try:
        response = do_call(token)
        try:
            res_json = response.json()
            if res_json.get("msg_cd") == "EGW00123" or "만료" in res_json.get("msg1", ""):
                print("[!] 토큰이 KIS 서버에서 만료되었습니다. 캐시를 비우고 재발급합니다.")
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
                new_token = get_access_token()
                response = do_call(new_token)
        except Exception:
            pass
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[-] 기초자산 시세 조회 API 호출 오류: {e}")
        if response is not None:
            print(f"[-] KIS API 상세 에러 응답: {response.text}")
        return None

def get_effective_premium(output):
    """
    호가 스프레드가 벌어지거나 거래량이 적은 경우 중간값(Mid Price)을 계산하고,
    차선책으로 현재가(last_price) 또는 전일정산가(sttl_price)를 반환합니다.
    """
    def safe_float(val):
        if not val:
            return 0.0
        try:
            return float(val.strip())
        except ValueError:
            return 0.0

    bid = safe_float(output.get('bid_price'))
    ask = safe_float(output.get('ask_price'))
    last = safe_float(output.get('last_price'))
    sttl = safe_float(output.get('sttl_price'))

    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        return mid

    if last > 0:
        return last

    if sttl > 0:
        return sttl

    return 0.0
