import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../models/bot_trade.dart';
import '../models/ai_analysis.dart';
import '../models/daily_report.dart';
import '../services/supabase/trading_data_service.dart';

final tradingDataServiceProvider = Provider<TradingDataService>((ref) {
  return TradingDataService(Supabase.instance.client);
});

final botTradesProvider = FutureProvider.autoDispose<List<BotTrade>>((
  ref,
) async {
  final service = ref.watch(tradingDataServiceProvider);
  return service.fetchTrades();
});

final aiAnalysesProvider = FutureProvider.autoDispose<List<AiAnalysis>>((
  ref,
) async {
  final service = ref.watch(tradingDataServiceProvider);
  return service.fetchAnalyses();
});

final dailyReportsProvider = FutureProvider.autoDispose<List<DailyReport>>((
  ref,
) async {
  final service = ref.watch(tradingDataServiceProvider);
  return service.fetchDailyReports();
});
