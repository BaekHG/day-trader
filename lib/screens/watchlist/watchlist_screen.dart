import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/models/watchlist_item.dart';
import 'package:day_trader/providers/watchlist_provider.dart';
import 'package:day_trader/providers/stock_provider.dart';
import 'package:day_trader/widgets/common/stock_list_tile.dart';
import 'package:day_trader/widgets/common/empty_state.dart';

class WatchlistScreen extends ConsumerWidget {
  const WatchlistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final watchlist = ref.watch(watchlistProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('워치리스트'),
        actions: [
          IconButton(icon: const Icon(Icons.sort, size: 22), onPressed: () {}),
          const SizedBox(width: 4),
        ],
      ),
      body: watchlist.isEmpty
          ? EmptyState(
              icon: Icons.visibility_outlined,
              message: '워치리스트가 비어있습니다',
              submessage: '관심 종목을 추가하고 실시간으로\n가격을 추적해보세요',
              actionLabel: '종목 추가',
              onAction: () => context.push('/watchlist/add'),
            )
          : ListView.builder(
              padding: const EdgeInsets.only(top: 8, bottom: 100),
              itemCount: watchlist.length,
              itemBuilder: (context, index) {
                final item = watchlist[index];
                return Dismissible(
                  key: ValueKey(item.symbol),
                  direction: DismissDirection.endToStart,
                  onDismissed: (_) {
                    ref
                        .read(watchlistProvider.notifier)
                        .removeItem(item.symbol);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('${item.name} 삭제됨'),
                        action: SnackBarAction(
                          label: '취소',
                          textColor: AppColors.accent,
                          onPressed: () {
                            ref.read(watchlistProvider.notifier).addItem(item);
                          },
                        ),
                      ),
                    );
                  },
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    color: AppColors.loss.withOpacity(0.15),
                    child: const Icon(
                      Icons.delete_outline,
                      color: AppColors.loss,
                      size: 24,
                    ),
                  ),
                  child: _WatchlistItemTile(item: item),
                );
              },
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/watchlist/add'),
        backgroundColor: AppColors.accent,
        foregroundColor: AppColors.background,
        child: const Icon(Icons.add),
      ),
    );
  }
}

class _WatchlistItemTile extends ConsumerWidget {
  const _WatchlistItemTile({required this.item});

  final WatchlistItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final priceAsync = ref.watch(
      currentPriceProvider((symbol: item.symbol, market: item.market)),
    );

    return priceAsync.when(
      loading: () => StockListTile(
        symbol: item.name,
        name: item.symbol,
        price: '...',
        subtitle: _buildTargetString(item),
        onTap: () => context.push('/chart/${item.symbol}'),
      ),
      error: (err, _) => StockListTile(
        symbol: item.name,
        name: item.symbol,
        price: '로딩 실패',
        subtitle: '$err',
        onTap: () => context.push('/chart/${item.symbol}'),
      ),
      data: (priceData) {
        final currentPrice =
            int.tryParse(priceData['stck_prpr']?.toString() ?? '0') ?? 0;
        final changeRate =
            double.tryParse(priceData['prdy_ctrt']?.toString() ?? '0') ?? 0.0;
        final volume =
            int.tryParse(priceData['acml_vol']?.toString() ?? '0') ?? 0;

        return StockListTile(
          symbol: item.name,
          name: item.symbol,
          price: Formatters.formatKRW(currentPrice),
          changePercent: changeRate,
          subtitle: _buildTargetString(item, volume: volume),
          onTap: () => context.push('/chart/${item.symbol}'),
        );
      },
    );
  }

  String? _buildTargetString(WatchlistItem item, {int? volume}) {
    final parts = <String>[];
    if (item.targetBuyPrice != null) {
      parts.add('매수목표 ${Formatters.formatKRW(item.targetBuyPrice!.toInt())}');
    }
    if (item.targetSellPrice != null) {
      parts.add('매도목표 ${Formatters.formatKRW(item.targetSellPrice!.toInt())}');
    }
    if (parts.isEmpty && volume != null) {
      return '거래량 ${Formatters.formatVolume(volume)}';
    }
    if (parts.isEmpty) return null;
    return parts.join(' · ');
  }
}
