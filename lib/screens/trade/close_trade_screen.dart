import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';

class CloseTradeScreen extends ConsumerStatefulWidget {
  const CloseTradeScreen({super.key, required this.tradeId});

  final String tradeId;

  @override
  ConsumerState<CloseTradeScreen> createState() => _CloseTradeScreenState();
}

class _CloseTradeScreenState extends ConsumerState<CloseTradeScreen> {
  final _sellPriceController = TextEditingController();
  final _feeController = TextEditingController();

  final String _symbol = '삼성전자';
  final double _entryPrice = 72000;
  final int _quantity = 100;
  final DateTime _entryDate = DateTime(2025, 2, 15);

  double get _sellPrice => double.tryParse(_sellPriceController.text) ?? 0;
  double get _fee => double.tryParse(_feeController.text) ?? 0;
  double get _pnl => (_sellPrice - _entryPrice) * _quantity - _fee;
  double get _pnlPercent =>
      _entryPrice > 0 ? ((_sellPrice - _entryPrice) / _entryPrice) * 100 : 0;
  int get _holdDays => DateTime.now().difference(_entryDate).inDays;

  @override
  void dispose() {
    _sellPriceController.dispose();
    _feeController.dispose();
    super.dispose();
  }

  void _onConfirm() {
    if (_sellPrice <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('매도 가격을 입력해주세요')),
      );
      return;
    }
    context.pop();
  }

  @override
  Widget build(BuildContext context) {
    final isProfit = _pnl >= 0;

    return Scaffold(
      appBar: AppBar(
        title: const Text('포지션 청산'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.card,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border, width: 0.5),
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      Container(
                        width: 46,
                        height: 46,
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(10),
                          border:
                              Border.all(color: AppColors.border, width: 0.5),
                        ),
                        child: const Center(
                          child: Text(
                            '삼성',
                            style: TextStyle(
                              color: AppColors.accent,
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _symbol,
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '보유 D+$_holdDays',
                            style: const TextStyle(
                              color: AppColors.textTertiary,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Divider(height: 0.5),
                  const SizedBox(height: 16),
                  _DetailRow(
                    label: '매입가',
                    value: '₩${_entryPrice.toStringAsFixed(0)}',
                  ),
                  const SizedBox(height: 8),
                  _DetailRow(
                    label: '수량',
                    value: '$_quantity주',
                  ),
                  const SizedBox(height: 8),
                  _DetailRow(
                    label: '매입일',
                    value:
                        '${_entryDate.year}.${_entryDate.month.toString().padLeft(2, '0')}.${_entryDate.day.toString().padLeft(2, '0')}',
                  ),
                  const SizedBox(height: 8),
                  _DetailRow(
                    label: '총 매입금액',
                    value: '₩${(_entryPrice * _quantity).toStringAsFixed(0)}',
                    isBold: true,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              '매도 가격',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _sellPriceController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              autofocus: true,
              decoration: const InputDecoration(
                hintText: '0',
                suffixText: 'KRW',
              ),
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 20),
            const Text(
              '수수료 (선택)',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _feeController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              decoration: const InputDecoration(
                hintText: '자동 계산',
                suffixText: 'KRW',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 24),
            if (_sellPrice > 0) ...[
              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: isProfit
                        ? [AppColors.profitBg, AppColors.card]
                        : [AppColors.lossBg, AppColors.card],
                  ),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isProfit
                        ? AppColors.profit.withOpacity(0.3)
                        : AppColors.loss.withOpacity(0.3),
                    width: 0.5,
                  ),
                ),
                child: Column(
                  children: [
                    const Text(
                      '예상 손익',
                      style: TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ProfitLossText(
                      amount: _pnl,
                      fontSize: 28,
                      fontWeight: FontWeight.w800,
                    ),
                    const SizedBox(height: 4),
                    ProfitLossChip(percentage: _pnlPercent),
                    const SizedBox(height: 12),
                    _DetailRow(
                      label: '매도 총액',
                      value: '₩${(_sellPrice * _quantity).toStringAsFixed(0)}',
                    ),
                    if (_fee > 0) ...[
                      const SizedBox(height: 4),
                      _DetailRow(
                        label: '수수료',
                        value: '₩${_fee.toStringAsFixed(0)}',
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _sellPrice > 0 ? _onConfirm : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: isProfit && _sellPrice > 0
                      ? AppColors.profit
                      : _sellPrice > 0
                          ? AppColors.loss
                          : null,
                ),
                child: Text(_sellPrice > 0
                    ? isProfit
                        ? '수익 확정'
                        : '손절 확정'
                    : '청산 확인'),
              ),
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({
    required this.label,
    required this.value,
    this.isBold = false,
  });

  final String label;
  final String value;
  final bool isBold;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: AppColors.textTertiary,
            fontSize: 13,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: AppColors.textPrimary,
            fontSize: isBold ? 14 : 13,
            fontWeight: isBold ? FontWeight.w700 : FontWeight.w500,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}
