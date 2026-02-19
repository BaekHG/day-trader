import 'package:flutter_dotenv/flutter_dotenv.dart';

abstract final class AppConstants {
  static const String appName = 'Day Trader';
  static const String appVersion = '1.0.0';

  static String get kisAppKey => dotenv.get('KIS_APP_KEY', fallback: '');
  static String get kisAppSecret => dotenv.get('KIS_APP_SECRET', fallback: '');
  static String get kisAccountNo => dotenv.get('KIS_ACCOUNT_NO', fallback: '');
  static const String kisApiBase = 'https://openapi.koreainvestment.com:9443';
  static const String kisWebSocket = 'ws://ops.koreainvestment.com:21000';

  static String get openaiApiKey => dotenv.get('OPENAI_API_KEY', fallback: '');
  static String get anthropicApiKey =>
      dotenv.get('ANTHROPIC_API_KEY', fallback: '');

  static String get alpacaApiKey => dotenv.get('ALPACA_API_KEY', fallback: '');
  static String get alpacaApiSecret =>
      dotenv.get('ALPACA_API_SECRET', fallback: '');

  static String get supabaseUrl => dotenv.get('SUPABASE_URL', fallback: '');
  static String get supabaseAnonKey =>
      dotenv.get('SUPABASE_ANON_KEY', fallback: '');
  static const String alpacaDataBase = 'https://data.alpaca.markets';
  static const String alpacaTradingBase = 'https://api.alpaca.markets';
  static const String alpacaStream = 'wss://stream.data.alpaca.markets/v2/iex';

  static const double defaultFeeRateKR = 0.00015;
  static const double defaultFeeRateUS = 0.0;
  static const double defaultTaxRateKR = 0.0023;
  static const double defaultTaxRateUS = 0.0;

  static const int maxWatchlistItems = 50;
  static const int defaultCandleCount = 100;
  static const Duration wsReconnectDelay = Duration(seconds: 3);
  static const Duration dataRefreshInterval = Duration(seconds: 5);
}
