# AGENTS.md — day-trader

## Project Overview

Day trading portfolio app for Korean & US stocks. Two components:
- **Flutter app** (`lib/`) — Mobile UI for portfolio tracking, charting, watchlist, trade journaling
- **Python bot** (`monitor/`) — Automated day-trading system deployed on GCE (KIS API + Telegram + OpenAI analysis)

## Build & Run Commands

### Flutter App (Dart >=3.11.0)

```bash
# Install dependencies
flutter pub get

# Static analysis (lint)
flutter analyze

# Run all tests
flutter test

# Run a single test file
flutter test test/widget_test.dart

# Code generation (freezed, json_serializable, riverpod_generator)
dart run build_runner build --delete-conflicting-outputs

# Build
flutter build ios --release
flutter build web
flutter build apk

# Run on device
flutter run
```

### Python Bot (`monitor/`)

```bash
cd monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### CI/CD

- GitHub Actions (`.github/workflows/deploy.yml`): auto-deploys `monitor/` to GCE on push to `main`
- No Flutter CI pipeline configured

## Architecture

```
lib/
  core/
    constants/    # AppConstants (abstract final class), enums
    router/       # GoRouter config (go_router)
    theme/        # AppTheme, AppColors (abstract final classes)
    utils/        # Formatters, technical indicators
  models/         # Data classes (Equatable-based)
  providers/      # Riverpod state management
  screens/        # Feature-based screen folders (home/, trade/, watchlist/, etc.)
  services/       # API clients organized by provider (kis/, alpaca/, naver/, openai/, supabase/)
  widgets/common/ # Reusable UI components
monitor/          # Python automated trading system (standalone)
```

## State Management — Riverpod

- Uses `flutter_riverpod` (not riverpod_annotation codegen in practice)
- Provider types used: `Provider`, `StateProvider`, `StateNotifierProvider`, `FutureProvider.family`, `StreamProvider`
- Screens use `ConsumerWidget` or `ConsumerStatefulWidget`
- Root widget wrapped in `ProviderScope`
- Typedef records for family parameters: `typedef StockPriceParams = ({String symbol, Market market});`

## Code Style

### Formatting

- Dart standard formatting (`dart format`)
- Trailing commas on all multi-line argument lists and collections
- Single quotes for strings (Dart default)
- Lines generally under 100 chars but no strict enforced limit

### Imports

Mixed style — follow whichever is used in the file being edited:
- Package imports (`package:day_trader/...`) in screens and widgets
- Relative imports (`../core/...`) in models, providers, and services
- Order: `dart:` → `package:flutter/` → third-party packages → local packages/relative

### Naming Conventions

| Element               | Convention     | Example                         |
|-----------------------|----------------|---------------------------------|
| Files                 | snake_case     | `kis_api_service.dart`          |
| Classes               | PascalCase     | `KisApiService`, `TradeScreen`  |
| Private classes       | _PascalCase    | `_HomeScreenState`, `_MiniStat` |
| Variables / methods   | camelCase       | `currentPrice`, `getAccessToken()` |
| Constants             | camelCase       | `maxWatchlistItems`, `defaultFeeRateKR` |
| Enums                 | PascalCase type, camelCase values | `Market.kr`, `ChartInterval.min5` |
| Typedefs              | PascalCase     | `StockPriceParams`              |
| Providers             | camelCase + Provider suffix | `tradesProvider`, `currentPriceProvider` |

### Classes & Models

- **Utility/constant classes**: Use `abstract final class` (not instantiable, not extendable)
  ```dart
  abstract final class AppConstants { ... }
  abstract final class Formatters { ... }
  ```
- **Models**: Extend `Equatable`, implement `props`, include `copyWith()`, `fromJson()`, `toJson()`
  ```dart
  class Stock extends Equatable {
    const Stock({ required this.symbol, ... });
    Stock copyWith({ ... }) => Stock( ... );
    factory Stock.fromJson(Map<String, dynamic> json) => ...;
    Map<String, dynamic> toJson() => { ... };
    @override
    List<Object?> get props => [ ... ];
  }
  ```
- **Enums**: Enhanced enums with `label` field and const constructor
  ```dart
  enum Market {
    kr('Korea', 'KRW'),
    us('US', 'USD');
    const Market(this.label, this.currency);
    final String label;
    final String currency;
  }
  ```

### Widgets

- Use `const` constructors with `super.key` everywhere
- Private widget classes (`_WidgetName`) for screen-internal components
- Prefer composition over inheritance — break screens into small private widgets
- `ConsumerWidget` for stateless + Riverpod, `ConsumerStatefulWidget` for stateful + Riverpod
- Use `AppColors` constants directly (not `Theme.of(context)`) for colors in most cases

### Error Handling

- Catch `DioException` specifically in API service methods
- Throw `Exception('descriptive message: ${e.message}')` with context
- Korean-language error messages are acceptable (matches user-facing strings)
- Empty catch blocks only for non-critical operations (e.g., watchlist price fetch skip)
- `try/catch` at initialization boundaries (main.dart)

### Services (API Clients)

- One class per external API, injected via Riverpod `Provider`
- Constructor takes credentials, creates `Dio` instance internally
- Expose `dispose()` method, wire to `ref.onDispose`
- Return raw `Map<String, dynamic>` from API calls (parsing done at provider/model layer)

## Configuration

- `.env` file for secrets (loaded via `flutter_dotenv`). **Never commit `.env`**
- `AppConstants` reads env vars with `dotenv.get('KEY', fallback: '')`
- Linting: `package:flutter_lints/flutter.yaml` (standard rules, no custom overrides)
- `analysis_options.yaml` — default Flutter lint rules

## Python Bot (`monitor/`) Conventions

- Config via `config.py` (reads env vars with `os.getenv` + defaults)
- Standard library `logging` with KST timezone formatting
- No type hints enforced; functions use docstrings sparingly
- `snake_case` for everything (files, functions, variables)
- `UPPER_CASE` for module-level constants
- Classes: `PascalCase` (`KISClient`, `TelegramBot`, `AIAnalyzer`)
- Main orchestration in `run_daily_cycle()` with numbered phases
- Error recovery: catch + log + Telegram notification + graceful return

## Key Dependencies

### Flutter
- `flutter_riverpod` — state management
- `go_router` — declarative routing
- `dio` — HTTP client
- `supabase_flutter` — auth & database
- `fl_chart` — charting
- `hive_flutter` — local storage
- `equatable` — value equality for models
- `freezed_annotation` / `json_annotation` — code generation (dev)
- `google_fonts` — Inter font family

### Python
- `requests` — HTTP
- `python-dotenv` — env loading
- `pytz` — timezone handling
