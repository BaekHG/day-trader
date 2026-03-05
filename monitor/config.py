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
KIS_CANO = KIS_ACCOUNT_NO[:8]          # KIS API splits account: first 8 digits
KIS_ACNT_PRDT_CD = KIS_ACCOUNT_NO[8:]   # KIS API splits account: last 2 digits
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

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
]

# --- 멀티사이클 ---
MAX_CYCLES = int(os.getenv("MAX_CYCLES", "10"))
NO_NEW_ENTRY_AFTER = os.getenv("NO_NEW_ENTRY_AFTER", "10:30")  # 10:30 이후 신규 진입 차단
FORCE_CLOSE_TIME = "15:10"     # 손실 종목 강제 청산 (수익 종목은 트레일링 유지)
FINAL_CLOSE_TIME = "15:20"    # 전량 강제 청산 (체결 여유 10분 확보)

# --- 조건부 오버나이트 홀딩 ---
OVERNIGHT_ENABLED = os.getenv("OVERNIGHT_ENABLED", "true").lower() == "true"
OVERNIGHT_MIN_PROFIT_PCT = float(os.getenv("OVERNIGHT_MIN_PROFIT_PCT", "5.0"))  # 수익 +5% 이상이면 홀딩 후보
OVERNIGHT_MIN_HIGH_RATIO = float(os.getenv("OVERNIGHT_MIN_HIGH_RATIO", "0.95"))  # 고점 대비 95% 이상 유지 중이어야 홀딩
OVERNIGHT_MORNING_CHECK = os.getenv("OVERNIGHT_MORNING_CHECK", "09:05")  # 다음날 갭 체크 시각
OVERNIGHT_GAP_DOWN_SELL_PCT = float(os.getenv("OVERNIGHT_GAP_DOWN_SELL_PCT", "-2.0"))  # 갭다운 -2% 이하면 즉시 매도
CYCLE_COOLDOWN = int(os.getenv("CYCLE_COOLDOWN", "180"))  # 사이클 간 쿨다운 (초)

# --- 오후 전략: 눌림목 반등 매매 (10:30~14:00) ---
AFTERNOON_ENABLED = os.getenv("AFTERNOON_ENABLED", "true").lower() == "true"  # False→True!
AFTERNOON_PHASE_START = os.getenv("AFTERNOON_PHASE_START", "10:30")  # 11:00→10:30
AFTERNOON_PHASE_END = os.getenv("AFTERNOON_PHASE_END", "14:00")  # 14:30→14:00
AFTERNOON_MAX_CYCLES = int(os.getenv("AFTERNOON_MAX_CYCLES", "20"))  # 3→20: 14:00까지 계속 스캔 (10분 × 20 = 200분)
AFTERNOON_MAX_POSITION_PCT = int(os.getenv("AFTERNOON_MAX_POSITION_PCT", "80"))  # 30→80%: 오전과 동일
AFTERNOON_MAX_HOLD_MINUTES = int(os.getenv("AFTERNOON_MAX_HOLD_MINUTES", "20"))
AFTERNOON_MIN_STOP_LOSS_PCT = float(os.getenv("AFTERNOON_MIN_STOP_LOSS_PCT", "1.5"))
AFTERNOON_CYCLE_COOLDOWN = int(os.getenv("AFTERNOON_CYCLE_COOLDOWN", "180"))  # 600→180초(3분)
AFTERNOON_HARD_FILTER_CHANGE_MIN = float(os.getenv("AFTERNOON_HARD_FILTER_CHANGE_MIN", "0.5"))  # 오후 재투자 등락률 하한
AFTERNOON_HARD_FILTER_CHANGE_MAX = float(os.getenv("AFTERNOON_HARD_FILTER_CHANGE_MAX", "8.0"))  # 오후 재투자 등락률 상한 (오전 6→8%)
MORNING_HARD_FILTER_CHANGE_MAX = float(os.getenv("MORNING_HARD_FILTER_CHANGE_MAX", "8.0"))  # 오전 등락률 상한 (6→8%, 오후와 통일)
HARD_FILTER_MAX_CHANGE = float(os.getenv("HARD_FILTER_MAX_CHANGE", "15.0"))  # 급등 필터 상한 (10→15%, 강세장 대응)
# 눌림목 전략 전용 파라미터
PULLBACK_MIN_MORNING_CHANGE = float(os.getenv("PULLBACK_MIN_MORNING_CHANGE", "5.0"))  # 8→5%: 더 많은 종목 대상
PULLBACK_RETRACEMENT_MIN = float(os.getenv("PULLBACK_RETRACEMENT_MIN", "0.20"))  # 30→20%: 살짝 눈림도 매수
PULLBACK_RETRACEMENT_MAX = float(os.getenv("PULLBACK_RETRACEMENT_MAX", "0.65"))  # 60→65%: 조금 더 여유
PULLBACK_TARGET_PCT = float(os.getenv("PULLBACK_TARGET_PCT", "3.0"))  # 고정 목표 +3%
PULLBACK_STOP_LOSS_PCT = float(os.getenv("PULLBACK_STOP_LOSS_PCT", "1.5"))  # 손절 -1.5%
PULLBACK_BOUNCE_CONFIRM_PCT = float(os.getenv("PULLBACK_BOUNCE_CONFIRM_PCT", "0.3"))  # 0.5→0.3%: 매수 진입 빨라짐
PULLBACK_MAX_ENTRIES = int(os.getenv("PULLBACK_MAX_ENTRIES", "3"))  # 1→3회: 눌림목 최대 3번 진입

