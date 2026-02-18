import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/core/constants/app_constants.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/models/trade.dart';
import 'package:day_trader/providers/trade_provider.dart';
import 'package:day_trader/providers/stock_provider.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';
import 'package:day_trader/widgets/common/loading_shimmer.dart';
import 'package:day_trader/widgets/common/empty_state.dart';
import 'package:day_trader/main.dart' show initError;

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _isLoading = false;

  Future<void> _onRefresh() async {
    setState(() => _isLoading = true);
    for (final trade in ref.read(tradesProvider)) {
      if (trade.status == TradeStatus.open) {
        ref.invalidate(
          currentPriceProvider((symbol: trade.symbol, market: trade.market)),
        );
      }
    }
    await Future.delayed(const Duration(milliseconds: 400));
    setState(() => _isLoading = false);
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
                color: AppColors.profit,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            const Text('Day Trader'),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined, size: 22),
            onPressed: () {},
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined, size: 22),
            onPressed: () {},
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _onRefresh,
        color: AppColors.accent,
        backgroundColor: AppColors.card,
        child: _isLoading
            ? const _LoadingState()
            : ListView(
                padding: const EdgeInsets.only(bottom: 100),
                children: [
                  const _ApiStatusBanner(),
                  const _TodayPnlCard(),
                  const SizedBox(height: 4),
                  const _PortfolioSummaryRow(),
                  const SizedBox(height: 16),
                  _SectionHeader(
                    title: '보유 포지션',
                    trailing: '전체보기',
                    onTrailingTap: () {},
                  ),
                  const _ActiveTradesList(),
                  const SizedBox(height: 16),
                  _SectionHeader(
                    title: '최근 청산',
                    trailing: '전체보기',
                    onTrailingTap: () {},
                  ),
                  const _RecentClosedList(),
                ],
              ),
      ),
    );
  }
}

class _ApiStatusBanner extends StatelessWidget {
  const _ApiStatusBanner();

  @override
  Widget build(BuildContext context) {
    final hasKey = AppConstants.kisAppKey.isNotEmpty;
    final hasSecret = AppConstants.kisAppSecret.isNotEmpty;
    final hasAccount = AppConstants.kisAccountNo.isNotEmpty;
    final allGood = hasKey && hasSecret && hasAccount && initError == null;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: allGood ? AppColors.profitBg : AppColors.lossBg,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: allGood ? AppColors.profit : AppColors.loss,
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                allGood ? Icons.check_circle : Icons.warning_amber_rounded,
                color: allGood ? AppColors.profit : AppColors.loss,
                size: 18,
              ),
              const SizedBox(width: 6),
              Text(
                allGood ? 'API 연결 상태' : 'API 설정 문제',
                style: TextStyle(
                  color: allGood ? AppColors.profit : AppColors.loss,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (initError != null)
            Text(
              'Init Error: $initError',
              style: const TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
              ),
            ),
          Text(
            '${hasKey ? "✅" : "❌"} APP_KEY: ${hasKey ? AppConstants.kisAppKey.substring(0, 6) : "없음"}',
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
            ),
          ),
          Text(
            '${hasSecret ? "✅" : "❌"} APP_SECRET: ${hasSecret ? "설정됨" : "없음"}',
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
            ),
          ),
          Text(
            '${hasAccount ? "✅" : "❌"} ACCOUNT: ${hasAccount ? AppConstants.kisAccountNo : "없음"}',
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const SingleChildScrollView(
      physics: NeverScrollableScrollPhysics(),
      child: Column(
        children: [
          CardShimmer(height: 140),
          SizedBox(height: 4),
          CardShimmer(height: 70),
          SizedBox(height: 16),
          StockListShimmer(itemCount: 4),
        ],
      ),
    );
  }
}

class _TodayPnlCard extends ConsumerWidget {
  const _TodayPnlCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final todayPnl = ref.watch(todayPnLProvider);
    final summary = ref.watch(portfolioSummaryProvider);
    final isProfit = todayPnl >= 0;

