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

TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "2.0"))  # % drop from high (legacy, replaced by TRAILING_STOP_LEVELS)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))  # seconds
TELEGRAM_MIN_INTERVAL = 60  # seconds between repeated alerts per stock

# --- 프로그레시브 트레일링 스톱 (공격적 트레일링 only — 고정 타겟 없음) ---
# (고점 수익률 %, 보호선 %) — 고정 매도 타겟 없이 트레일링만으로 수익 실현
# 상승 추세가 계속되면 보호선이 올라가며 수익을 극대화
TRAILING_STOP_LEVELS = [
    (5.0, 4.0),   # +5% 찍으면 최소 +4% 보호
    (3.0, 2.2),   # +3% 찍으면 최소 +2.2% 보호
    (2.0, 1.5),   # +2% 찍으면 최소 +1.5% 보호
    (1.5, 1.0),   # +1.5% 찍으면 최소 +1.0% 보호 (수수료 후 순수익)
    (0.8, 0.4),   # +0.8% 찍으면 최소 +0.4% 보호 (수수료 커버)
]

# --- 멀티사이클 ---
MAX_CYCLES = int(os.getenv("MAX_CYCLES", "5"))
NO_NEW_ENTRY_AFTER = "10:30"   # 오전장 집중 — 이후 신규 진입 차단
FORCE_CLOSE_TIME = "15:10"     # 전량 강제 청산
CYCLE_COOLDOWN = int(os.getenv("CYCLE_COOLDOWN", "1200"))  # 사이클 간 쿨다운 (초)

# --- 손절 보호 (소자본 타이트 관리) ---
STOP_LOSS_GRACE_MINUTES = int(os.getenv("STOP_LOSS_GRACE_MINUTES", "2"))  # 진입 후 손절 유예 (분)
MIN_STOP_LOSS_PCT = float(os.getenv("MIN_STOP_LOSS_PCT", "1.2"))  # 최소 손절 거리 (%)
MAX_ENTRY_DEVIATION_PCT = float(os.getenv("MAX_ENTRY_DEVIATION_PCT", "3.0"))  # 현재가 vs 지정가 허용 괴리 (%)


# --- 오프닝 검증 (실시간 안전 필터) ---
OPENING_MAX_GAP_DOWN_PCT = float(os.getenv("OPENING_MAX_GAP_DOWN_PCT", "-2.0"))  # 갭다운 한도 (전일 대비 %)
OPENING_MAX_GAP_UP_PCT = float(os.getenv("OPENING_MAX_GAP_UP_PCT", "4.0"))  # 갭업 한도 — 초과 시 추격매수 방지 (%)
OPENING_MIN_VOLUME = int(os.getenv("OPENING_MIN_VOLUME", "5000"))  # 최소 거래량 (5분간)
# --- 시간 기반 청산 ---
MAX_HOLD_MINUTES = int(os.getenv("MAX_HOLD_MINUTES", "30"))

# --- 일일 리스크 관리 (보수적) ---
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "-1.5"))
DAILY_PROFIT_TARGET_PCT = float(os.getenv("DAILY_PROFIT_TARGET_PCT", "2.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "2"))  # 연패 시 당일 중단
MIN_CONFIDENCE_AFTER_LOSS = int(os.getenv("MIN_CONFIDENCE_AFTER_LOSS", "75"))  # 손절 후 다음 사이클 최소 신뢰도

MIN_REINVEST_CASH = int(os.getenv("MIN_REINVEST_CASH", "200000"))
REINVEST_CHECK_INTERVAL = int(os.getenv("REINVEST_CHECK_INTERVAL", "300"))

# --- 포지션 사이징 ---
MAX_PICKS = int(os.getenv("MAX_PICKS", "1"))            # 최대 동시 보유 종목 수
MAX_POSITION_PCT = int(os.getenv("MAX_POSITION_PCT", "70"))  # 종목당 자본 배분 한도 (%)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # "anthropic" or "openai"
TOTAL_CAPITAL = int(os.getenv("TOTAL_CAPITAL", "3000000"))
ANALYSIS_TIME = os.getenv("ANALYSIS_TIME", "09:10")
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
