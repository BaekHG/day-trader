import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../models/bot_trade.dart';
import '../../models/ai_analysis.dart';
import '../../models/daily_report.dart';

class TradingDataService {
  final SupabaseClient _client;

  TradingDataService(this._client);

  Future<List<BotTrade>> fetchTrades({int limit = 50}) async {
    try {
      final response = await _client
          .from('trades')
          .select()
          .order('traded_at', ascending: false)
          .limit(limit);

      return (response as List)
          .map((json) => BotTrade.fromJson(json as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('Error fetching trades: $e');
      return [];
    }
  }

  Future<List<AiAnalysis>> fetchAnalyses({int limit = 20}) async {
    try {
      final response = await _client
          .from('ai_analyses')
          .select()
          .order('analyzed_at', ascending: false)
          .limit(limit);

      return (response as List)
          .map((json) => AiAnalysis.fromJson(json as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('Error fetching analyses: $e');
      return [];
    }
  }

  Future<List<DailyReport>> fetchDailyReports({int limit = 30}) async {
    try {
      final response = await _client
          .from('daily_reports')
          .select()
          .gt('total_trades', 0)
          .order('report_date', ascending: false)
          .limit(limit);

      return (response as List)
          .map((json) => DailyReport.fromJson(json as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('Error fetching daily reports: $e');
      return [];
    }
  }
}