    final closedTrades = ref
        .watch(tradesProvider)
        .where((t) => t.status == TradeStatus.closed)
        .toList();
    final now = DateTime.now();
    final todayStart = DateTime(now.year, now.month, now.day);
    final todayClosed = closedTrades
        .where((t) => t.timestamp.isAfter(todayStart))
        .toList();
    final wins = todayClosed.where((t) {
      final pnl = t.totalAmount - (t.price * t.quantity) - t.fee;
      return pnl >= 0;
    }).length;
    final losses = todayClosed.length - wins;
    final winRateToday = todayClosed.isEmpty
        ? 0.0
        : (wins / todayClosed.length) * 100;

    final todayPnlPct = summary.totalInvested > 0
        ? (todayPnl / summary.totalInvested) * 100
        : 0.0;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isProfit
              ? [AppColors.profitBg, AppColors.card, AppColors.card]
              : [AppColors.lossBg, AppColors.card, AppColors.card],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isProfit
              ? AppColors.profit.withOpacity(0.2)
              : AppColors.loss.withOpacity(0.2),
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.calendar_today_outlined,
                size: 14,
                color: theme.textTheme.bodySmall?.color,
              ),
              const SizedBox(width: 6),
              Text(
                '오늘의 수익',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '실시간',
                  style: TextStyle(
                    color: AppColors.profit,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${todayPnl >= 0 ? '+' : ''}${Formatters.formatKRW(todayPnl.toInt())}',
                style: TextStyle(
                  color: isProfit ? AppColors.profit : AppColors.loss,
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(width: 10),
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: ProfitLossChip(percentage: todayPnlPct),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _MiniStat(label: '승', value: '$wins', color: AppColors.profit),
              const SizedBox(width: 16),
              _MiniStat(label: '패', value: '$losses', color: AppColors.loss),
              const SizedBox(width: 16),
              _MiniStat(
                label: '승률',
                value: '${winRateToday.toStringAsFixed(1)}%',
                color: AppColors.accent,
              ),
            ],
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
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
        ),
        const SizedBox(width: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 13,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

class _PortfolioSummaryRow extends ConsumerWidget {
  const _PortfolioSummaryRow();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(portfolioSummaryProvider);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Row(
        children: [
          Expanded(
            child: _SummaryItem(
              label: '총 투자금',
              value: Formatters.formatKRW(summary.totalInvested.toInt()),
            ),
          ),
          const _VerticalDivider(),
          Expanded(
            child: _SummaryItem(
              label: '평가금액',
              value: Formatters.formatKRW(summary.totalCurrentValue.toInt()),
            ),
          ),
          const _VerticalDivider(),
          Expanded(
            child: _SummaryItem(
              label: '수익률',
              value: Formatters.formatPercent(summary.totalProfitLossPercent),
              valueColor: summary.totalProfitLossPercent >= 0
                  ? AppColors.profit
                  : AppColors.loss,
            ),
          ),
        ],
      ),
    );
  }
}

class _VerticalDivider extends StatelessWidget {
  const _VerticalDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 0.5,
      height: 32,
      color: AppColors.border,
      margin: const EdgeInsets.symmetric(horizontal: 4),
    );
  }
}

class _SummaryItem extends StatelessWidget {
  const _SummaryItem({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

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
            color: valueColor ?? AppColors.textPrimary,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    this.trailing,
    this.onTrailingTap,
  });

