import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/widgets/common/market_toggle.dart';

class AddTradeScreen extends ConsumerStatefulWidget {
  const AddTradeScreen({super.key});

  @override
  ConsumerState<AddTradeScreen> createState() => _AddTradeScreenState();
}

class _AddTradeScreenState extends ConsumerState<AddTradeScreen> {
  Market _market = Market.kr;
  TradeType _tradeType = TradeType.buy;
  final _stockController = TextEditingController();
  final _priceController = TextEditingController();
  final _quantityController = TextEditingController();
  final _feeController = TextEditingController();
  final _memoController = TextEditingController();
  String? _selectedSymbol;

  double get _price => double.tryParse(_priceController.text) ?? 0;
  int get _quantity => int.tryParse(_quantityController.text) ?? 0;
  double get _fee => double.tryParse(_feeController.text) ?? 0;
  double get _totalAmount => _price * _quantity + _fee;

  @override
  void dispose() {
    _stockController.dispose();
    _priceController.dispose();
    _quantityController.dispose();
    _feeController.dispose();
    _memoController.dispose();
    super.dispose();
  }

  void _onSave() {
    if (_selectedSymbol == null || _price <= 0 || _quantity <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('필수 항목을 입력해주세요')),
      );
      return;
    }
    context.pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('거래 기록'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: MarketToggle(
                selected: _market,
                onChanged: (m) => setState(() => _market = m),
              ),
            ),
            const SizedBox(height: 20),
            _buildLabel('종목'),
            const SizedBox(height: 8),
            TextField(
              controller: _stockController,
              decoration: InputDecoration(
                hintText: '종목명 또는 코드 검색',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _selectedSymbol != null
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () => setState(() {
                          _selectedSymbol = null;
                          _stockController.clear();
                        }),
                      )
                    : null,
              ),
              onTap: () => _showStockSearch(),
              readOnly: true,
            ),
            const SizedBox(height: 20),
            _buildLabel('거래 유형'),
            const SizedBox(height: 8),
            Row(
              children: TradeType.values.map((type) {
                final isSelected = type == _tradeType;
                final isBuy = type == TradeType.buy;
                final activeColor = isBuy ? AppColors.loss : AppColors.accent;

                return Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(
                      right: isBuy ? 6 : 0,
                      left: isBuy ? 0 : 6,
                    ),
                    child: GestureDetector(
                      onTap: () => setState(() => _tradeType = type),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? activeColor.withOpacity(0.15)
                              : AppColors.surface,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: isSelected ? activeColor : AppColors.border,
                            width: isSelected ? 1.5 : 0.5,
                          ),
                        ),
                        child: Center(
                          child: Text(
                            type.label,
                            style: TextStyle(
                              color: isSelected
                                  ? activeColor
                                  : AppColors.textSecondary,
                              fontSize: 15,
                              fontWeight: isSelected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 20),
            _buildLabel('가격'),
            const SizedBox(height: 8),
            TextField(
              controller: _priceController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              decoration: InputDecoration(
                hintText: '0',
                suffixText: _market == Market.kr ? 'KRW' : 'USD',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 20),
            _buildLabel('수량'),
            const SizedBox(height: 8),
            TextField(
              controller: _quantityController,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                hintText: '0',
                suffixText: '주',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 20),
            _buildLabel('수수료 (선택)'),
            const SizedBox(height: 8),
            TextField(
              controller: _feeController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              decoration: InputDecoration(
                hintText: '자동 계산',
                suffixText: _market == Market.kr ? 'KRW' : 'USD',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 20),
            _buildLabel('메모 (선택)'),
            const SizedBox(height: 8),
            TextField(
              controller: _memoController,
              maxLines: 3,
              decoration: const InputDecoration(
                hintText: '거래 사유, 전략 등을 기록하세요',
              ),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border, width: 0.5),
              ),
              child: Row(
                children: [
                  const Text(
                    '총 거래금액',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 14,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _totalAmount > 0
                        ? _market == Market.kr
                            ? '₩${_totalAmount.toStringAsFixed(0)}'
                            : '\$${_totalAmount.toStringAsFixed(2)}'
                        : '—',
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _onSave,
                child: const Text('저장'),
              ),
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  Widget _buildLabel(String text) {
    return Text(
      text,
      style: const TextStyle(
        color: AppColors.textSecondary,
        fontSize: 13,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  void _showStockSearch() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.9,
        expand: false,
        builder: (ctx, scrollController) => _StockSearchSheet(
          market: _market,
          scrollController: scrollController,
          onSelect: (symbol, name) {
            setState(() {
              _selectedSymbol = symbol;
              _stockController.text = '$symbol · $name';
            });
            Navigator.of(ctx).pop();
          },
        ),
      ),
    );
  }
}

class _StockSearchSheet extends StatefulWidget {
  const _StockSearchSheet({
    required this.market,
    required this.scrollController,
    required this.onSelect,
  });

  final Market market;
  final ScrollController scrollController;
  final void Function(String symbol, String name) onSelect;

  @override
  State<_StockSearchSheet> createState() => _StockSearchSheetState();
}

class _StockSearchSheetState extends State<_StockSearchSheet> {
  final _controller = TextEditingController();
  String _query = '';

  final _mockStocks = <_Stock>[
    _Stock('삼성전자', '005930', Market.kr),
    _Stock('SK하이닉스', '000660', Market.kr),
    _Stock('카카오', '035720', Market.kr),
    _Stock('네이버', '035420', Market.kr),
    _Stock('현대차', '005380', Market.kr),
    _Stock('AAPL', 'Apple Inc.', Market.us),
    _Stock('TSLA', 'Tesla Inc.', Market.us),
    _Stock('NVDA', 'NVIDIA Corp.', Market.us),
    _Stock('MSFT', 'Microsoft Corp.', Market.us),
    _Stock('AMZN', 'Amazon.com', Market.us),
  ];

  List<_Stock> get _filtered {
    final byMarket =
        _mockStocks.where((s) => s.market == widget.market).toList();
    if (_query.isEmpty) return byMarket;
    return byMarket
        .where((s) =>
            s.symbol.toLowerCase().contains(_query.toLowerCase()) ||
            s.name.toLowerCase().contains(_query.toLowerCase()))
        .toList();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          margin: const EdgeInsets.only(top: 8),
          width: 36,
          height: 4,
          decoration: BoxDecoration(
            color: AppColors.border,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _controller,
            autofocus: true,
            onChanged: (v) => setState(() => _query = v),
            decoration: const InputDecoration(
              hintText: '종목 검색',
              prefixIcon: Icon(Icons.search, size: 20),
            ),
          ),
        ),
        Expanded(
          child: ListView.separated(
            controller: widget.scrollController,
            itemCount: _filtered.length,
            separatorBuilder: (_, __) => const Divider(indent: 60, height: 0.5),
            itemBuilder: (context, index) {
              final stock = _filtered[index];
              return ListTile(
                leading: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppColors.border, width: 0.5),
                  ),
                  child: Center(
                    child: Text(
                      stock.symbol.length > 2
                          ? stock.symbol.substring(0, 2)
                          : stock.symbol,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                title: Text(
                  stock.symbol,
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 14),
                ),
                subtitle: Text(
                  stock.name,
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
                onTap: () => widget.onSelect(stock.symbol, stock.name),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Stock {
  final String symbol;
  final String name;
  final Market market;

  _Stock(this.symbol, this.name, this.market);
}
