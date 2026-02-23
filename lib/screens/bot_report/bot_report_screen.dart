import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/models/bot_trade.dart';
import 'package:day_trader/models/ai_analysis.dart';
import 'package:day_trader/models/daily_report.dart';
import 'package:day_trader/providers/bot_data_provider.dart';
import 'package:day_trader/widgets/common/empty_state.dart';
import 'package:day_trader/widgets/common/loading_shimmer.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';

class BotReportScreen extends ConsumerStatefulWidget {
  const BotReportScreen({super.key});

  @override
  ConsumerState<BotReportScreen> createState() => _BotReportScreenState();
}

class _BotReportScreenState extends ConsumerState<BotReportScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.accent,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            const Text('봇 리포트'),
          ],
        ),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: '거래내역'),
            Tab(text: '전략 성과'),
            Tab(text: 'AI분석'),
            Tab(text: '일일리포트'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          const _TradesTab(),
          const _StrategyTab(),
          const _AnalysesTab(),
          _DailyReportsTab(),
        ],
      ),
    );
  }
}

// ==================== TRADES TAB ====================

class _TradesTab extends ConsumerWidget {
  const _TradesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tradesAsync = ref.watch(botTradesProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(botTradesProvider);
      },
      color: AppColors.accent,
      backgroundColor: AppColors.card,
      child: tradesAsync.when(
        loading: () => const StockListShimmer(itemCount: 8),
        error: (err, _) => EmptyState(
          icon: Icons.error_outline,
          message: '데이터 로드 실패',
          submessage: err.toString(),
        ),
        data: (trades) {
          if (trades.isEmpty) {
            return const EmptyState(
              icon: Icons.swap_horiz,
              message: '거래 내역이 없습니다',
              submessage: '봇이 거래를 실행하면 여기에 표시됩니다',
            );
          }

          // Group trades by date
          final grouped = <String, List<BotTrade>>{};
          for (final trade in trades) {
            final key = Formatters.formatDate(trade.tradedAt);
            grouped.putIfAbsent(key, () => []).add(trade);
          }
          final sortedKeys = grouped.keys.toList()
            ..sort((a, b) => b.compareTo(a));

          // Calculate today's summary
          final todayKey = Formatters.formatDate(DateTime.now());
          final todayTrades = grouped[todayKey] ?? [];
          int todayBuyCount = 0;
          int todaySellCount = 0;
          int todayBuyAmount = 0;
          int todaySellAmount = 0;
          for (final t in todayTrades) {
            if (t.isSell) {
              todaySellCount++;
              todaySellAmount += t.amount;
            } else {
              todayBuyCount++;
              todayBuyAmount += t.amount;
            }
          }

          // Use daily_report total_pnl for today (more accurate than trades)
          final reportsAsync = ref.watch(dailyReportsProvider);
          final todayDateStr = Formatters.formatDate(DateTime.now());
          int todayPnl = 0;
          reportsAsync.whenData((reports) {
            for (final r in reports) {
              if (r.reportDate == todayDateStr) {
                todayPnl = r.totalPnl;
                break;
              }
            }
          });

          // Fallback: sum sell pnl from trades if no daily_report
          if (todayPnl == 0) {
            for (final t in todayTrades) {
              if (t.isSell) todayPnl += t.pnlAmount;
            }
          }

          // Calculate total P&L from all daily reports + sell trades
          int totalPnl = 0;
          int totalSellCount = 0;
          reportsAsync.whenData((reports) {
            for (final r in reports) {
              totalPnl += r.totalPnl;
            }
          });
          for (final t in trades) {
            if (t.isSell) totalSellCount++;
          }
          // Fallback if no reports
          if (totalPnl == 0) {
            for (final t in trades) {
              if (t.isSell) totalPnl += t.pnlAmount;
            }
          }

          return ListView.builder(
            padding: const EdgeInsets.only(top: 8, bottom: 100),
            itemCount: sortedKeys.length + 1, // +1 for summary card
            itemBuilder: (context, index) {
              // First item: summary card
              if (index == 0) {
                return _TradeSummaryCard(
                  todayPnl: todayPnl,
                  todayBuyCount: todayBuyCount,
                  todaySellCount: todaySellCount,
                  todayBuyAmount: todayBuyAmount,
                  todaySellAmount: todaySellAmount,
                  totalPnl: totalPnl,
                  totalSellCount: totalSellCount,
                  totalTradeCount: trades.length,
                );
              }

              final dateIndex = index - 1;
              final dateKey = sortedKeys[dateIndex];
              final dayTrades = grouped[dateKey]!;
              final firstDate = dayTrades.first.tradedAt;
              final dateLabel = Formatters.formatDateWithDay(firstDate);

              // Calculate daily P&L from sell trades
              int dailyPnl = 0;
              int sellCount = 0;
              for (final t in dayTrades) {
                if (t.isSell) {
                  dailyPnl += t.pnlAmount;
                  sellCount++;
                }
              }

              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _DateHeader(
                    dateLabel: dateLabel,
                    tradeCount: dayTrades.length,
                    dailyPnl: dailyPnl,
                    hasSells: sellCount > 0,
                  ),
                  ...dayTrades.map((t) => _TradeItem(trade: t)),
                  const SizedBox(height: 8),
                ],
              );
            },
          );
        },
      ),
    );
  }
}

