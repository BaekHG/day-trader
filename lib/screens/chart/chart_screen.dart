import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/widgets/common/profit_loss_text.dart';

class ChartScreen extends ConsumerStatefulWidget {
  const ChartScreen({super.key, required this.symbol});

  final String symbol;

  @override
  ConsumerState<ChartScreen> createState() => _ChartScreenState();
}

class _ChartScreenState extends ConsumerState<ChartScreen> {
  ChartInterval _interval = ChartInterval.daily;
  final _activeIndicators = <String>{};

  @override
  Widget build(BuildContext context) {
    const stockName = '삼성전자';
    const currentPrice = '₩73,200';
    const changePercent = 1.67;
    const changeAmount = '+₩1,200';

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.symbol,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const Text(
              stockName,
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.star_border, size: 22),
            onPressed: () {},
          ),
          IconButton(
            icon: const Icon(Icons.share_outlined, size: 22),
            onPressed: () {},
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 40),
        children: [
          _PriceHeader(
            price: currentPrice,
            changeAmount: changeAmount,
            changePercent: changePercent,
          ),
          const SizedBox(height: 16),
          _IntervalSelector(
            selected: _interval,
            onChanged: (v) => setState(() => _interval = v),
          ),
          const SizedBox(height: 8),
          const _ChartPlaceholder(),
          const SizedBox(height: 8),
          const _VolumePlaceholder(),
          const SizedBox(height: 12),
          _IndicatorToggles(
            active: _activeIndicators,
            onToggle: (indicator) {
              setState(() {
                if (_activeIndicators.contains(indicator)) {
                  _activeIndicators.remove(indicator);
                } else {
                  _activeIndicators.add(indicator);
                }
              });
            },
          ),
          const SizedBox(height: 20),
          _QuickActions(symbol: widget.symbol),
        ],
      ),
    );
  }
}

class _PriceHeader extends StatelessWidget {
  const _PriceHeader({
    required this.price,
    required this.changeAmount,
    required this.changePercent,
  });

  final String price;
  final String changeAmount;
  final double changePercent;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            price,
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 32,
              fontWeight: FontWeight.w800,
              letterSpacing: -1.5,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Text(
                changeAmount,
                style: TextStyle(
                  color: changePercent >= 0 ? AppColors.profit : AppColors.loss,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(width: 8),
              ProfitLossChip(percentage: changePercent),
            ],
          ),
        ],
      ),
    );
  }
}

class _IntervalSelector extends StatelessWidget {
  const _IntervalSelector({
    required this.selected,
    required this.onChanged,
  });

  final ChartInterval selected;
  final ValueChanged<ChartInterval> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: ChartInterval.values.map((interval) {
          final isSelected = interval == selected;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: GestureDetector(
              onTap: () => onChanged(interval),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                decoration: BoxDecoration(
                  color: isSelected ? AppColors.accent : AppColors.surface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: isSelected ? AppColors.accent : AppColors.border,
                    width: 0.5,
                  ),
                ),
                child: Text(
                  interval.label,
                  style: TextStyle(
                    color: isSelected
                        ? AppColors.background
                        : AppColors.textSecondary,
                    fontSize: 12,
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _ChartPlaceholder extends StatelessWidget {
  const _ChartPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 280,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(painter: _GridPainter()),
          ),
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    shape: BoxShape.circle,
                    border: Border.all(color: AppColors.border, width: 0.5),
                  ),
                  child: const Icon(
                    Icons.candlestick_chart_outlined,
                    color: AppColors.textTertiary,
                    size: 26,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '차트 영역',
                  style: TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  '캔들스틱 차트가 여기에 표시됩니다',
                  style: TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
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

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.border.withOpacity(0.3)
      ..strokeWidth = 0.5;

    for (var i = 1; i < 5; i++) {
      final y = size.height * i / 5;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
    for (var i = 1; i < 8; i++) {
      final x = size.width * i / 8;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _VolumePlaceholder extends StatelessWidget {
  const _VolumePlaceholder();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 80,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(painter: _VolumeBarPainter()),
          ),
          const Center(
            child: Text(
              '거래량',
              style: TextStyle(
                color: AppColors.textTertiary,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _VolumeBarPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.accent.withOpacity(0.1);
    final rng = [
      0.3,
      0.5,
      0.7,
      0.4,
      0.8,
      0.6,
      0.3,
      0.9,
      0.5,
      0.4,
      0.6,
      0.7,
      0.3,
      0.5,
      0.8
    ];
    final barWidth = size.width / (rng.length * 1.5);

    for (var i = 0; i < rng.length; i++) {
      final x = i * size.width / rng.length + barWidth * 0.25;
      final h = size.height * rng[i] * 0.8;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x, size.height - h, barWidth, h),
          const Radius.circular(2),
        ),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _IndicatorToggles extends StatelessWidget {
  const _IndicatorToggles({
    required this.active,
    required this.onToggle,
  });

  final Set<String> active;
  final ValueChanged<String> onToggle;

  static const _indicators = [
    ('MA', '이동평균'),
    ('RSI', 'RSI'),
    ('MACD', 'MACD'),
    ('BB', '볼린저'),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '보조지표',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _indicators.map((ind) {
              final isActive = active.contains(ind.$1);
              return GestureDetector(
                onTap: () => onToggle(ind.$1),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppColors.accent.withOpacity(0.15)
                        : AppColors.surface,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: isActive ? AppColors.accent : AppColors.border,
                      width: isActive ? 1 : 0.5,
                    ),
                  ),
                  child: Text(
                    ind.$2,
                    style: TextStyle(
                      color:
                          isActive ? AppColors.accent : AppColors.textSecondary,
                      fontSize: 13,
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.symbol});

  final String symbol;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.visibility_outlined, size: 18),
              label: const Text('워치리스트 추가'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton.icon(
              onPressed: () => context.push('/trade/add'),
              icon: const Icon(Icons.edit_outlined, size: 18),
              label: const Text('매수 기록'),
            ),
          ),
        ],
      ),
    );
  }
}