MIN_STOP_LOSS_PCT = float(os.getenv("MIN_STOP_LOSS_PCT", "1.2"))
MAX_ENTRY_DEVIATION_PCT = float(os.getenv("MAX_ENTRY_DEVIATION_PCT", "3.0"))  # 현재가 vs 지정가 허용 괴리 (%)


# --- 오프닝 검증 (실시간 안전 필터) ---
OPENING_MAX_GAP_DOWN_PCT = float(os.getenv("OPENING_MAX_GAP_DOWN_PCT", "-2.0"))  # 갭다운 한도 (전일 대비 %)
OPENING_MAX_GAP_UP_PCT = float(os.getenv("OPENING_MAX_GAP_UP_PCT", "6.0"))  # 갭업 한도 — 초과 시 추격매수 방지 (%)
OPENING_MIN_VOLUME = int(os.getenv("OPENING_MIN_VOLUME", "5000"))  # 최소 거래량 (5분간)
# --- 시간 기반 청산 ---
MAX_HOLD_MINUTES = int(os.getenv("MAX_HOLD_MINUTES", "30"))

# --- 일일 리스크 관리 (보수적) ---
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "-1.5"))
DAILY_PROFIT_TARGET_PCT = float(os.getenv("DAILY_PROFIT_TARGET_PCT", "5.0"))  # 일일 누적 수익 상한 (안전망)
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "4"))  # 2→4: 공격적 전략 — 4연패까지 허용
MIN_CONFIDENCE_AFTER_LOSS = int(os.getenv("MIN_CONFIDENCE_AFTER_LOSS", "75"))  # 손절 후 다음 사이클 최소 신뢰도

# --- 사이클별 분기 전략 ---
FIRST_PROFIT_STOP_PCT = float(os.getenv("FIRST_PROFIT_STOP_PCT", "3.0"))  # 단일 거래 +3% 이상 → 당일 종료
AFTER_LOSS_MIN_SCORE = int(os.getenv("AFTER_LOSS_MIN_SCORE", "65"))  # 손절 후 다음 진입 최소 모멘텀 스코어

MIN_REINVEST_CASH = int(os.getenv("MIN_REINVEST_CASH", "200000"))
REINVEST_CHECK_INTERVAL = int(os.getenv("REINVEST_CHECK_INTERVAL", "300"))

# --- 포지션 사이징 ---
MAX_PICKS = int(os.getenv("MAX_PICKS", "1"))            # 최대 동시 보유 종목 수
MAX_POSITION_PCT = int(os.getenv("MAX_POSITION_PCT", "95"))  # 종목당 자본 배분 한도 (%) — 올인

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # "anthropic" or "openai"
TOTAL_CAPITAL = int(os.getenv("TOTAL_CAPITAL", "3000000"))
ANALYSIS_TIME = os.getenv("ANALYSIS_TIME", "09:02")
BUY_CONFIRM_TIMEOUT = int(os.getenv("BUY_CONFIRM_TIMEOUT", "900"))

ENRICHMENT_POOL_SIZE = int(os.getenv("ENRICHMENT_POOL_SIZE", "15"))  # 심층 분석할 후보 종목 수

