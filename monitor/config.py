import os
from dotenv import load_dotenv

load_dotenv()

KIS_APP_KEY = os.getenv(
    "KIS_APP_KEY",
    "PSfuCOiUYoVpbzRxsJDrM7gZUnxOXHZTsbVN",
)
KIS_APP_SECRET = os.getenv(
    "KIS_APP_SECRET",
    "zZmagjvaedjMO1dUOeTdKT/ZQbVOdpy5I3eRtAUQJrOW4p3Lhq3PYFhw8oZWFYRhGmfrYFZoj5D/"
    "XtRzemBuW6e5g5FlxWM6JGP4+hTVxloCO+9d7o8iUbGelWnO/+WL/kc5stM537aMQ3qmHDLEuMnj2fABtndTQAwAXnOpfnCbWj03X3k=",
)
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "6864747501")
KIS_CANO = "68647475"       # KIS API splits account: first 8 digits
KIS_ACNT_PRDT_CD = "01"     # KIS API splits account: last 2 digits
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8450232682:AAH_xAmcPG8uoOdcnEH-nD5zbaFcxJg-Ph4")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6250731705")

TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "2.0"))  # % drop from high
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))  # seconds
TELEGRAM_MIN_INTERVAL = 60  # seconds between repeated alerts per stock

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "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",
)
TOTAL_CAPITAL = int(os.getenv("TOTAL_CAPITAL", "3000000"))
ANALYSIS_TIME = os.getenv("ANALYSIS_TIME", "08:40")
BUY_CONFIRM_TIMEOUT = int(os.getenv("BUY_CONFIRM_TIMEOUT", "900"))

NAVER_FALLBACK_STOCKS = [
    "005930", "000660", "035720", "035420", "051910",
    "006400", "068270", "028260", "105560", "003670",
]
NAVER_FALLBACK_NAMES = {
    "005930": "삼성전자", "000660": "SK하이닉스", "035720": "카카오",
    "035420": "NAVER", "051910": "LG화학", "006400": "삼성SDI",
    "068270": "셀트리온", "028260": "삼성물산", "105560": "KB금융",
    "003670": "포스코퓨처엠",
}

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE_DIR, "positions.json")
TOKEN_CACHE_FILE = os.path.join(BASE_DIR, ".token_cache.json")
TRADES_FILE = os.path.join(BASE_DIR, "trades_today.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
VERSION = "1.0.0"
