import 'package:equatable/equatable.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/kis/kis_api_service.dart';
import '../services/naver/naver_finance_service.dart';
import '../services/naver/naver_news_service.dart';
import 'daily_pick_provider.dart';
import 'stock_provider.dart';

export '../services/naver/naver_news_service.dart' show NewsArticle;

/// Free market data that loads automatically when the 데일리픽 tab opens.
class MarketData extends Equatable {
  final Map<String, dynamic> kospiIndex;
  final Map<String, dynamic> kosdaqIndex;
  final Map<String, dynamic> exchangeRate;
  final List<Map<String, dynamic>> volumeRanking;
  final List<Map<String, dynamic>> upRanking;
  final List<Map<String, dynamic>> downRanking;
  final Map<String, List<NewsArticle>> stockNews;
  final bool isMarketOpen;

  const MarketData({
    required this.kospiIndex,
    required this.kosdaqIndex,
    required this.exchangeRate,
    required this.volumeRanking,
    required this.upRanking,
    required this.downRanking,
    required this.stockNews,
    this.isMarketOpen = false,
  });

  MarketData copyWith({
    Map<String, dynamic>? kospiIndex,
    Map<String, dynamic>? kosdaqIndex,
    Map<String, dynamic>? exchangeRate,
    List<Map<String, dynamic>>? volumeRanking,
    List<Map<String, dynamic>>? upRanking,
    List<Map<String, dynamic>>? downRanking,
    Map<String, List<NewsArticle>>? stockNews,
    bool? isMarketOpen,
  }) {
    return MarketData(
      kospiIndex: kospiIndex ?? this.kospiIndex,
      kosdaqIndex: kosdaqIndex ?? this.kosdaqIndex,
      exchangeRate: exchangeRate ?? this.exchangeRate,
      volumeRanking: volumeRanking ?? this.volumeRanking,
      upRanking: upRanking ?? this.upRanking,
      downRanking: downRanking ?? this.downRanking,
      stockNews: stockNews ?? this.stockNews,
      isMarketOpen: isMarketOpen ?? this.isMarketOpen,
    );
  }

  /// Top 10 volume stocks used for display & enrichment.
  List<Map<String, dynamic>> get topVolumeStocks =>
      volumeRanking.take(10).toList();

  @override
  List<Object?> get props => [
    kospiIndex,
    kosdaqIndex,
    exchangeRate,
    volumeRanking,
    upRanking,
    downRanking,
    stockNews,
    isMarketOpen,
  ];
}

final naverFinanceServiceProvider = Provider<NaverFinanceService>((ref) {
  final service = NaverFinanceService();
  ref.onDispose(service.dispose);
  return service;
});

final marketDataProvider =
    StateNotifierProvider<MarketDataNotifier, AsyncValue<MarketData?>>((ref) {
      return MarketDataNotifier(
        kisService: ref.watch(kisApiServiceProvider),
        naverFinanceService: ref.watch(naverFinanceServiceProvider),
        naverNewsService: ref.watch(naverNewsServiceProvider),
      );
    });

class MarketDataNotifier extends StateNotifier<AsyncValue<MarketData?>> {
  MarketDataNotifier({
    required this.kisService,
    required this.naverFinanceService,
    required this.naverNewsService,
  }) : super(const AsyncValue.data(null));

  final KisApiService kisService;
  final NaverFinanceService naverFinanceService;
  final NaverNewsService naverNewsService;

  bool _hasFetched = false;

  /// 기본 뉴스용 종목 (랭킹 데이터 없을 때 fallback)
  static const _defaultNewsStocks = {
    '삼성전자': '005930',
    'SK하이닉스': '000660',
    'LG에너지솔루션': '373220',
    '현대차': '005380',
    'NAVER': '035420',
    '카카오': '035720',
    '셀트리온': '068270',
    '에코프로비엠': '247540',
    '알테오젠': '196170',
    '삼성바이오로직스': '207940',
  };

  /// Auto-fetch on first read. Subsequent calls are no-ops unless [refresh] is
  /// called explicitly.
  Future<void> fetchIfNeeded() async {
    if (_hasFetched) return;
    await fetchData();
  }