DUAL_SOURCING_ENABLED = os.getenv("DUAL_SOURCING_ENABLED", "true").lower() == "true"
DUAL_SOURCING_MIN_PRICE = int(os.getenv("DUAL_SOURCING_MIN_PRICE", "1000"))
DUAL_SOURCING_MIN_VOLUME = int(os.getenv("DUAL_SOURCING_MIN_VOLUME", "100000"))
DUAL_SOURCING_MIN_MARKET_CAP = int(os.getenv("DUAL_SOURCING_MIN_MARKET_CAP", "0"))  # 시총 필터 비활성화 — 거래대금 필터로 유동성 확보

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

# --- 모멘텀 전략 (아이티켐형 급등주 단타) ---
MOMENTUM_ENABLED = os.getenv("MOMENTUM_ENABLED", "true").lower() == "true"
MOMENTUM_RATE_MIN = float(os.getenv("MOMENTUM_RATE_MIN", "5.0"))    # 소싱 최소 등락률 (%)
MOMENTUM_RATE_MAX = float(os.getenv("MOMENTUM_RATE_MAX", "29.9"))   # 소싱 최대 (상한가 미만)
MOMENTUM_MIN_PRICE = int(os.getenv("MOMENTUM_MIN_PRICE", "2000"))   # 동전주 제외
MOMENTUM_MIN_VOLUME = int(os.getenv("MOMENTUM_MIN_VOLUME", "200000"))  # 최소 거래량 20만주
MOMENTUM_PREV_DAY_MAX_CHANGE = float(os.getenv("MOMENTUM_PREV_DAY_MAX_CHANGE", "12.0"))  # 전일 +12%↑ → 연속급등 제외
MOMENTUM_MIN_HIGH_RATIO = float(os.getenv("MOMENTUM_MIN_HIGH_RATIO", "0.93"))  # 고점 대비 93% 이상 유지
MOMENTUM_VOL_SUSTAIN_RATIO = float(os.getenv("MOMENTUM_VOL_SUSTAIN_RATIO", "0.5"))  # 0.7→0.5: 5분봉 거래량 변동 크므로 50%까지 허용
MOMENTUM_ENTRY_START = os.getenv("MOMENTUM_ENTRY_START", "09:02")   # 모멘텀 진입 시작
MOMENTUM_ENTRY_END = os.getenv("MOMENTUM_ENTRY_END", "14:30")       # 모멘텀 진입 종료
MOMENTUM_STOP_LOSS_PCT = float(os.getenv("MOMENTUM_STOP_LOSS_PCT", "2.5"))  # 모멘텀 손절 기본값
MOMENTUM_MIN_SCORE = int(os.getenv("MOMENTUM_MIN_SCORE", "40"))  # 50→40: 한국첨단소재(35.2) 같은 유효 후보 놓치지 않도록
MOMENTUM_STOP_LOSS_BY_SCORE = [
    (70, 3.5),   # 스코어 70+ → -3.5% (확신 높음, 버틴다)
    (50, 2.5),   # 스코어 50~69 → -2.5% (기본)
]
MOMENTUM_TIME_STOP_MINUTES = int(os.getenv("MOMENTUM_TIME_STOP_MINUTES", "20"))  # 20분 횡보 시 청산
MOMENTUM_TIME_STOP_MIN_PROFIT = float(os.getenv("MOMENTUM_TIME_STOP_MIN_PROFIT", "0.5"))  # 20분 후 +0.5% 미만이면 청산
MOMENTUM_DAILY_MAX_LOSSES = int(os.getenv("MOMENTUM_DAILY_MAX_LOSSES", "6"))  # 2→6: 오전+오후 하루 종일 매매 — 손절 6회까지 허용
MOMENTUM_OPTIMAL_CHANGE_MIN = float(os.getenv("MOMENTUM_OPTIMAL_CHANGE_MIN", "8.0"))  # 스코어링: 최적 등락률 하한
MOMENTUM_OPTIMAL_CHANGE_MAX = float(os.getenv("MOMENTUM_OPTIMAL_CHANGE_MAX", "15.0"))  # 스코어링: 최적 등락률 상한
MOMENTUM_VOL_GATE = float(os.getenv("MOMENTUM_VOL_GATE", "1.5"))  # 2.0→1.5: 장 초반 전일대비 2.7배 요구는 과도 (1.65배로 완화)

