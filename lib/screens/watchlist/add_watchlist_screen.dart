import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/widgets/common/market_toggle.dart';
import 'package:day_trader/widgets/common/empty_state.dart';

class AddWatchlistScreen extends ConsumerStatefulWidget {
  const AddWatchlistScreen({super.key});

  @override
  ConsumerState<AddWatchlistScreen> createState() => _AddWatchlistScreenState();
}

class _AddWatchlistScreenState extends ConsumerState<AddWatchlistScreen> {
  Market _selectedMarket = Market.kr;
  final _searchController = TextEditingController();
  String _query = '';

  final _mockResults = <_SearchResult>[
    _SearchResult('삼성전자', '005930', Market.kr),
    _SearchResult('삼성SDI', '006400', Market.kr),
    _SearchResult('삼성물산', '028260', Market.kr),
    _SearchResult('삼성생명', '032830', Market.kr),
    _SearchResult('AAPL', 'Apple Inc.', Market.us),
    _SearchResult('AMZN', 'Amazon.com Inc.', Market.us),
    _SearchResult('AMD', 'Advanced Micro Devices', Market.us),
  ];

  List<_SearchResult> get _filteredResults {
    if (_query.isEmpty) return [];
    return _mockResults
        .where((r) =>
            r.market == _selectedMarket &&
            (r.symbol.toLowerCase().contains(_query.toLowerCase()) ||
                r.name.toLowerCase().contains(_query.toLowerCase())))
        .toList();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _showTargetPriceDialog(_SearchResult result) {
    final buyController = TextEditingController();
    final sellController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border, width: 0.5),
              ),
              child: Center(
                child: Text(
                  result.symbol.length > 2
                      ? result.symbol.substring(0, 2)
                      : result.symbol,
                  style: const TextStyle(
                    color: AppColors.accent,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    result.symbol,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text(
                    result.name,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Divider(),
            const SizedBox(height: 8),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '목표가 설정 (선택사항)',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                ),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: buyController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: '매수 목표가',
                prefixIcon: Icon(Icons.arrow_downward,
                    color: AppColors.profit, size: 18),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: sellController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: '매도 목표가',
                prefixIcon:
                    Icon(Icons.arrow_upward, color: AppColors.loss, size: 18),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              _onAdd(result);
            },
            child: const Text('추가'),
          ),
        ],
      ),
    );
  }

  void _onAdd(_SearchResult result) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${result.symbol}이(가) 워치리스트에 추가되었습니다')),
    );
    context.pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('종목 추가'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(
              children: [
                MarketToggle(
                  selected: _selectedMarket,
                  onChanged: (m) => setState(() {
                    _selectedMarket = m;
                    _query = _searchController.text;
                  }),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _searchController,
                  autofocus: true,
                  onChanged: (v) => setState(() => _query = v),
                  decoration: InputDecoration(
                    hintText: '종목명 또는 코드 검색',
                    prefixIcon: const Icon(Icons.search, size: 20),
                    suffixIcon: _query.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 18),
                            onPressed: () {
                              _searchController.clear();
                              setState(() => _query = '');
                            },
                          )
                        : null,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 0.5),
          Expanded(
            child: _query.isEmpty
                ? const EmptyState(
                    icon: Icons.search,
                    message: '종목을 검색해주세요',
                    submessage: '종목명 또는 코드로 검색할 수 있습니다',
                  )
                : _filteredResults.isEmpty
                    ? EmptyState(
                        icon: Icons.search_off,
                        message: '검색 결과가 없습니다',
                        submessage: '"$_query"에 대한 결과를 찾을 수 없습니다',
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: _filteredResults.length,
                        separatorBuilder: (_, __) =>
                            const Divider(indent: 60, height: 0.5),
                        itemBuilder: (context, index) {
                          final result = _filteredResults[index];
                          return ListTile(
                            leading: Container(
                              width: 42,
                              height: 42,
                              decoration: BoxDecoration(
                                color: AppColors.surface,
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(
                                  color: AppColors.border,
                                  width: 0.5,
                                ),
                              ),
                              child: Center(
                                child: Text(
                                  result.symbol.length > 2
                                      ? result.symbol.substring(0, 2)
                                      : result.symbol,
                                  style: const TextStyle(
                                    color: AppColors.accent,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                            ),
                            title: Text(
                              result.symbol,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                              ),
                            ),
                            subtitle: Text(
                              result.name,
                              style: const TextStyle(
                                color: AppColors.textTertiary,
                                fontSize: 12,
                              ),
                            ),
                            trailing: IconButton(
                              icon: const Icon(
                                Icons.add_circle_outline,
                                color: AppColors.accent,
                              ),
                              onPressed: () => _showTargetPriceDialog(result),
                            ),
                            onTap: () => _showTargetPriceDialog(result),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _SearchResult {
  final String symbol;
  final String name;
  final Market market;

  _SearchResult(this.symbol, this.name, this.market);
}
