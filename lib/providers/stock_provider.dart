import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/constants/app_constants.dart';
import '../core/constants/enums.dart';
import '../services/alpaca/alpaca_api_service.dart';
import '../services/kis/kis_api_service.dart';

final kisApiServiceProvider = Provider<KisApiService>((ref) {
  final service = KisApiService(
    appKey: AppConstants.kisAppKey,
    appSecret: AppConstants.kisAppSecret,
    accountNo: AppConstants.kisAccountNo,
  );
  ref.onDispose(service.dispose);
  return service;
});

final alpacaApiServiceProvider = Provider<AlpacaApiService>((ref) {
  final service = AlpacaApiService(
    apiKeyId: AppConstants.alpacaApiKey,
    apiSecretKey: AppConstants.alpacaApiSecret,
  );
  ref.onDispose(service.dispose);
  return service;
});

typedef StockPriceParams = ({String symbol, Market market});

final currentPriceProvider =
    FutureProvider.family<Map<String, dynamic>, StockPriceParams>(
  (ref, params) async {
    switch (params.market) {
      case Market.kr:
        final kis = ref.watch(kisApiServiceProvider);
        return kis.getCurrentPrice(params.symbol);
      case Market.us:
        final alpaca = ref.watch(alpacaApiServiceProvider);
        return alpaca.getLatestTrade(params.symbol);
    }
  },
);

typedef CandleParams = ({String symbol, Market market, ChartInterval interval});

final candleDataProvider =
    FutureProvider.family<List<Map<String, dynamic>>, CandleParams>(
  (ref, params) async {
    switch (params.market) {
      case Market.kr:
        final kis = ref.watch(kisApiServiceProvider);
        switch (params.interval) {
          case ChartInterval.daily:
            return kis.getDailyCandles(params.symbol);
          case ChartInterval.min1:
          case ChartInterval.min5:
          case ChartInterval.min15:
          case ChartInterval.min30:
          case ChartInterval.hour1:
            return kis.getMinuteCandles(params.symbol);
        }
      case Market.us:
        final alpaca = ref.watch(alpacaApiServiceProvider);
        final timeframe = switch (params.interval) {
          ChartInterval.min1 => '1Min',
          ChartInterval.min5 => '5Min',
          ChartInterval.min15 => '15Min',
          ChartInterval.min30 => '30Min',
          ChartInterval.hour1 => '1Hour',
          ChartInterval.daily => '1Day',
        };
        return alpaca.getBars(params.symbol, timeframe: timeframe);
    }
  },
);

typedef SearchParams = ({String query, Market market});

final stockSearchProvider =
    FutureProvider.family<List<Map<String, dynamic>>, SearchParams>(
  (ref, params) async {
    switch (params.market) {
      case Market.kr:
        final kis = ref.watch(kisApiServiceProvider);
        return kis.searchStock(params.query);
      case Market.us:
        final alpaca = ref.watch(alpacaApiServiceProvider);
        return alpaca.searchAssets(params.query);
    }
  },
);

final watchlistSymbolsProvider =
    StateProvider<List<({String symbol, Market market})>>(
  (ref) => [],
);

final watchlistPricesProvider =
    StreamProvider<Map<String, Map<String, dynamic>>>((ref) {
  final symbols = ref.watch(watchlistSymbolsProvider);
  final kis = ref.watch(kisApiServiceProvider);
  final alpaca = ref.watch(alpacaApiServiceProvider);

  final controller = StreamController<Map<String, Map<String, dynamic>>>();

  Future<void> fetchAll() async {
    final results = <String, Map<String, dynamic>>{};

    for (final item in symbols) {
      try {
        switch (item.market) {
          case Market.kr:
            results[item.symbol] = await kis.getCurrentPrice(item.symbol);
          case Market.us:
            results[item.symbol] = await alpaca.getLatestTrade(item.symbol);
        }
      } catch (_) {
        // Skip failed fetches
      }
    }

    if (!controller.isClosed) {
      controller.add(results);
    }
  }

  final timer = Timer.periodic(AppConstants.dataRefreshInterval, (_) {
    fetchAll();
  });

  fetchAll();

  ref.onDispose(() {
    timer.cancel();
    controller.close();
  });

  return controller.stream;
});