# 모멘텀 트레일링 스톱 (공격적 — 큰 수익 추구, +5% 전에는 트레일링 없음)
MOMENTUM_TRAILING_STOP_LEVELS = [
    (15.0, 11.0),  # +15% 도달 → +11% 확보 (4% 숨 여유)
    (10.0, 7.0),   # +10% 도달 → +7.0% 확보 (3% 숨 여유)
    (7.0, 4.0),    # +7%  도달 → +4.0% 확보 (3% 숨 여유)
    (5.0, 2.0),    # +5%  도달 → +2.0% 확보 (3% 숨 여유)
    # +5% 미만: 트레일링 없음 → 초기 손절(-2.5%)로만 관리
]

# --- 단계적 매도 (슬리피지 방지) ---
# 지정가(높은가격) → 지정가(현재가) → 시장가 순서로 시도
SELL_STEP_DOWN = os.getenv("SELL_STEP_DOWN", "true").lower() == "true"
SELL_LIMIT_OFFSET_PCT = float(os.getenv("SELL_LIMIT_OFFSET_PCT", "0.3"))  # 1단계: 현재가 + 0.3%
SELL_STEP_WAIT_SEC = int(os.getenv("SELL_STEP_WAIT_SEC", "3"))  # 각 단계 대기 시간 (초)

# --- 후반 시간대 (10:30 이후) 보수적 파라미터 ---
LATE_SESSION_START = "10:30"
LATE_SESSION_POSITION_PCT = 40
LATE_SESSION_MIN_SCORE = 65
LATE_SESSION_STOP_LOSS_PCT = 2.0
LATE_SESSION_REQUIRE_PROFIT = os.getenv("LATE_SESSION_REQUIRE_PROFIT", "false").lower() == "true"

# --- 장 초반 빠른 진입 모드 (09:00~09:10) ---
# 초반 10분간 모멘텀 진입 조건 완화: 낮은 스코어/등락률도 진입 허용
EARLY_MORNING_MINUTES = int(os.getenv("EARLY_MORNING_MINUTES", "20"))  # 10→20분: 09:14 한국첨단소재 35.2점 놓친 사례 반영
EARLY_MOMENTUM_RATE_MIN = float(os.getenv("EARLY_MOMENTUM_RATE_MIN", "3.0"))  # 소싱 등락률 하한 3% (평시 5%)
EARLY_MOMENTUM_MIN_SCORE = int(os.getenv("EARLY_MOMENTUM_MIN_SCORE", "35"))  # 최소 스코어 35 (평시 50)
EARLY_MOMENTUM_VOL_GATE = float(os.getenv("EARLY_MOMENTUM_VOL_GATE", "1.0"))  # 1.5→1.0: 초반 거래량 불안정, 최소한만 확인
EARLY_CYCLE_COOLDOWN = int(os.getenv("EARLY_CYCLE_COOLDOWN", "90"))  # 쿨다운 90초 (평시 180초)
EARLY_FALLBACK_OPEN_TOLERANCE = float(os.getenv("EARLY_FALLBACK_OPEN_TOLERANCE", "0.005"))  # 시가 대비 0.5% 하회 허용
EARLY_SKIP_PULLBACK_SCORE = int(os.getenv("EARLY_SKIP_PULLBACK_SCORE", "40"))  # 이 스코어 이상이면 풀백 없이 즉시 진입
EARLY_SKIP_PULLBACK_HIGH_RATIO = float(os.getenv("EARLY_SKIP_PULLBACK_HIGH_RATIO", "0.97"))  # 고점 대비 97% 이상일 때만
MOMENTUM_SKIP_PULLBACK_SCORE = int(os.getenv("MOMENTUM_SKIP_PULLBACK_SCORE", "60"))  # 시간 무관: 이 스코어 이상이면 풀백 체크 생략

MARKET_INDEX_BLOCK_PCT = float(os.getenv("MARKET_INDEX_BLOCK_PCT", "-2.5"))  # KOSDAQ 하락 시 모멘텀 차단 기준 (%)
MARKET_INDEX_OVERRIDE_SCORE = int(os.getenv("MARKET_INDEX_OVERRIDE_SCORE", "70"))  # 이 스코어 이상이면 차단 무시


