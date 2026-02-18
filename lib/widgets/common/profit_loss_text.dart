import 'package:flutter/material.dart';
import 'package:day_trader/core/theme/app_theme.dart';

class ProfitLossText extends StatelessWidget {
  const ProfitLossText({
    super.key,
    this.amount,
    this.percentage,
    this.fontSize = 14,
    this.fontWeight = FontWeight.w600,
    this.showSign = true,
    this.showPercentage = true,
    this.compact = false,
  });

  final double? amount;
  final double? percentage;
  final double fontSize;
  final FontWeight fontWeight;
  final bool showSign;
  final bool showPercentage;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final value = amount ?? percentage ?? 0;
    final isProfit = value >= 0;
    final color = value == 0
        ? AppColors.textSecondary
        : isProfit
            ? AppColors.profit
            : AppColors.loss;
    final sign = showSign && value > 0 ? '+' : '';

    final parts = <String>[];

    if (amount != null) {
      final absAmount = amount!.abs();
      final formatted = absAmount >= 1000000
          ? '${(absAmount / 10000).toStringAsFixed(1)}만'
          : absAmount
              .toStringAsFixed(absAmount == absAmount.roundToDouble() ? 0 : 2);
      parts.add('$sign${value < 0 ? "-" : ""}$formatted');
    }

    if (percentage != null && showPercentage) {
      final pctStr =
          '${percentage! >= 0 && showSign ? "+" : ""}${percentage!.toStringAsFixed(2)}%';
      if (amount != null) {
        parts.add('($pctStr)');
      } else {
        parts.add(pctStr);
      }
    }

    final text = parts.join(compact ? '' : ' ');

    return Text(
      text,
      style: TextStyle(
        color: color,
        fontSize: fontSize,
        fontWeight: fontWeight,
        letterSpacing: -0.3,
      ),
    );
  }
}

class ProfitLossChip extends StatelessWidget {
  const ProfitLossChip({
    super.key,
    required this.percentage,
    this.compact = false,
  });

  final double percentage;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final isProfit = percentage >= 0;
    final color = percentage == 0
        ? AppColors.textSecondary
        : isProfit
            ? AppColors.profit
            : AppColors.loss;
    final bgColor = percentage == 0
        ? AppColors.surface
        : isProfit
            ? AppColors.profitBg
            : AppColors.lossBg;
    final sign = percentage > 0 ? '+' : '';
    final icon = percentage == 0
        ? Icons.remove
        : isProfit
            ? Icons.arrow_drop_up
            : Icons.arrow_drop_down;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 6 : 8,
        vertical: compact ? 2 : 4,
      ),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: compact ? 14 : 16),
          Text(
            '$sign${percentage.toStringAsFixed(2)}%',
            style: TextStyle(
              color: color,
              fontSize: compact ? 11 : 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
