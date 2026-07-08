import os
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

CACHE_FILE = os.path.join("data", ".token_cache.json")
MASTER_FILE = os.path.join("data", "fostkcode.mst")
MASTER_ZIP = os.path.join("data", "fostkcode.mst.zip")
MASTER_URL = "https://new.real.download.dws.co.kr/common/master/fostkcode.mst.zip"
