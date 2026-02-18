import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/constants/enums.dart';
import '../models/trade.dart';
import '../models/portfolio_summary.dart';

class TradesNotifier extends StateNotifier<List<Trade>> {
  TradesNotifier()
      : super([
          Trade(
              symbol: '005930',
              name: '삼성전자',
              market: Market.kr,
              type: TradeType.buy,
              price: 72000,
              quantity: 100),
          Trade(
              symbol: '035720',
              name: '카카오',
              market: Market.kr,
              type: TradeType.buy,
              price: 48500,
              quantity: 50),
        ]);

  void addTrade(Trade trade) {
    state = [...state, trade];
  }

  void closeTrade(String tradeId) {
    state = [
      for (final trade in state)
        if (trade.id == tradeId)
          trade.copyWith(status: TradeStatus.closed)
        else
          trade,
    ];
  }

  void deleteTrade(String tradeId) {
    state = state.where((t) => t.id != tradeId).toList();
  }

  List<Trade> getOpenTrades() {
    return state.where((t) => t.status == TradeStatus.open).toList();
  }

  List<Trade> getClosedTrades() {
    return state.where((t) => t.status == TradeStatus.closed).toList();
  }
}

final tradesProvider =
    StateNotifierProvider<TradesNotifier, List<Trade>>((ref) {
  return TradesNotifier();
});

final portfolioSummaryProvider = Provider<PortfolioSummary>((ref) {
  final trades = ref.watch(tradesProvider);
  return PortfolioSummary.fromTrades(trades);
});

final todayPnLProvider = Provider<double>((ref) {
  final trades = ref.watch(tradesProvider);
  final now = DateTime.now();
  final todayStart = DateTime(now.year, now.month, now.day);

  double pnl = 0;

  for (final trade in trades) {
    if (trade.status == TradeStatus.closed &&
        trade.timestamp.isAfter(todayStart)) {
      pnl += trade.totalAmount - (trade.price * trade.quantity) - trade.fee;
    }
  }

  return pnl;
});
