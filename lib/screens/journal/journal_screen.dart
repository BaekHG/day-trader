import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/models/trade.dart';
import 'package:day_trader/providers/trade_provider.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';
import 'package:day_trader/widgets/common/empty_state.dart';

class JournalScreen extends ConsumerWidget {
  const JournalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('매매일지'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_month_outlined, size: 22),
            onPressed: () {},
          ),
          IconButton(
            icon: const Icon(Icons.filter_list, size: 22),
            onPressed: () {},
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 100),
        children: const [
          _StatsHeaderCard(),
          SizedBox(height: 16),
          _JournalList(),
        ],
      ),
    );
  }
}

class _StatsHeaderCard extends ConsumerWidget {
  const _StatsHeaderCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(portfolioSummaryProvider);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        children: [
          Row(
            children: [
              const Icon(Icons.analytics_outlined,
                  size: 16, color: AppColors.accent),
              const SizedBox(width: 6),
              Text(
                '전체 성과',
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _StatItem(
                  label: '총 거래',
                  value: '${summary.totalTrades}',
                  unit: '건',
                ),
              ),
              Expanded(
                child: _StatItem(
                  label: '승률',
                  value: summary.winRate.toStringAsFixed(1),
                  unit: '%',
                  valueColor: summary.winRate > 0 ? AppColors.profit : null,
                ),
              ),
              Expanded(
                child: _StatItem(
                  label: '수익률',
                  value:
                      '${summary.totalProfitLossPercent >= 0 ? '+' : ''}${summary.totalProfitLossPercent.toStringAsFixed(2)}',
                  unit: '%',
                  valueColor: summary.totalProfitLossPercent >= 0
                      ? AppColors.profit
                      : AppColors.loss,
                ),
              ),
              Expanded(
                child: _StatItem(
                  label: '보유중',
                  value: '${summary.openTrades}',
                  unit: '건',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  const _StatItem({
    required this.label,
    required this.value,
    required this.unit,
    this.valueColor,
  });

  final String label;
  final String value;
  final String unit;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(
            color: AppColors.textTertiary,
            fontSize: 11,
          ),
        ),
        const SizedBox(height: 6),
        RichText(
          text: TextSpan(
            children: [
              TextSpan(
                text: value,
                style: TextStyle(
                  color: valueColor ?? AppColors.textPrimary,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              TextSpan(
                text: unit,
                style: TextStyle(
                  color: valueColor ?? AppColors.textSecondary,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _JournalList extends ConsumerStatefulWidget {
  const _JournalList();

  @override
  ConsumerState<_JournalList> createState() => _JournalListState();
}

class _JournalListState extends ConsumerState<_JournalList> {
  final _expandedIndices = <int>{};

  static final _dayOfWeek = ['월', '화', '수', '목', '금', '토', '일'];

  @override
  Widget build(BuildContext context) {
    final allTrades = ref.watch(tradesProvider);

    final grouped = <String, List<Trade>>{};
    for (final trade in allTrades) {
      final key = Formatters.formatDate(trade.timestamp);
      grouped.putIfAbsent(key, () => []).add(trade);
    }

    final sortedKeys = grouped.keys.toList()..sort((a, b) => b.compareTo(a));

    if (sortedKeys.isEmpty) {
      return const EmptyState(
        icon: Icons.book_outlined,
        message: '매매일지가 비어있습니다',
        submessage: '거래를 기록하면 자동으로 일지가 생성됩니다',
      );
    }

    return Column(
      children: List.generate(sortedKeys.length, (index) {
        final dateKey = sortedKeys[index];
        final trades = grouped[dateKey]!;
        final firstDate = trades.first.timestamp;
        final dow = _dayOfWeek[firstDate.weekday - 1];

        double dailyPnl = 0;
        double dailyInvested = 0;
        for (final t in trades) {
          final invested = t.price * t.quantity;
          dailyInvested += invested;
          if (t.status == TradeStatus.closed) {
            dailyPnl += t.totalAmount - invested - t.fee;
          }
        }
        final dailyPnlPct =
            dailyInvested > 0 ? (dailyPnl / dailyInvested) * 100 : 0.0;

        final entry = _JournalEntry(
          date: '$dateKey ($dow)',
          tradesCount: trades.length,
          dailyPnl: dailyPnl,
          dailyPnlPct: dailyPnlPct,
          trades: trades.map((t) {
            final statusLabel = t.status == TradeStatus.closed ? '청산' : '보유';
            final action = '${t.type.label}→$statusLabel';
            final invested = t.price * t.quantity;
            final pnl = t.totalAmount - invested - t.fee;
            final pnlPct = invested > 0 ? (pnl / invested) * 100 : 0.0;
            return _JournalTrade(
                t.name, action, pnlPct, t.memo.isNotEmpty ? t.memo : null);
          }).toList(),
        );

        final isExpanded = _expandedIndices.contains(index);
        return _JournalEntryCard(
          entry: entry,
          isExpanded: isExpanded,
          onToggle: () {
            setState(() {
              if (isExpanded) {
                _expandedIndices.remove(index);
              } else {
                _expandedIndices.add(index);
              }
            });
          },
        );
      }),
    );
  }
}

class _JournalEntry {
  final String date;
  final int tradesCount;
  final double dailyPnl;
  final double dailyPnlPct;
  final List<_JournalTrade> trades;

  _JournalEntry({
    required this.date,
    required this.tradesCount,
    required this.dailyPnl,
    required this.dailyPnlPct,
    required this.trades,
  });
}

class _JournalTrade {
  final String symbol;
  final String action;
  final double pnlPct;
  final String? memo;

  _JournalTrade(this.symbol, this.action, this.pnlPct, [this.memo]);
}

class _JournalEntryCard extends StatelessWidget {
  const _JournalEntryCard({
    required this.entry,
    required this.isExpanded,
    required this.onToggle,
  });

  final _JournalEntry entry;
  final bool isExpanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final isProfit = entry.dailyPnl >= 0;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        children: [
          InkWell(
            onTap: onToggle,
            borderRadius: isExpanded
                ? const BorderRadius.vertical(top: Radius.circular(12))
                : BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Container(
                    width: 6,
                    height: 40,
                    decoration: BoxDecoration(
                      color: isProfit ? AppColors.profit : AppColors.loss,
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.date,
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${entry.tradesCount}건 거래',
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                  ProfitLossText(
                    amount: entry.dailyPnl,
                    percentage: entry.dailyPnlPct,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                  const SizedBox(width: 8),
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
            ),
          ),
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
      children: [
        const Divider(height: 0.5),
        ...entry.trades.map((trade) => Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: trade.pnlPct >= 0
                          ? AppColors.profitBg
                          : AppColors.lossBg,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Icon(
                      trade.pnlPct >= 0
                          ? Icons.arrow_upward_rounded
                          : Icons.arrow_downward_rounded,
                      color:
                          trade.pnlPct >= 0 ? AppColors.profit : AppColors.loss,
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              trade.symbol,
                              style: const TextStyle(
                                color: AppColors.textPrimary,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              trade.action,
                              style: const TextStyle(
                                color: AppColors.textTertiary,
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                        if (trade.memo != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            trade.memo!,
                            style: const TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 12,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  ProfitLossChip(
                    percentage: trade.pnlPct,
                    compact: true,
                  ),
                ],
              ),
            )),
        const SizedBox(height: 6),
      ],
    );
  }
}
