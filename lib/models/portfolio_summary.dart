import 'package:equatable/equatable.dart';

import '../core/constants/enums.dart';
import 'trade.dart';

class PortfolioSummary extends Equatable {
  final double totalInvested;
  final double totalCurrentValue;
  final double totalProfitLoss;
  final double totalProfitLossPercent;
  final double winRate;
  final int totalTrades;
  final int openTrades;

  const PortfolioSummary({
    this.totalInvested = 0,
    this.totalCurrentValue = 0,
    this.totalProfitLoss = 0,
    this.totalProfitLossPercent = 0,
    this.winRate = 0,
    this.totalTrades = 0,
    this.openTrades = 0,
  });

  bool get isProfit => totalProfitLoss >= 0;

  factory PortfolioSummary.fromTrades(
    List<Trade> trades, {
    Map<String, double> currentPrices = const {},
  }) {
    if (trades.isEmpty) {
      return const PortfolioSummary();
    }

    double invested = 0;
    double currentValue = 0;
    int wins = 0;
    int closedCount = 0;
    int openCount = 0;

    for (final trade in trades) {
      if (trade.type == TradeType.buy) {
        invested += trade.totalAmount;

        final currentPrice = currentPrices[trade.symbol] ?? trade.price;
        if (trade.status == TradeStatus.open) {
          currentValue += currentPrice * trade.quantity;
          openCount++;
        } else {
          closedCount++;
          if (currentPrice >= trade.price) {
            wins++;
          }
        }
      }
    }

    final profitLoss = currentValue - invested;
    final profitLossPercent = invested > 0 ? (profitLoss / invested) * 100 : 0;
    final wr = closedCount > 0 ? (wins / closedCount) * 100 : 0;

    return PortfolioSummary(
      totalInvested: invested,
      totalCurrentValue: currentValue,
      totalProfitLoss: profitLoss,
      totalProfitLossPercent: profitLossPercent.toDouble(),
      winRate: wr.toDouble(),
      totalTrades: trades.length,
      openTrades: openCount,
    );
  }

  @override
  List<Object?> get props => [
        totalInvested,
        totalCurrentValue,
        totalProfitLoss,
        totalProfitLossPercent,
        winRate,
        totalTrades,
        openTrades,
      ];
}
