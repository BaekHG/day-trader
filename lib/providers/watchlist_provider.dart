import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/constants/enums.dart';
import '../models/watchlist_item.dart';

class WatchlistNotifier extends StateNotifier<List<WatchlistItem>> {
  WatchlistNotifier()
      : super([
          WatchlistItem(symbol: '005930', name: '삼성전자', market: Market.kr),
          WatchlistItem(symbol: '000660', name: 'SK하이닉스', market: Market.kr),
          WatchlistItem(symbol: '035720', name: '카카오', market: Market.kr),
        ]);

  void addItem(WatchlistItem item) {
    if (state.any((e) => e.symbol == item.symbol)) return;
    state = [...state, item];
  }

  void removeItem(String symbol) {
    state = state.where((e) => e.symbol != symbol).toList();
  }

  void updateTargetPrices(
    String symbol, {
    double? buyTarget,
    double? sellTarget,
  }) {
    state = [
      for (final item in state)
        if (item.symbol == symbol)
          item.copyWith(
            targetBuyPrice: buyTarget,
            targetSellPrice: sellTarget,
          )
        else
          item,
    ];
  }
}

final watchlistProvider =
    StateNotifierProvider<WatchlistNotifier, List<WatchlistItem>>((ref) {
  return WatchlistNotifier();
});
