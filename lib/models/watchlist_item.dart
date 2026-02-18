import 'package:equatable/equatable.dart';

import '../core/constants/enums.dart';

class WatchlistItem extends Equatable {
  final String symbol;
  final String name;
  final Market market;
  final double? targetBuyPrice;
  final double? targetSellPrice;
  final DateTime addedAt;
  final String memo;

  WatchlistItem({
    required this.symbol,
    required this.name,
    required this.market,
    this.targetBuyPrice,
    this.targetSellPrice,
    DateTime? addedAt,
    this.memo = '',
  }) : addedAt = addedAt ?? DateTime.now();

  WatchlistItem copyWith({
    String? symbol,
    String? name,
    Market? market,
    double? targetBuyPrice,
    double? targetSellPrice,
    DateTime? addedAt,
    String? memo,
  }) {
    return WatchlistItem(
      symbol: symbol ?? this.symbol,
      name: name ?? this.name,
      market: market ?? this.market,
      targetBuyPrice: targetBuyPrice ?? this.targetBuyPrice,
      targetSellPrice: targetSellPrice ?? this.targetSellPrice,
      addedAt: addedAt ?? this.addedAt,
      memo: memo ?? this.memo,
    );
  }

  factory WatchlistItem.fromJson(Map<String, dynamic> json) {
    return WatchlistItem(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      market: Market.values.firstWhere(
        (e) => e.name == json['market'],
        orElse: () => Market.kr,
      ),
      targetBuyPrice: (json['targetBuyPrice'] as num?)?.toDouble(),
      targetSellPrice: (json['targetSellPrice'] as num?)?.toDouble(),
      addedAt: DateTime.parse(json['addedAt'] as String),
      memo: json['memo'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'name': name,
      'market': market.name,
      'targetBuyPrice': targetBuyPrice,
      'targetSellPrice': targetSellPrice,
      'addedAt': addedAt.toIso8601String(),
      'memo': memo,
    };
  }

  @override
  List<Object?> get props => [
        symbol,
        name,
        market,
        targetBuyPrice,
        targetSellPrice,
        addedAt,
        memo,
      ];
}