  /// 장 운영시간 확인 (09:00 ~ 15:30 KST)
  bool _isMarketOpen() {
    final now = DateTime.now().toUtc().add(const Duration(hours: 9)); // KST
    final weekday = now.weekday; // 1=Mon, 7=Sun
    if (weekday > 5) return false; // 주말

    final hour = now.hour;
    final minute = now.minute;
    final timeInMinutes = hour * 60 + minute;
    return timeInMinutes >= 9 * 60 && timeInMinutes <= 15 * 60 + 30;
  }

  /// Fetch all free market data. Used for initial load and pull-to-refresh.
  Future<void> fetchData() async {
    state = const AsyncValue.loading();
    _hasFetched = true;

    try {
      final isOpen = _isMarketOpen();

      // Step 1: 시장 지수 + 환율 (장 마감 후에도 반환됨)
      final indexFutures = Future.wait([
        kisService.getKospiIndex(),
        kisService.getKosdaqIndex(),
        kisService.getExchangeRate(),
      ]);

      // Step 2: 랭킹 데이터 — KIS 먼저 시도, 비어있으면 Naver fallback
      List<Map<String, dynamic>> volumeRanking;
      List<Map<String, dynamic>> upRanking;
      List<Map<String, dynamic>> downRanking;

      if (isOpen) {
        // 장중: KIS API 우선 시도
        final kisResults = await Future.wait([
          kisService.getVolumeRanking(),
          kisService.getFluctuationRanking(isUp: true),
          kisService.getFluctuationRanking(isUp: false),
        ]);

        volumeRanking = kisResults[0];
        upRanking = kisResults[1];
        downRanking = kisResults[2];

        // KIS가 빈 결과 반환하면 Naver fallback
        if (volumeRanking.isEmpty) {
          volumeRanking = await naverFinanceService.getVolumeRanking(count: 15);
        }
        if (upRanking.isEmpty) {
          upRanking = await naverFinanceService.getUpRanking();
        }
        if (downRanking.isEmpty) {
          downRanking = await naverFinanceService.getDownRanking();
        }
      } else {
        // 장 마감: Naver API 직접 사용 (24시간 데이터 제공)
        final naverResults = await Future.wait([
          naverFinanceService.getVolumeRanking(count: 15),
          naverFinanceService.getUpRanking(),
          naverFinanceService.getDownRanking(),
        ]);

        volumeRanking = naverResults[0];
        upRanking = naverResults[1];
        downRanking = naverResults[2];
      }

      final indexResults = await indexFutures;
      final kospiIndex = indexResults[0];
      final kosdaqIndex = indexResults[1];
      final exchangeRate = indexResults[2];

      // Step 3: 뉴스 — 거래량 TOP 10 종목 뉴스 가져오기
      final newsMap = <String, List<NewsArticle>>{};

      if (volumeRanking.isNotEmpty) {
        final top10 = volumeRanking.take(10).toList();
        final newsFutures = top10.map((stock) {
          final code = stock['mksc_shrn_iscd'] as String? ?? '';
          final name = stock['hts_kor_isnm'] as String? ?? '';
          if (code.isEmpty) return Future.value(null);
          return naverNewsService.getStockNews(code).then((articles) {
            if (articles.isNotEmpty) {
              newsMap[name.isNotEmpty ? name : code] = articles;
            }
          });
        });
        await Future.wait(newsFutures);
      }

      if (newsMap.length < 3) {
        final remaining = 5 - newsMap.length;
        final defaultEntries = _defaultNewsStocks.entries
            .where((e) => !newsMap.containsKey(e.key))
            .take(remaining);

        final defaultFutures = defaultEntries.map((entry) {
          return naverNewsService.getStockNews(entry.value).then((articles) {
            if (articles.isNotEmpty) {
              newsMap[entry.key] = articles;
            }
          });
        });
        await Future.wait(defaultFutures);
      }

      state = AsyncValue.data(
        MarketData(
          kospiIndex: kospiIndex,
          kosdaqIndex: kosdaqIndex,
          exchangeRate: exchangeRate,
          volumeRanking: volumeRanking,
          upRanking: upRanking,
          downRanking: downRanking,
          stockNews: newsMap,
          isMarketOpen: isOpen,
        ),
      );
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  /// Pull-to-refresh — re-fetches free data.
  Future<void> refresh() async {
    await fetchData();
  }
}