# --- 불장 모드 (Market Boost) — 시장 강세/호재 뉴스 감지 시 공격적 파라미터 ---
BOOST_ENABLED = os.getenv("BOOST_ENABLED", "true").lower() == "true"
SENTIMENT_TIME = os.getenv("SENTIMENT_TIME", "08:55")  # 장 시작 5분 전 뉴스 센티먼트 분석
BOOST_KOSPI_THRESHOLD = float(os.getenv("BOOST_KOSPI_THRESHOLD", "1.0"))  # KOSPI +1%↑ → 부스트 후보
BOOST_KOSDAQ_THRESHOLD = float(os.getenv("BOOST_KOSDAQ_THRESHOLD", "1.5"))  # KOSDAQ +1.5%↑ → 부스트 후보
BOOST_CONFIRM_MINUTES = int(os.getenv("BOOST_CONFIRM_MINUTES", "8"))  # 09:02 감지 후 8분간 유지 확인
BOOST_MAX_POSITION_PCT = int(os.getenv("BOOST_MAX_POSITION_PCT", "95"))  # 포지션 95%
BOOST_MOMENTUM_MIN_SCORE = int(os.getenv("BOOST_MOMENTUM_MIN_SCORE", "35"))  # 최소 스코어 35
BOOST_STOP_LOSS_PCT = float(os.getenv("BOOST_STOP_LOSS_PCT", "3.5"))  # 손절 -3.5% (숨 여유)
BOOST_FIRST_PROFIT_STOP_PCT = float(os.getenv("BOOST_FIRST_PROFIT_STOP_PCT", "5.0"))  # +5% 이상 시 종료
BOOST_NO_NEW_ENTRY_AFTER = os.getenv("BOOST_NO_NEW_ENTRY_AFTER", "13:00")  # 오후 1시까지 신규 진입 허용
BOOST_CYCLE_COOLDOWN = int(os.getenv("BOOST_CYCLE_COOLDOWN", "90"))  # 쿨다운 90초
BOOST_DAILY_PROFIT_TARGET_PCT = float(os.getenv("BOOST_DAILY_PROFIT_TARGET_PCT", "8.0"))  # 일일 수익 상한 8%
BOOST_THEME_SCORE_BONUS = float(os.getenv("BOOST_THEME_SCORE_BONUS", "1.2"))  # 수혜테마 종목 스코어 +20%
BOOST_THEME_SCORE_PENALTY = float(os.getenv("BOOST_THEME_SCORE_PENALTY", "0.85"))  # 피해테마 종목 스코어 -15%
# 불장 모드 트레일링 스탑 (넓은 숨 여유 — 최대한 늦게, 높을 때 매도)
BOOST_MOMENTUM_TRAILING_STOP_LEVELS = [
    (15.0, 12.0),   # +15% 찍으면 최소 +12% 확보 (3% 여유)
    (10.0, 7.0),    # +10% 찍으면 최소 +7% 확보 (3% 여유)
    (7.0, 4.0),     # +7%  찍으면 최소 +4% 확보 (3% 여유)
    (5.0, 2.5),     # +5%  찍으면 최소 +2.5% 확보 (2.5% 여유)
    (3.0, 0.5),     # +3%  찍으면 최소 +0.5% 확보 (수수료 커버)
]
BOOST_TIME_STOP_MINUTES = int(os.getenv("BOOST_TIME_STOP_MINUTES", "40"))  # 횡보 청산 40분 (평시 20분)
BOOST_TIME_STOP_MIN_PROFIT = float(os.getenv("BOOST_TIME_STOP_MIN_PROFIT", "0.3"))  # 40분 후 +0.3% 미만이면 청산

# --- 거래대금 필터 (가격대별 차등) ---
# 저가주는 거래대금 기준을 낮춰 아이티켐(1~2만원대) 같은 중소형 급등주도 포착
MIN_TRADING_VALUE_TIERS = [
    (50000, 5_000_000_000),   # 5만원 이상: 50억
    (20000, 3_000_000_000),   # 2~5만원: 30억
    (0,     1_000_000_000),   # 2만원 이하: 10억
]

# --- Dry-run 모의투자 모드 ---
# --dry-run 플래그로 활성화: 전체 파이프라인 실행하되 실제 주문 없이 시뮬레이션
DRY_RUN = False
