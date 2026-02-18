import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/models/trade.dart';
import 'package:day_trader/providers/trade_provider.dart';
import 'package:day_trader/providers/stock_provider.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';
import 'package:day_trader/widgets/common/empty_state.dart';

class TradeScreen extends ConsumerStatefulWidget {
  const TradeScreen({super.key});

  @override
  ConsumerState<TradeScreen> createState() => _TradeScreenState();
}

class _TradeScreenState extends ConsumerState<TradeScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
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
        title: const Text('거래 관리'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: '진행중'),
            Tab(text: '완료'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _OpenTradesTab(),
          _ClosedTradesTab(),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/trade/add'),
        backgroundColor: AppColors.accent,
        foregroundColor: AppColors.background,
        icon: const Icon(Icons.add, size: 20),
        label: const Text('거래 기록'),
      ),
    );
  }
}

class _OpenTradesTab extends ConsumerWidget {
  const _OpenTradesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final trades = ref
        .watch(tradesProvider)
        .where((t) => t.status == TradeStatus.open)
        .toList();

    if (trades.isEmpty) {
      return EmptyState(
        icon: Icons.swap_vert,
        message: '진행중인 거래가 없습니다',
        submessage: '새로운 거래를 기록해보세요',
        actionLabel: '거래 기록',
        onAction: () => context.push('/trade/add'),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.only(top: 8, bottom: 100),
      itemCount: trades.length,
      itemBuilder: (context, index) {
        final trade = trades[index];
        return _OpenTradeCard(trade: trade);
      },
    );
  }
}

class _OpenTradeCard extends ConsumerWidget {
  const _OpenTradeCard({required this.trade});

  final Trade trade;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final priceAsync = ref.watch(
      currentPriceProvider((symbol: trade.symbol, market: trade.market)),
    );
    final holdDays = DateTime.now().difference(trade.timestamp).inDays;

    return priceAsync.when(
      loading: () => _buildCard(
        context,
        holdDays: holdDays,
        pnlWidget: const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        entryValue: Formatters.formatKRW(trade.price.toInt()),
        currentValue: '...',
        tradeId: trade.id,
      ),
      error: (err, _) {
        return _buildCard(
          context,
          holdDays: holdDays,
          pnlWidget: IconButton(
            icon: const Icon(Icons.refresh, size: 18, color: AppColors.accent),
            onPressed: () => ref.invalidate(
              currentPriceProvider(
                  (symbol: trade.symbol, market: trade.market)),
            ),
          ),
          entryValue: Formatters.formatKRW(trade.price.toInt()),
          currentValue: '실패',
          tradeId: trade.id,
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
          holdDays: holdDays,
          pnlWidget: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              ProfitLossText(
                amount: unrealizedPnl,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                showPercentage: false,
              ),
              const SizedBox(height: 2),
              ProfitLossChip(
                percentage: pnlPercent,
                compact: true,
              ),
            ],
          ),
          entryValue: Formatters.formatKRW(trade.price.toInt()),
          currentValue: Formatters.formatKRW(currentPrice.toInt()),
          tradeId: trade.id,
        );
      },
    );
  }

  Widget _buildCard(
    BuildContext context, {
    required int holdDays,
    required Widget pnlWidget,
    required String entryValue,
    required String currentValue,
    required String tradeId,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () {},
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
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: AppColors.border, width: 0.5),
                      ),
                      child: Center(
                        child: Text(
                          trade.name.length > 2
                              ? trade.name.substring(0, 2)
                              : trade.name,
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
                          Row(
                            children: [
                              Text(
                                trade.name,
                                style: const TextStyle(
                                  color: AppColors.textPrimary,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(width: 6),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: trade.type == TradeType.buy
                                      ? AppColors.loss.withOpacity(0.15)
                                      : AppColors.profit.withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  trade.type.label,
                                  style: TextStyle(
                                    color: trade.type == TradeType.buy
                                        ? AppColors.loss
                                        : AppColors.profit,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${trade.quantity}주 · D+$holdDays',
                            style: const TextStyle(
                              color: AppColors.textTertiary,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    pnlWidget,
                  ],
                ),
                const SizedBox(height: 10),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      _InfoChip(label: '매입가', value: entryValue),
                      const _DotDivider(),
                      _InfoChip(label: '현재가', value: currentValue),
                      const Spacer(),
                      GestureDetector(
                        onTap: () => context.push('/trade/close/$tradeId'),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            border: Border.all(color: AppColors.accent),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            '청산',
                            style: TextStyle(
                              color: AppColors.accent,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 11),
        ),
        const SizedBox(width: 4),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.textSecondary,
            fontSize: 12,
            fontWeight: FontWeight.w600,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

class _DotDivider extends StatelessWidget {
  const _DotDivider();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(horizontal: 8),
      child: Text(
        '·',
        style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
      ),
    );
  }
}

class _ClosedTradesTab extends ConsumerWidget {
  const _ClosedTradesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final trades = ref
        .watch(tradesProvider)
        .where((t) => t.status == TradeStatus.closed)
        .toList()
      ..sort((a, b) => b.timestamp.compareTo(a.timestamp));

    if (trades.isEmpty) {
      return const EmptyState(
        icon: Icons.check_circle_outline,
        message: '완료된 거래가 없습니다',
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.only(top: 8, bottom: 100),
      itemCount: trades.length,
      itemBuilder: (context, index) {
        final trade = trades[index];
        return _ClosedTradeItem(trade: trade);
      },
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
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: isProfit ? AppColors.profitBg : AppColors.lossBg,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              isProfit
                  ? Icons.trending_up_rounded
                  : Icons.trending_down_rounded,
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
                const SizedBox(height: 2),
                Text(
                  '${trade.quantity}주 · ${Formatters.formatDate(trade.timestamp)}',
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
              ProfitLossText(
                amount: pnl,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                showPercentage: false,
              ),
              const SizedBox(height: 2),
              ProfitLossChip(
                percentage: pnlPercent,
                compact: true,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