class _TradeSummaryCard extends StatelessWidget {
  const _TradeSummaryCard({
    required this.todayPnl,
    required this.todayBuyCount,
    required this.todaySellCount,
    required this.todayBuyAmount,
    required this.todaySellAmount,
    required this.totalPnl,
    required this.totalSellCount,
    required this.totalTradeCount,
  });

  final int todayPnl;
  final int todayBuyCount;
  final int todaySellCount;
  final int todayBuyAmount;
  final int todaySellAmount;
  final int totalPnl;
  final int totalSellCount;
  final int totalTradeCount;

  @override
  Widget build(BuildContext context) {
    final todayIsProfit = todayPnl >= 0;
    final totalIsProfit = totalPnl >= 0;
    final todayTotal = todayBuyCount + todaySellCount;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: todayIsProfit
              ? AppColors.profit.withValues(alpha: 0.3)
              : AppColors.loss.withValues(alpha: 0.3),
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Today's P&L
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.accentDim,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'TODAY',
                  style: TextStyle(
                    color: AppColors.accent,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                Formatters.formatDateWithDay(DateTime.now()),
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${todayPnl >= 0 ? '+' : ''}${Formatters.formatKRW(todayPnl)}',
                style: TextStyle(
                  color: todayIsProfit ? AppColors.profit : AppColors.loss,
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              const Spacer(),
              Text(
                '$todayTotal건 거래',
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Today detail stats
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Expanded(
                  child: _MiniStat(
                    label: '매수',
                    value: '$todayBuyCount건',
                    sub: Formatters.formatKRW(todayBuyAmount),
                    color: AppColors.profit,
                  ),
                ),
                Container(width: 0.5, height: 32, color: AppColors.border),
                Expanded(
                  child: _MiniStat(
                    label: '매도',
                    value: '$todaySellCount건',
                    sub: Formatters.formatKRW(todaySellAmount),
                    color: AppColors.loss,
                  ),
                ),
                Container(width: 0.5, height: 32, color: AppColors.border),
                Expanded(
                  child: _MiniStat(
                    label: '누적 수익',
                    value:
                        '${totalPnl >= 0 ? '+' : ''}${Formatters.formatKRW(totalPnl)}',
                    sub: '총 $totalTradeCount건',
                    color: totalIsProfit ? AppColors.profit : AppColors.loss,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat({
    required this.label,
    required this.value,
    required this.sub,
    required this.color,
  });

  final String label;
  final String value;
  final String sub;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 10),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 13,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
        const SizedBox(height: 2),
        Text(
          sub,
          style: const TextStyle(
            color: AppColors.textTertiary,
            fontSize: 10,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

class _DateHeader extends StatelessWidget {
  const _DateHeader({
    required this.dateLabel,
    required this.tradeCount,
    required this.dailyPnl,
    required this.hasSells,
  });

  final String dateLabel;
  final int tradeCount;
  final int dailyPnl;
  final bool hasSells;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Container(
            width: 4,
            height: 16,
            decoration: BoxDecoration(
              color: AppColors.accent,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            dateLabel,
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '$tradeCount건',
            style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
          ),
          const Spacer(),
          if (hasSells)
            ProfitLossText(
              amount: dailyPnl.toDouble(),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
        ],
      ),
    );
  }
}

class _TradeItem extends StatelessWidget {
  const _TradeItem({required this.trade});

  final BotTrade trade;

  Color _exitTypeColor(BotTrade t) {
    return switch (t.exitTypeLabel) {
      '트레일링' => AppColors.accent,
      '손절' => AppColors.loss,
      '시간청산' => AppColors.warning,
      '강제청산' => AppColors.textTertiary,
      _ => AppColors.info,
    };
  }

  @override
  Widget build(BuildContext context) {
    final isBuy = trade.isBuy;
    final actionColor = isBuy ? AppColors.profit : AppColors.loss;
    final actionBgColor = isBuy ? AppColors.profitBg : AppColors.lossBg;
    final actionText = isBuy ? '매수' : '매도';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: actionBgColor,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  actionText,
                  style: TextStyle(
                    color: actionColor,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  trade.stockName,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              Text(
                Formatters.formatTimeOnly(trade.tradedAt),
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 11,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '단가',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      Formatters.formatKRW(trade.price),
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '수량',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${trade.quantity}주',
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '거래금액',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      Formatters.formatKRW(trade.amount),
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (trade.isSell && trade.pnlAmount != 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: trade.pnlAmount >= 0
                    ? AppColors.profitBg
                    : AppColors.lossBg,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Text(
                    '실현손익',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                  const Spacer(),
                  ProfitLossText(
                    amount: trade.pnlAmount.toDouble(),
                    percentage: trade.pnlPct,
                    fontSize: 13,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (trade.exitTypeLabel.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: _exitTypeColor(trade).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      trade.exitTypeLabel,
                      style: TextStyle(
                        color: _exitTypeColor(trade),
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                if (trade.holdMinutes > 0) ...[
                  const SizedBox(width: 6),
                  Text(
                    trade.holdMinutes >= 60
                        ? '${(trade.holdMinutes / 60).toStringAsFixed(1)}시간 보유'
                        : '${trade.holdMinutes.toStringAsFixed(0)}분 보유',
                    style: const TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 10,
                    ),
                  ),
                ],
                if (trade.highWaterMarkPct > 0) ...[
                  const SizedBox(width: 6),
                  Text(
                    '고점 +${trade.highWaterMarkPct.toStringAsFixed(1)}%',
                    style: const TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 10,
                    ),
                  ),
                ],
              ],
            ),
          ],
          if (trade.isBuy && trade.reason.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              trade.reason,
              style: const TextStyle(
                color: AppColors.textTertiary,
                fontSize: 11,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

// ==================== STRATEGY TAB ====================

class _StrategyTab extends ConsumerWidget {
  const _StrategyTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tradesAsync = ref.watch(botTradesProvider);
    final reportsAsync = ref.watch(dailyReportsProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(botTradesProvider);
        ref.invalidate(dailyReportsProvider);
      },
      color: AppColors.accent,
      backgroundColor: AppColors.card,
      child: tradesAsync.when(
        loading: () => const StockListShimmer(itemCount: 6),
        error: (err, _) => EmptyState(
          icon: Icons.error_outline,
          message: '데이터 로드 실패',
          submessage: err.toString(),
        ),
        data: (trades) {
          final sells = trades.where((t) => t.isSell).toList();
          if (sells.isEmpty) {
            return const EmptyState(
              icon: Icons.analytics_outlined,
              message: '전략 성과 데이터 없음',
              submessage: '매도 거래가 발생하면 분석 결과가 표시됩니다',
            );
          }

          final wins = sells.where((t) => t.pnlAmount > 0).toList();
          final losses = sells.where((t) => t.pnlAmount < 0).toList();
          final winRate = sells.isNotEmpty
              ? (wins.length / sells.length * 100)
              : 0.0;
          final avgProfit = wins.isNotEmpty
              ? wins.map((t) => t.pnlAmount).reduce((a, b) => a + b) /
                    wins.length
              : 0.0;
          final avgLoss = losses.isNotEmpty
              ? losses.map((t) => t.pnlAmount).reduce((a, b) => a + b) /
                    losses.length
              : 0.0;
          final riskReward = avgLoss != 0 ? (avgProfit / avgLoss.abs()) : 0.0;

          final reports = reportsAsync.valueOrNull ?? [];

          return ListView(
            padding: const EdgeInsets.only(top: 8, bottom: 100),
            children: [
              _StrategySummaryCard(
                totalSells: sells.length,
                winRate: winRate,
                avgProfit: avgProfit,
                avgLoss: avgLoss,
                riskReward: riskReward,
              ),
              _ExitTypeSection(sells: sells),
              _TrailingEfficiencySection(sells: sells),
              _HoldTimeSection(sells: sells),
              if (reports.length >= 2) _WinRateTrendChart(reports: reports),
            ],
          );
        },
      ),
    );
  }
}

class _StrategySummaryCard extends StatelessWidget {
  const _StrategySummaryCard({
    required this.totalSells,
    required this.winRate,
    required this.avgProfit,
    required this.avgLoss,
    required this.riskReward,
  });

  final int totalSells;
  final double winRate;
  final double avgProfit;
  final double avgLoss;
  final double riskReward;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.accentDim,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'OVERVIEW',
                  style: TextStyle(
                    color: AppColors.accent,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '총 $totalSells건 매도',
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _StatBlock(
                  label: '승률',
                  value: '${winRate.toStringAsFixed(1)}%',
                  color: winRate >= 50 ? AppColors.profit : AppColors.loss,
                ),
              ),
              Container(width: 0.5, height: 44, color: AppColors.border),
              Expanded(
                child: _StatBlock(
                  label: '평균 수익',
                  value: Formatters.formatKRW(avgProfit.toInt()),
                  color: AppColors.profit,
                ),
              ),
              Container(width: 0.5, height: 44, color: AppColors.border),
              Expanded(
                child: _StatBlock(
                  label: '평균 손실',
                  value: Formatters.formatKRW(avgLoss.toInt()),
                  color: AppColors.loss,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'Risk:Reward',
                  style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
                ),
                const SizedBox(width: 8),
                Text(
                  '1 : ${riskReward.toStringAsFixed(2)}',
                  style: TextStyle(
                    color: riskReward >= 1.5
                        ? AppColors.profit
                        : riskReward >= 1.0
                        ? AppColors.warning
                        : AppColors.loss,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatBlock extends StatelessWidget {
  const _StatBlock({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 11),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

class _ExitTypeSection extends StatelessWidget {
  const _ExitTypeSection({required this.sells});

  final List<BotTrade> sells;

  @override
  Widget build(BuildContext context) {
    final exitCounts = <String, int>{};
    for (final t in sells) {
      final label = t.exitTypeLabel;
      exitCounts[label] = (exitCounts[label] ?? 0) + 1;
    }
    if (exitCounts.isEmpty) return const SizedBox.shrink();

    final colorMap = {
      '트레일링': AppColors.accent,
      '손절': AppColors.loss,
      '시간청산': AppColors.warning,
      '강제청산': AppColors.textTertiary,
      '수동': AppColors.info,
    };

    final sortedEntries = exitCounts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    final sections = <PieChartSectionData>[];
    for (final entry in sortedEntries) {
      final pct = entry.value / sells.length * 100;
      final color = colorMap[entry.key] ?? AppColors.textSecondary;
      sections.add(
        PieChartSectionData(
          value: entry.value.toDouble(),
          color: color,
          radius: 28,
          title: '${pct.toStringAsFixed(0)}%',
          titleStyle: const TextStyle(
            color: AppColors.textPrimary,
            fontSize: 10,
            fontWeight: FontWeight.w700,
          ),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.pie_chart_outline,
                size: 16,
                color: AppColors.accent,
              ),
              const SizedBox(width: 6),
              const Text(
                '매도 사유 분포',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 120,
            child: Row(
              children: [
                SizedBox(
                  width: 120,
                  height: 120,
                  child: PieChart(
                    PieChartData(
                      sections: sections,
                      centerSpaceRadius: 24,
                      sectionsSpace: 2,
                    ),
                  ),
                ),
                const SizedBox(width: 24),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: sortedEntries.map((entry) {
                      final color =
                          colorMap[entry.key] ?? AppColors.textSecondary;
                      final pct = entry.value / sells.length * 100;
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(
                          children: [
                            Container(
                              width: 10,
                              height: 10,
                              decoration: BoxDecoration(
                                color: color,
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                entry.key,
                                style: const TextStyle(
                                  color: AppColors.textSecondary,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                            Text(
                              '${entry.value}건 (${pct.toStringAsFixed(0)}%)',
                              style: const TextStyle(
                                color: AppColors.textPrimary,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                fontFeatures: [FontFeature.tabularFigures()],
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TrailingEfficiencySection extends StatelessWidget {
  const _TrailingEfficiencySection({required this.sells});

  final List<BotTrade> sells;

  @override
  Widget build(BuildContext context) {
    final trailingTrades = sells
        .where((t) => t.exitType == 'trailing' || t.reason.contains('트레일링'))
        .toList();

    if (trailingTrades.isEmpty) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border, width: 0.5),
        ),
        child: Row(
          children: [
            const Icon(Icons.trending_up, size: 16, color: AppColors.accent),
            const SizedBox(width: 6),
            const Text(
              '트레일링 효율',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Spacer(),
            const Text(
              '데이터 수집 중',
              style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
            ),
          ],
        ),
      );
    }

    final avgPeak =
        trailingTrades.map((t) => t.highWaterMarkPct).reduce((a, b) => a + b) /
        trailingTrades.length;
    final avgRealized =
        trailingTrades.map((t) => t.pnlPct).reduce((a, b) => a + b) /
        trailingTrades.length;
    final captureRate = avgPeak > 0 ? (avgRealized / avgPeak * 100) : 0.0;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.trending_up, size: 16, color: AppColors.accent),
              const SizedBox(width: 6),
              const Text(
                '트레일링 효율',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                '${trailingTrades.length}건',
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Expanded(
                  child: _StatBlock(
                    label: '평균 고점',
                    value: '+${avgPeak.toStringAsFixed(1)}%',
                    color: AppColors.accent,
                  ),
                ),
                Container(width: 0.5, height: 36, color: AppColors.border),
                Expanded(
                  child: _StatBlock(
                    label: '평균 실현',
                    value:
                        '${avgRealized >= 0 ? '+' : ''}${avgRealized.toStringAsFixed(1)}%',
                    color: avgRealized >= 0 ? AppColors.profit : AppColors.loss,
                  ),
                ),
                Container(width: 0.5, height: 36, color: AppColors.border),
                Expanded(
                  child: _StatBlock(
                    label: '수익 캡처율',
                    value: '${captureRate.toStringAsFixed(0)}%',
                    color: captureRate >= 70
                        ? AppColors.profit
                        : captureRate >= 50
                        ? AppColors.warning
                        : AppColors.loss,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HoldTimeSection extends StatelessWidget {
  const _HoldTimeSection({required this.sells});

  final List<BotTrade> sells;

  @override
  Widget build(BuildContext context) {
    final withHold = sells.where((t) => t.holdMinutes > 0).toList();
    if (withHold.isEmpty) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border, width: 0.5),
        ),
        child: Row(
          children: [
            const Icon(Icons.timer_outlined, size: 16, color: AppColors.accent),
            const SizedBox(width: 6),
            const Text(
              '보유 시간 분석',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Spacer(),
            const Text(
              '데이터 수집 중',
              style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
            ),
          ],
        ),
      );
    }

    final avgHold =
        withHold.map((t) => t.holdMinutes).reduce((a, b) => a + b) /
        withHold.length;
    final minHold = withHold.map((t) => t.holdMinutes).reduce(math.min);
    final maxHold = withHold.map((t) => t.holdMinutes).reduce(math.max);

    String formatMinutes(double m) {
      if (m >= 60) return '${(m / 60).toStringAsFixed(1)}시간';
      return '${m.toStringAsFixed(0)}분';
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.timer_outlined,
                size: 16,
                color: AppColors.accent,
              ),
              const SizedBox(width: 6),
              const Text(
                '보유 시간 분석',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                '${withHold.length}건',
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Expanded(
                  child: _StatBlock(
                    label: '최소',
                    value: formatMinutes(minHold),
                    color: AppColors.textPrimary,
                  ),
                ),
                Container(width: 0.5, height: 36, color: AppColors.border),
                Expanded(
                  child: _StatBlock(
                    label: '평균',
                    value: formatMinutes(avgHold),
                    color: AppColors.accent,
                  ),
                ),
                Container(width: 0.5, height: 36, color: AppColors.border),
                Expanded(
                  child: _StatBlock(
                    label: '최대',
                    value: formatMinutes(maxHold),
                    color: AppColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _WinRateTrendChart extends StatelessWidget {
  const _WinRateTrendChart({required this.reports});

  final List<DailyReport> reports;

  @override
  Widget build(BuildContext context) {
    final chartData = reports.reversed.toList();
    final displayData = chartData.length > 14
        ? chartData.sublist(chartData.length - 14)
        : chartData;
    if (displayData.length < 2) return const SizedBox.shrink();

    final spots = <FlSpot>[];
    for (int i = 0; i < displayData.length; i++) {
      spots.add(FlSpot(i.toDouble(), displayData[i].winRate));
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.show_chart, size: 16, color: AppColors.accent),
              const SizedBox(width: 6),
              const Text(
                '일별 승률 추이',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                '최근 ${displayData.length}일',
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 120,
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: 25,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: value == 50
                        ? AppColors.warning.withValues(alpha: 0.4)
                        : AppColors.border.withValues(alpha: 0.3),
                    strokeWidth: value == 50 ? 1 : 0.5,
                    dashArray: value == 50 ? [4, 4] : null,
                  ),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 32,
                      interval: 50,
                      getTitlesWidget: (value, meta) {
                        if (value == 0 || value == 50 || value == 100) {
                          return Text(
                            '${value.toInt()}%',
                            style: const TextStyle(
                              color: AppColors.textTertiary,
                              fontSize: 9,
                            ),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 20,
                      interval: 1,
                      getTitlesWidget: (value, meta) {
                        final idx = value.toInt();
                        if (idx < 0 || idx >= displayData.length) {
                          return const SizedBox.shrink();
                        }
                        if (displayData.length > 7 && idx % 2 != 0) {
                          return const SizedBox.shrink();
                        }
                        final dateStr = displayData[idx].reportDate;
                        final short = dateStr.length >= 10
                            ? '${dateStr.substring(5, 7)}/${dateStr.substring(8, 10)}'
                            : dateStr;
                        return Text(
                          short,
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 9,
                          ),
                        );
                      },
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                minY: 0,
                maxY: 100,
                lineBarsData: [
                  LineChartBarData(
                    spots: spots,
                    isCurved: true,
                    color: AppColors.accent,
                    barWidth: 2,
                    isStrokeCapRound: true,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, percent, barData, index) =>
                          FlDotCirclePainter(
                            radius: 3,
                            color: spot.y >= 50
                                ? AppColors.profit
                                : AppColors.loss,
                            strokeWidth: 1.5,
                            strokeColor: AppColors.card,
                          ),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      color: AppColors.accent.withValues(alpha: 0.08),
                    ),
                  ),
                ],
                lineTouchData: LineTouchData(
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipColor: (_) => AppColors.surface,
                    tooltipRoundedRadius: 6,
                    getTooltipItems: (touchedSpots) {
                      return touchedSpots.map((spot) {
                        final report = displayData[spot.x.toInt()];
                        return LineTooltipItem(
                          '${Formatters.formatDateStringWithDay(report.reportDate)}\n승률 ${spot.y.toStringAsFixed(1)}% (${report.winCount}승 ${report.lossCount}패)',
                          const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                          ),
                        );
                      }).toList();
                    },
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ==================== ANALYSES TAB ====================

class _AnalysesTab extends ConsumerWidget {
  const _AnalysesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final analysesAsync = ref.watch(aiAnalysesProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(aiAnalysesProvider);
      },
      color: AppColors.accent,
      backgroundColor: AppColors.card,
      child: analysesAsync.when(
        loading: () => const StockListShimmer(itemCount: 5),
        error: (err, _) => EmptyState(
          icon: Icons.error_outline,
          message: '데이터 로드 실패',
          submessage: err.toString(),
        ),
        data: (analyses) {
          if (analyses.isEmpty) {
            return const EmptyState(
              icon: Icons.psychology_outlined,
              message: 'AI 분석 내역이 없습니다',
              submessage: '봇이 시장 분석을 수행하면 여기에 표시됩니다',
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.only(top: 8, bottom: 100),
            itemCount: analyses.length,
            itemBuilder: (context, index) =>
                _AnalysisItem(analysis: analyses[index]),
          );
        },
      ),
    );
  }
}

class _AnalysisItem extends StatelessWidget {
  const _AnalysisItem({required this.analysis});

  final AiAnalysis analysis;

  @override
  Widget build(BuildContext context) {
    final scoreColor = analysis.marketScore >= 70
        ? AppColors.profit
        : analysis.marketScore >= 40
        ? AppColors.warning
        : AppColors.loss;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _ScoreIndicator(score: analysis.marketScore, color: scoreColor),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '시장 점수',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${analysis.marketScore}점',
                      style: TextStyle(
                        color: scoreColor,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '성공확률',
                    style: TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 11,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${analysis.successProbability.toStringAsFixed(1)}%',
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '추천',
                  style: TextStyle(color: AppColors.textTertiary, fontSize: 11),
                ),
                const SizedBox(height: 4),
                Text(
                  analysis.recommendation,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          if (analysis.favorableThemes.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              '유망 테마',
              style: TextStyle(color: AppColors.textTertiary, fontSize: 11),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: analysis.favorableThemes
                  .take(5)
                  .map(
                    (theme) => Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.accentDim,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        theme,
                        style: const TextStyle(
                          color: AppColors.accent,
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
          if (analysis.picks.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              '추천 종목',
              style: TextStyle(color: AppColors.textTertiary, fontSize: 11),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: analysis.picks.take(5).map((pick) {
                final pickName = pick is Map
                    ? (pick['name'] ?? pick['stock_name'] ?? pick.toString())
                    : pick.toString();
                return Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: AppColors.border, width: 0.5),
                  ),
                  child: Text(
                    pickName,
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text(
                Formatters.formatDateTime(analysis.analyzedAt),
                style: const TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ScoreIndicator extends StatelessWidget {
  const _ScoreIndicator({required this.score, required this.color});

  final int score;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 48,
      height: 48,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 48,
            height: 48,
            child: CircularProgressIndicator(
              value: score / 100,
              strokeWidth: 4,
              backgroundColor: AppColors.border,
              valueColor: AlwaysStoppedAnimation<Color>(color),
            ),
          ),
          Icon(
            score >= 70
                ? Icons.trending_up
                : score >= 40
                ? Icons.trending_flat
                : Icons.trending_down,
            color: color,
            size: 20,
          ),
        ],
      ),
    );
  }
}

// ==================== DAILY REPORTS TAB ====================

class _DailyReportsTab extends ConsumerStatefulWidget {
  const _DailyReportsTab();

  @override
  ConsumerState<_DailyReportsTab> createState() => _DailyReportsTabState();
}

class _DailyReportsTabState extends ConsumerState<_DailyReportsTab> {
  final _expandedIndices = <int>{};

  @override
  Widget build(BuildContext context) {
    final reportsAsync = ref.watch(dailyReportsProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(dailyReportsProvider);
      },
      color: AppColors.accent,
      backgroundColor: AppColors.card,
      child: reportsAsync.when(
        loading: () => const StockListShimmer(itemCount: 6),
        error: (err, _) => EmptyState(
          icon: Icons.error_outline,
          message: '데이터 로드 실패',
          submessage: err.toString(),
        ),
        data: (reports) {
          if (reports.isEmpty) {
            return const EmptyState(
              icon: Icons.calendar_today_outlined,
              message: '일일 리포트가 없습니다',
              submessage: '봇이 일일 리포트를 생성하면 여기에 표시됩니다',
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.only(top: 8, bottom: 100),
            itemCount: reports.length + 1, // +1 for chart
            itemBuilder: (context, index) {
              // First item: P&L chart
              if (index == 0) {
                return _DailyPnlChart(reports: reports);
              }

              final reportIndex = index - 1;
              final isExpanded = _expandedIndices.contains(reportIndex);
              return _DailyReportItem(
                report: reports[reportIndex],
                isExpanded: isExpanded,
                onToggle: () {
                  setState(() {
                    if (isExpanded) {
                      _expandedIndices.remove(reportIndex);
                    } else {
                      _expandedIndices.add(reportIndex);
                    }
                  });
                },
              );
            },
          );
        },
      ),
    );
  }
}

class _DailyReportItem extends StatelessWidget {
  const _DailyReportItem({
    required this.report,
    required this.isExpanded,
    required this.onToggle,
  });

  final DailyReport report;
  final bool isExpanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final isProfit = report.isProfit;
    final dateLabel = Formatters.formatDateStringWithDay(report.reportDate);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isProfit
              ? AppColors.profit.withValues(alpha: 0.3)
              : AppColors.loss.withValues(alpha: 0.3),
          width: 0.5,
        ),
      ),
      child: Column(
        children: [
          // Collapsed summary (always visible)
          InkWell(
            onTap: onToggle,
            borderRadius: isExpanded
                ? const BorderRadius.vertical(top: Radius.circular(12))
                : BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: [
                  Row(
                    children: [
                      Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          color: isProfit
                              ? AppColors.profitBg
                              : AppColors.lossBg,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(
                          isProfit
                              ? Icons.arrow_upward_rounded
                              : Icons.arrow_downward_rounded,
                          color: isProfit ? AppColors.profit : AppColors.loss,
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              dateLabel,
                              style: const TextStyle(
                                color: AppColors.textPrimary,
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '총 ${report.totalTrades}건 거래',
                              style: const TextStyle(
                                color: AppColors.textTertiary,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            Formatters.formatKRW(report.totalPnl),
                            style: TextStyle(
                              color: isProfit
                                  ? AppColors.profit
                                  : AppColors.loss,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              fontFeatures: const [
                                FontFeature.tabularFigures(),
                              ],
                            ),
                          ),
                          const SizedBox(height: 2),
                          ProfitLossChip(
                            percentage: report.totalPnlPct,
                            compact: true,
                          ),
                        ],
                      ),
                      const SizedBox(width: 4),
                      AnimatedRotation(
                        turns: isExpanded ? 0.5 : 0,
                        duration: const Duration(milliseconds: 200),
                        child: const Icon(
                          Icons.keyboard_arrow_down,
                          color: AppColors.textTertiary,
                          size: 20,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: _ReportStat(
                            label: '승',
                            value: '${report.winCount}',
                            color: AppColors.profit,
                          ),
                        ),
                        Container(
                          width: 0.5,
                          height: 24,
                          color: AppColors.border,
                        ),
                        Expanded(
                          child: _ReportStat(
                            label: '패',
                            value: '${report.lossCount}',
                            color: AppColors.loss,
                          ),
                        ),
                        Container(
                          width: 0.5,
                          height: 24,
                          color: AppColors.border,
                        ),
                        Expanded(
                          child: _ReportStat(
                            label: '승률',
                            value: '${report.winRate.toStringAsFixed(1)}%',
                            color: AppColors.accent,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          // Expanded content
          AnimatedCrossFade(
            firstChild: const SizedBox.shrink(),
            secondChild: _buildExpandedContent(),
            crossFadeState: isExpanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 250),
          ),
        ],
      ),
    );
  }

  Widget _buildExpandedContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(height: 0.5, color: AppColors.border),
        // Trade details
        if (report.trades.isNotEmpty) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
            child: Row(
              children: [
                const Icon(
                  Icons.receipt_long,
                  size: 14,
                  color: AppColors.accent,
                ),
                const SizedBox(width: 6),
                Text(
                  '거래 상세',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          ...report.trades.map((trade) {
            if (trade is! Map) return const SizedBox.shrink();
            final name = (trade['name'] as String?) ?? '';
            final pnlAmt = ((trade['pnl_amt'] as num?)?.toInt()) ?? 0;
            final pnlPct = ((trade['pnl_pct'] as num?)?.toDouble()) ?? 0.0;
            final entryPrice = ((trade['entry'] as num?)?.toInt()) ?? 0;
            final exitPrice = ((trade['exit'] as num?)?.toInt()) ?? 0;
            final qty = ((trade['qty'] as num?)?.toInt()) ?? 0;
            final isWin = pnlAmt >= 0;

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: isWin ? AppColors.profitBg : AppColors.lossBg,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Icon(
                      isWin
                          ? Icons.arrow_upward_rounded
                          : Icons.arrow_downward_rounded,
                      color: isWin ? AppColors.profit : AppColors.loss,
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${Formatters.formatKRW(entryPrice)} → ${Formatters.formatKRW(exitPrice)}  ×$qty주',
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '${pnlAmt >= 0 ? '+' : ''}${Formatters.formatKRW(pnlAmt)}',
                        style: TextStyle(
                          color: isWin ? AppColors.profit : AppColors.loss,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                      ProfitLossChip(percentage: pnlPct, compact: true),
                    ],
                  ),
                ],
              ),
            );
          }),
        ],
        // Remaining positions
        if (report.remainingPositions.isNotEmpty) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
            child: Row(
              children: [
                const Icon(
                  Icons.inventory_2_outlined,
                  size: 14,
                  color: AppColors.warning,
                ),
                const SizedBox(width: 6),
                Text(
                  '잔여 포지션',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          ...report.remainingPositions.map((pos) {
            if (pos is! Map) return const SizedBox.shrink();
            final name = (pos['name'] as String?) ?? '';
            final qty = ((pos['quantity'] as num?)?.toInt()) ?? 0;
            final avgPrice = ((pos['avg_price'] as num?)?.toInt()) ?? 0;
            final pnlPct = ((pos['pnl_pct'] as num?)?.toDouble()) ?? 0.0;

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: AppColors.border, width: 0.5),
                    ),
                    child: const Icon(
                      Icons.account_balance_wallet_outlined,
                      color: AppColors.textTertiary,
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${Formatters.formatKRW(avgPrice)} × $qty주',
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  ProfitLossChip(percentage: pnlPct, compact: true),
                ],
              ),
            );
          }),
        ],
        const SizedBox(height: 10),
      ],
    );
  }
}

class _ReportStat extends StatelessWidget {
  const _ReportStat({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 11),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

// ==================== DAILY P&L CHART ====================

class _DailyPnlChart extends StatelessWidget {
  const _DailyPnlChart({required this.reports});

  final List<DailyReport> reports;

  @override
  Widget build(BuildContext context) {
    // Reverse to show oldest→newest (left→right), take last 14 days
    final chartData = reports.reversed.toList();
    final displayData = chartData.length > 14
        ? chartData.sublist(chartData.length - 14)
        : chartData;

    if (displayData.isEmpty) return const SizedBox.shrink();

    // Calculate cumulative P&L
    int cumulativePnl = 0;
    final cumulativeData = <int>[];
    for (final r in displayData) {
      cumulativePnl += r.totalPnl;
      cumulativeData.add(cumulativePnl);
    }

    final maxPnl = displayData.map((r) => r.totalPnl.abs()).reduce(math.max);
    final maxY = (maxPnl * 1.3).toDouble();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.bar_chart_rounded,
                size: 16,
                color: AppColors.accent,
              ),
              const SizedBox(width: 6),
              const Text(
                '일별 손익',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                '누적 ${cumulativePnl >= 0 ? '+' : ''}${Formatters.formatKRW(cumulativePnl)}',
                style: TextStyle(
                  color: cumulativePnl >= 0 ? AppColors.profit : AppColors.loss,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 160,
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: maxY,
                minY: -maxY,
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => AppColors.surface,
                    tooltipPadding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    tooltipRoundedRadius: 6,
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      final report = displayData[group.x.toInt()];
                      final pnl = report.totalPnl;
                      return BarTooltipItem(
                        '${Formatters.formatDateStringWithDay(report.reportDate)}\n${pnl >= 0 ? '+' : ''}${Formatters.formatKRW(pnl)}',
                        TextStyle(
                          color: pnl >= 0 ? AppColors.profit : AppColors.loss,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      );
                    },
                  ),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 20,
                      getTitlesWidget: (value, meta) {
                        final idx = value.toInt();
                        if (idx < 0 || idx >= displayData.length) {
                          return const SizedBox.shrink();
                        }
                        if (displayData.length > 7 && idx % 2 != 0) {
                          return const SizedBox.shrink();
                        }
                        final dateStr = displayData[idx].reportDate;
                        final short = dateStr.length >= 10
                            ? '${dateStr.substring(5, 7)}/${dateStr.substring(8, 10)}'
                            : dateStr;
                        return Text(
                          short,
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 9,
                          ),
                        );
                      },
                    ),
                  ),
                ),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: maxY > 0 ? maxY / 2 : 1,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: value == 0
                        ? AppColors.textTertiary.withValues(alpha: 0.3)
                        : AppColors.border.withValues(alpha: 0.3),
                    strokeWidth: value == 0 ? 1 : 0.5,
                  ),
                ),
                borderData: FlBorderData(show: false),
                barGroups: List.generate(displayData.length, (i) {
                  final pnl = displayData[i].totalPnl.toDouble();
                  final isProfit = pnl >= 0;
                  return BarChartGroupData(
                    x: i,
                    barRods: [
                      BarChartRodData(
                        toY: pnl,
                        color: isProfit ? AppColors.profit : AppColors.loss,
                        width: displayData.length > 10 ? 8 : 14,
                        borderRadius: BorderRadius.vertical(
                          top: isProfit
                              ? const Radius.circular(3)
                              : Radius.zero,
                          bottom: isProfit
                              ? Radius.zero
                              : const Radius.circular(3),
                        ),
                      ),
                    ],
                  );
                }),
              ),
            ),
          ),
          if (displayData.length >= 2) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                const Icon(Icons.show_chart, size: 14, color: AppColors.accent),
                const SizedBox(width: 6),
                const Text(
                  '누적 손익 곡선',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 100,
              child: _buildCumulativeLineChart(displayData, cumulativeData),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCumulativeLineChart(
    List<DailyReport> displayData,
    List<int> cumulativeData,
  ) {
    final spots = <FlSpot>[];
    for (int i = 0; i < cumulativeData.length; i++) {
      spots.add(FlSpot(i.toDouble(), cumulativeData[i].toDouble()));
    }

    final maxAbs = cumulativeData.map((v) => v.abs()).reduce(math.max);
    final yBound = (maxAbs * 1.3).toDouble();
    final isPositive = cumulativeData.last >= 0;

    return LineChart(
      LineChartData(
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: yBound > 0 ? yBound : 1,
          getDrawingHorizontalLine: (value) => FlLine(
            color: value == 0
                ? AppColors.textTertiary.withValues(alpha: 0.3)
                : AppColors.border.withValues(alpha: 0.2),
            strokeWidth: value == 0 ? 1 : 0.5,
          ),
        ),
        titlesData: FlTitlesData(
          show: true,
          topTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
          rightTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
          leftTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
          bottomTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
        ),
        borderData: FlBorderData(show: false),
        minY: -yBound,
        maxY: yBound,
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            preventCurveOverShooting: true,
            color: isPositive ? AppColors.profit : AppColors.loss,
            barWidth: 2,
            isStrokeCapRound: true,
            dotData: FlDotData(
              show: true,
              getDotPainter: (spot, percent, barData, index) {
                final dotPositive = spot.y >= 0;
                return FlDotCirclePainter(
                  radius: 2.5,
                  color: dotPositive ? AppColors.profit : AppColors.loss,
                  strokeWidth: 1,
                  strokeColor: AppColors.card,
                );
              },
            ),
            belowBarData: BarAreaData(
              show: true,
              color: (isPositive ? AppColors.profit : AppColors.loss)
                  .withValues(alpha: 0.06),
            ),
          ),
        ],
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => AppColors.surface,
            tooltipRoundedRadius: 6,
            getTooltipItems: (touchedSpots) {
              return touchedSpots.map((spot) {
                final idx = spot.x.toInt();
                final report = displayData[idx];
                final cumPnl = cumulativeData[idx];
                return LineTooltipItem(
                  '${Formatters.formatDateStringWithDay(report.reportDate)}\n누적 ${cumPnl >= 0 ? '+' : ''}${Formatters.formatKRW(cumPnl)}',
                  TextStyle(
                    color: cumPnl >= 0 ? AppColors.profit : AppColors.loss,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                );
              }).toList();
            },
          ),
        ),
      ),
    );
  }
}
