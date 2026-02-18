import 'package:flutter/material.dart';
import 'package:day_trader/core/theme/app_theme.dart';

class StockListTile extends StatelessWidget {
  const StockListTile({
    super.key,
    required this.symbol,
    required this.name,
    required this.price,
    this.changePercent,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.showDivider = true,
  });

  final String symbol;
  final String name;
  final String price;
  final double? changePercent;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pctColor = changePercent == null || changePercent == 0
        ? AppColors.textSecondary
        : changePercent! > 0
            ? AppColors.profit
            : AppColors.loss;
    final sign = changePercent != null && changePercent! > 0 ? '+' : '';

    return Column(
      children: [
        InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
                      symbol.length > 2 ? symbol.substring(0, 2) : symbol,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -0.5,
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
                        symbol,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.3,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        name,
                        style: theme.textTheme.bodySmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: AppColors.textTertiary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                trailing ??
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          price,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                            fontFeatures: const [FontFeature.tabularFigures()],
                          ),
                        ),
                        if (changePercent != null) ...[
                          const SizedBox(height: 2),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: changePercent == 0
                                  ? AppColors.surface
                                  : changePercent! > 0
                                      ? AppColors.profitBg
                                      : AppColors.lossBg,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              '$sign${changePercent!.toStringAsFixed(2)}%',
                              style: TextStyle(
                                color: pctColor,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                fontFeatures: const [
                                  FontFeature.tabularFigures()
                                ],
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
              ],
            ),
          ),
        ),
        if (showDivider) const Divider(indent: 70, endIndent: 16, height: 0.5),
      ],
    );
  }
}
