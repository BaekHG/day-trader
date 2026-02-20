# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

한국/미국 주식 데이트레이딩 포트폴리오 앱. 두 가지 컴포넌트로 구성:
- **Flutter 앱** (`lib/`) — 포트폴리오 추적, 차트, 관심종목, 매매일지 등 모바일 UI
- **Python 봇** (`monitor/`) — GCE에 배포되는 자동매매 시스템 (KIS API + Telegram + AI 분석)

## 빌드 및 실행 명령어

### Flutter 앱 (Dart >=3.11.0)

```bash
flutter pub get                # 의존성 설치
flutter analyze                # 정적 분석 (린트)
flutter test                   # 전체 테스트 실행
flutter test test/widget_test.dart  # 단일 테스트 실행
dart run build_runner build --delete-conflicting-outputs  # 코드 생성 (freezed, json_serializable, riverpod_generator)
flutter build ios --release    # iOS 빌드
flutter build web              # 웹 빌드
flutter build apk              # Android 빌드
flutter run                    # 디바이스에서 실행
```

### Python 봇 (`monitor/`)

```bash
cd monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### CI/CD

- GitHub Actions (`.github/workflows/deploy.yml`): `main` 브랜치에 `monitor/` 변경 push 시 GCE 자동 배포
- Flutter CI 파이프라인은 미구성

## 아키텍처

```
lib/
  core/
    constants/    # AppConstants (abstract final class), 열거형(enums)
    router/       # GoRouter 설정 — StatefulShellRoute.indexedStack 기반 탭 네비게이션
    theme/        # AppTheme, AppColors (abstract final class)
    utils/        # Formatters, 기술적 지표 계산
  models/         # Equatable 기반 데이터 클래스 (copyWith, fromJson, toJson)
  providers/      # Riverpod 상태 관리
  screens/        # 기능별 화면 폴더 (home/, trade/, watchlist/, chart/, journal/, daily_pick/)
  services/       # API 클라이언트 (kis/, alpaca/, naver/, openai/, claude/, supabase/)
  widgets/common/ # 재사용 가능한 UI 컴포넌트
monitor/          # Python 자동매매 시스템 (독립 실행)
```

### 라우팅 구조

GoRouter의 `StatefulShellRoute.indexedStack`으로 5개 탭 관리:
- `/home` — 홈 (포트폴리오 요약)
- `/watchlist` — 관심종목 (하위: `/watchlist/add`)
- `/trade` — 매매 (하위: `/trade/add`, `/trade/close/:tradeId`)
- `/journal` — 매매일지
- `/daily-pick` — 오늘의 종목
- `/chart/:symbol` — 차트 (탭 외부 독립 라우트)

### 상태 관리 — Riverpod

- `flutter_riverpod` 사용 (codegen 방식 아님)
- Provider 타입: `Provider`, `StateProvider`, `StateNotifierProvider`, `FutureProvider.family`, `StreamProvider`
- 화면은 `ConsumerWidget` 또는 `ConsumerStatefulWidget` 사용
- 루트 위젯은 `ProviderScope`로 감싸져 있음
- family 파라미터에 typedef record 사용: `typedef StockPriceParams = ({String symbol, Market market});`

### 서비스 (API 클라이언트)

- 외부 API별 하나의 클래스, Riverpod `Provider`로 주입
- 생성자에서 credentials 받아 `Dio` 인스턴스 내부 생성
- `dispose()` 메서드 노출, `ref.onDispose`에 연결
- API 호출 결과는 `Map<String, dynamic>` 반환 (파싱은 provider/model 레이어에서 처리)

### 외부 API 연동

| 서비스 | 용도 | 인증 |
|--------|------|------|
| KIS (한국투자증권) | 한국 주식 시세/주문 + WebSocket | `.env` — `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` |
| Alpaca | 미국 주식 시세/주문 + WebSocket | `.env` — `ALPACA_API_KEY`, `ALPACA_API_SECRET` |
| Naver Finance | 한국 주식 뉴스/데이터 스크래핑 | 인증 불필요 |
| OpenAI / Claude | AI 분석 | `.env` — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |
| Supabase | 인증 및 DB | `.env` — `SUPABASE_URL`, `SUPABASE_ANON_KEY` |

## 코드 스타일

### 클래스 및 모델 패턴

- **유틸리티/상수 클래스**: `abstract final class` 사용
- **모델**: `Equatable` 상속, `props` 구현, `copyWith()`, `fromJson()`, `toJson()` 포함
- **열거형**: `label` 필드와 const 생성자를 가진 enhanced enum 사용

### 네이밍 규칙

| 요소 | 규칙 | 예시 |
|------|------|------|
| 파일 | snake_case | `kis_api_service.dart` |
| 클래스 | PascalCase | `KisApiService` |
| 변수/메서드 | camelCase | `currentPrice`, `getAccessToken()` |
| Provider | camelCase + Provider 접미사 | `tradesProvider` |

### 임포트

파일별로 혼용되므로 해당 파일의 기존 스타일을 따를 것:
- 패키지 임포트 (`package:day_trader/...`) — screens, widgets에서 주로 사용
- 상대 경로 임포트 (`../core/...`) — models, providers, services에서 주로 사용
- 순서: `dart:` → `package:flutter/` → 서드파티 패키지 → 로컬

### 위젯

- `const` 생성자 + `super.key` 항상 사용
- 화면 내부 컴포넌트는 `_PrivateWidgetName` 형태의 private 클래스로 분리
- 색상은 `AppColors` 상수 직접 사용 (`Theme.of(context)` 대신)

### 에러 처리

- API 서비스에서 `DioException` 구체적 catch
- `Exception('설명: ${e.message}')` 형태로 throw
- 한국어 에러 메시지 사용 가능 (사용자 대면 문자열과 일치)

## 설정

- `.env` 파일로 시크릿 관리 (`flutter_dotenv`로 로딩). **절대 커밋 금지**
- `AppConstants`에서 `dotenv.get('KEY', fallback: '')`로 환경변수 참조
- 린트: `package:flutter_lints/flutter.yaml` (기본 규칙, 커스텀 오버라이드 없음)

## Python 봇 (`monitor/`) 규칙

- `config.py`에서 `os.getenv` + 기본값으로 설정 관리
- `logging` 모듈 + KST 타임존 포맷 사용
- `snake_case` (파일, 함수, 변수), `UPPER_CASE` (모듈 상수), `PascalCase` (클래스)
- `run_daily_cycle()`에서 번호 매긴 단계별 오케스트레이션
- 에러 복구: catch → 로그 → Telegram 알림 → graceful return
