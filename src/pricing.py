import math

def normal_cdf(x):
    """표준정규분포의 누적분포함수(CDF)"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def black_scholes(S, K, T, r, sigma, option_type):
    """
    블랙-숄즈 모형을 사용한 유러피언 옵션 가격 산출
    S: 기초자산 가격
    K: 행사가격
    T: 잔존만기 (연 단위, 예: 5일 = 5/365)
    r: 무위험 이자율 (예: 0.04)
    sigma: 변동성 (예: 0.30)
    option_type: 'Call' 또는 'Put'
    """
    if T <= 0:
        if option_type == "Call" or option_type.upper() == "C":
            return max(S - K, 0.0)
        else:
            return max(K - S, 0.0)
            
    if sigma <= 0:
        sigma = 0.0001
        
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    if option_type == "Call" or option_type.upper() == "C":
        return S * normal_cdf(d1) - K * math.exp(-r * T) * normal_cdf(d2)
    else:
        return K * math.exp(-r * T) * normal_cdf(-d2) - S * normal_cdf(-d1)

def implied_volatility(market_price, S, K, T, r, option_type):
    """
    이분법(Bisection method)을 활용해 시장가에 부합하는 내재변동성 역산
    """
    if T <= 0 or market_price <= 0:
        return 0.0
        
    opt_type_val = "Call" if (option_type == "Call" or option_type.upper() == "C") else "Put"
    intrinsic = max(S - K, 0.0) if opt_type_val == "Call" else max(K - S, 0.0)
    if market_price <= intrinsic:
        return 0.0
        
    low = 0.0
    high = 10.0  # 최대 1000% 변동성
    
    for _ in range(100):
        mid = (low + high) / 2.0
        price = black_scholes(S, K, T, r, mid, opt_type_val)
        if abs(price - market_price) < 1e-5:
            return mid
        if price < market_price:
            low = mid
        else:
            high = mid
    return low
