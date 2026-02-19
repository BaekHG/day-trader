import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/constants/app_constants.dart';
import '../models/daily_pick.dart';
import '../services/kis/kis_api_service.dart';
import '../services/naver/naver_news_service.dart';
import '../services/claude/claude_service.dart';
import 'market_data_provider.dart';

export '../services/naver/naver_news_service.dart' show NewsArticle;
import 'stock_provider.dart';

final claudeServiceProvider = Provider<ClaudeService>((ref) {
  final service = ClaudeService(apiKey: AppConstants.anthropicApiKey);
  ref.onDispose(service.dispose);
  return service;
});

final naverNewsServiceProvider = Provider<NaverNewsService>((ref) {
  final service = NaverNewsService();
  ref.onDispose(service.dispose);
  return service;
});

final dailyPicksProvider =
    StateNotifierProvider<DailyPicksNotifier, AsyncValue<DailyPicksResult?>>((
      ref,
    ) {
      return DailyPicksNotifier(
        kisService: ref.watch(kisApiServiceProvider),
        claudeService: ref.watch(claudeServiceProvider),
        naverNewsService: ref.watch(naverNewsServiceProvider),
      );
    });

class DailyPicksNotifier extends StateNotifier<AsyncValue<DailyPicksResult?>> {
  DailyPicksNotifier({
    required this.kisService,
    required this.claudeService,
    required this.naverNewsService,
  }) : super(const AsyncValue.data(null));

  final KisApiService kisService;
  final ClaudeService claudeService;
  final NaverNewsService naverNewsService;

  DailyPicksResult? _cachedResult;

  DailyPicksResult? get cachedResult => _cachedResult;

  /// Run AI analysis using pre-loaded [MarketData] from the free tier.
  /// Only the OpenAI call costs money — market data is already available.
  Future<void> analyzeWithMarketData(MarketData marketData) async {
    state = const AsyncValue.loading();

    try {
      // Enrich top 10 volume stocks — 병렬 처리
      final topStocks = marketData.volumeRanking.take(10).toList();

      final enrichFutures = topStocks.map((stock) async {
        final code = stock['mksc_shrn_iscd'] as String? ?? '';
        if (code.isEmpty) return stock;

        final name = stock['hts_kor_isnm'] as String? ?? '';
        final newsKey = name.isNotEmpty ? name : code;
        final newsArticles = marketData.stockNews[newsKey] ?? [];
        final news = newsArticles.map((a) => a.title).toList();

        // 각 API를 개별 try-catch — 하나 실패해도 나머지는 살림
        List<Map<String, dynamic>> foreignData = [];
        try {
          foreignData = await kisService.getForeignInstitutionTotal(code);
        } catch (_) {}

        List<Map<String, dynamic>> dailyCandles = [];
        try {
          dailyCandles = await kisService.getDailyCandles(code);
        } catch (_) {}

        List<Map<String, dynamic>>? minuteCandles;
        if (marketData.isMarketOpen) {
          try {
            final raw = await kisService.getMinuteCandles(code, interval: '5');
            minuteCandles = raw.take(12).map((c) {
              return {
                'time': c['stck_cntg_hour'] ?? '',
                'open': c['stck_oprc'] ?? '',
                'high': c['stck_hgpr'] ?? '',
                'low': c['stck_lwpr'] ?? '',
                'close': c['stck_prpr'] ?? '',
                'volume': c['cntg_vol'] ?? '',
              };
            }).toList();
          } catch (_) {}
        }

        // 20일 고점 계산
        final recentCandles = dailyCandles.take(20).toList();
        double high20d = 0;
        for (final c in recentCandles) {
          final h = double.tryParse('${c['stck_hgpr'] ?? '0'}') ?? 0;
          if (h > high20d) high20d = h;
        }
        final currentPrice =
            double.tryParse('${stock['stck_prpr'] ?? '0'}') ?? 0;
        final positionFromHigh = high20d > 0
            ? ((currentPrice - high20d) / high20d) * 100
            : 0.0;

        // 최근 5일 일봉 요약 (AI용)
        final recentDays = recentCandles.take(5).map((c) {
          return {
            'date': c['stck_bsop_date'] ?? '',
            'open': c['stck_oprc'] ?? '',
            'high': c['stck_hgpr'] ?? '',
            'low': c['stck_lwpr'] ?? '',
            'close': c['stck_clpr'] ?? '',
            'volume': c['acml_vol'] ?? '',
            'trading_value': c['acml_tr_pbmn'] ?? '',
          };
        }).toList();

        return <String, dynamic>{
          ...stock,
          'foreign_institution': foreignData,
          'news_headlines': news,
          'recent_daily_candles': recentDays,
          'high_20d': high20d,
          'position_from_high': positionFromHigh,
          if (minuteCandles != null) 'minute_candles_5m': minuteCandles,
        };
      });

      final enrichedStocks = await Future.wait(enrichFutures);

      final result = await claudeService.analyzeDailyPicks(
        enrichedStocks: enrichedStocks.cast<Map<String, dynamic>>(),
        upRanking: marketData.upRanking,
        downRanking: marketData.downRanking,
        kospiIndex: marketData.kospiIndex,
        kosdaqIndex: marketData.kosdaqIndex,
        exchangeRate: marketData.exchangeRate,
        isMarketOpen: marketData.isMarketOpen,
      );

      _cachedResult = result;
      state = AsyncValue.data(result);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  /// Legacy analyze — fetches everything from scratch.
  Future<void> analyze() async {
    state = const AsyncValue.loading();

    try {
      // Step 1: Get rankings + KOSDAQ index (parallel)
      final results = await Future.wait([
        kisService.getVolumeRanking(),
        kisService.getFluctuationRanking(isUp: true),
        kisService.getFluctuationRanking(isUp: false),
        kisService.getKosdaqIndex(),
      ]);

      final volumeRanking = results[0] as List<Map<String, dynamic>>;
      final upRanking = results[1] as List<Map<String, dynamic>>;
      final downRanking = results[2] as List<Map<String, dynamic>>;
      final kosdaqIndex = results[3] as Map<String, dynamic>;

      // Step 2: For top 10 volume stocks, get supplementary data
      final topStocks = volumeRanking.take(10).toList();
      final enrichedStocks = <Map<String, dynamic>>[];

      for (final stock in topStocks) {
        final code = stock['mksc_shrn_iscd'] as String? ?? '';
        if (code.isEmpty) continue;

        try {
          final supplementary = await Future.wait<Object>([
            kisService.getForeignInstitutionTotal(code),
            naverNewsService.getStockNews(code),
          ]);

          final foreignData = supplementary[0] as List<Map<String, dynamic>>;
          final newsArticles = supplementary[1] as List<NewsArticle>;
          final news = newsArticles.map((a) => a.title).toList();

          enrichedStocks.add({
            ...stock,
            'foreign_institution': foreignData,
            'news_headlines': news,
          });
        } catch (_) {
          enrichedStocks.add(stock);
        }
      }

      final result = await claudeService.analyzeDailyPicks(
        enrichedStocks: enrichedStocks,
        upRanking: upRanking,
        downRanking: downRanking,
        kospiIndex: const {},
        kosdaqIndex: kosdaqIndex,
        exchangeRate: const {},
        isMarketOpen: true,
      );

      _cachedResult = result;
      state = AsyncValue.data(result);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}