  final String title;
  final String? trailing;
  final VoidCallback? onTrailingTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        children: [
          Text(
            title,
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          if (trailing != null)
            GestureDetector(
              onTap: onTrailingTap,
              child: Text(
                trailing!,
                style: const TextStyle(
                  color: AppColors.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ActiveTradesList extends ConsumerWidget {
  const _ActiveTradesList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final openTrades = ref
        .watch(tradesProvider)
        .where((t) => t.status == TradeStatus.open)
        .toList();

    if (openTrades.isEmpty) {
      return const EmptyState(
        icon: Icons.trending_up,
        message: '보유 중인 포지션이 없습니다',
        submessage: '새로운 거래를 기록해보세요',
      );
    }

    return Column(
      children: openTrades
          .map((trade) => _ActiveTradeItem(trade: trade))
          .toList(),
    );
  }
}

class _ActiveTradeItem extends ConsumerWidget {
  const _ActiveTradeItem({required this.trade});

  final Trade trade;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final priceAsync = ref.watch(
      currentPriceProvider((symbol: trade.symbol, market: trade.market)),
    );

    return priceAsync.when(
      loading: () => _buildCard(
        context,
        trailing: const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
      error: (err, _) {
        return _buildCard(
          context,
          trailing: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              GestureDetector(
                onTap: () => ref.invalidate(
                  currentPriceProvider((
                    symbol: trade.symbol,
                    market: trade.market,
                  )),
                ),
                child: const Icon(
                  Icons.refresh,
                  size: 18,
                  color: AppColors.accent,
                ),
              ),
              const SizedBox(height: 2),
              SizedBox(
                width: 140,
                child: Text(
                  '$err',
                  style: const TextStyle(color: AppColors.loss, fontSize: 9),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        );
      },
      data: (priceData) {
        final currentPrice =
            (int.tryParse(priceData['stck_prpr']?.toString() ?? '0') ?? 0)
                .toDouble();
        final unrealizedPnl = trade.profitLoss(currentPrice);
        final pnlPercent = trade.profitLossPercent(currentPrice);

        return _buildCard(
          context,
          trailing: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                Formatters.formatKRW(currentPrice.toInt()),
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(height: 2),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ProfitLossText(
                    amount: unrealizedPnl,
                    fontSize: 12,
                    showSign: true,
                    showPercentage: false,
                  ),
                  const SizedBox(width: 4),
                  ProfitLossChip(percentage: pnlPercent, compact: true),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildCard(BuildContext context, {required Widget trailing}) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: AppColors.border, width: 0.5),
            ),
            child: Center(
              child: Text(
                trade.name.length > 2 ? trade.name.substring(0, 2) : trade.name,
                style: const TextStyle(
                  color: AppColors.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  trade.name,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${trade.quantity}주 · 평균 ${Formatters.formatKRW(trade.price.toInt())}',
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          trailing,
        ],
      ),
    );
  }
}

class _RecentClosedList extends ConsumerWidget {
  const _RecentClosedList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final closedTrades =
        ref
            .watch(tradesProvider)
            .where((t) => t.status == TradeStatus.closed)
            .toList()
          ..sort((a, b) => b.timestamp.compareTo(a.timestamp));

    final recent = closedTrades.take(5).toList();

    if (recent.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(
          child: Text(
            '최근 청산 내역이 없습니다',
            style: TextStyle(color: AppColors.textTertiary, fontSize: 13),
          ),
        ),
      );
    }

    return Column(
      children: recent.map((trade) => _ClosedTradeItem(trade: trade)).toList(),
    );
  }
}

class _ClosedTradeItem extends StatelessWidget {
  const _ClosedTradeItem({required this.trade});

  final Trade trade;

  @override
  Widget build(BuildContext context) {
    final pnl = trade.totalAmount - (trade.price * trade.quantity) - trade.fee;
    final pnlPercent = (trade.price * trade.quantity) > 0
        ? (pnl / (trade.price * trade.quantity)) * 100
        : 0.0;
    final isProfit = pnl >= 0;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: isProfit ? AppColors.profitBg : AppColors.lossBg,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              isProfit
                  ? Icons.arrow_upward_rounded
                  : Icons.arrow_downward_rounded,
              color: isProfit ? AppColors.profit : AppColors.loss,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  trade.name,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 1),
                Text(
                  '${trade.quantity}주',
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          ProfitLossText(amount: pnl, percentage: pnlPercent, fontSize: 13),
        ],
      ),
    );
  }
}
