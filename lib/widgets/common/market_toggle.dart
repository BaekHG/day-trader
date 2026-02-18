import 'package:flutter/material.dart';
import 'package:day_trader/core/constants/enums.dart';
import 'package:day_trader/core/theme/app_theme.dart';

class MarketToggle extends StatelessWidget {
  const MarketToggle({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  final Market selected;
  final ValueChanged<Market> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      padding: const EdgeInsets.all(3),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: Market.values.map((market) {
          final isSelected = market == selected;
          return GestureDetector(
            onTap: () => onChanged(market),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: isSelected ? AppColors.accent : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    market == Market.kr ? '🇰🇷' : '🇺🇸',
                    style: const TextStyle(fontSize: 14),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    market.label,
                    style: TextStyle(
                      color: isSelected
                          ? AppColors.background
                          : AppColors.textSecondary,
                      fontSize: 13,
                      fontWeight:
                          isSelected ? FontWeight.w700 : FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}
