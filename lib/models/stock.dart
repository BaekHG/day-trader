import 'package:equatable/equatable.dart';

import '../core/constants/enums.dart';

class Stock extends Equatable {
  final String symbol;
  final String name;
  final Market market;
  final double currentPrice;
  final double previousClose;
  final double changePercent;
  final int volume;
  final double high;
  final double low;
  final double open;

  const Stock({
    required this.symbol,
    required this.name,
    required this.market,
    required this.currentPrice,
    required this.previousClose,
    required this.changePercent,
    required this.volume,
    this.high = 0,
    this.low = 0,
    this.open = 0,
  });

  double get changeAmount => currentPrice - previousClose;

  bool get isProfit => changePercent >= 0;

  Stock copyWith({
    String? symbol,
    String? name,
    Market? market,
    double? currentPrice,
    double? previousClose,
    double? changePercent,
    int? volume,
    double? high,
    double? low,
    double? open,
  }) {
    return Stock(
      symbol: symbol ?? this.symbol,
      name: name ?? this.name,
      market: market ?? this.market,
      currentPrice: currentPrice ?? this.currentPrice,
      previousClose: previousClose ?? this.previousClose,
      changePercent: changePercent ?? this.changePercent,
      volume: volume ?? this.volume,
      high: high ?? this.high,
      low: low ?? this.low,
      open: open ?? this.open,
    );
  }

  factory Stock.fromJson(Map<String, dynamic> json) {
    return Stock(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      market: Market.values.firstWhere(
        (e) => e.name == json['market'],
        orElse: () => Market.kr,
      ),
      currentPrice: (json['currentPrice'] as num).toDouble(),
      previousClose: (json['previousClose'] as num).toDouble(),
      changePercent: (json['changePercent'] as num).toDouble(),
      volume: json['volume'] as int,
      high: (json['high'] as num?)?.toDouble() ?? 0,
      low: (json['low'] as num?)?.toDouble() ?? 0,
      open: (json['open'] as num?)?.toDouble() ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'name': name,
      'market': market.name,
      'currentPrice': currentPrice,
      'previousClose': previousClose,
      'changePercent': changePercent,
      'volume': volume,
      'high': high,
      'low': low,
      'open': open,
    };
  }

  @override
  List<Object?> get props => [
        symbol,
        name,
        market,
        currentPrice,
        previousClose,
        changePercent,
        volume,
        high,
        low,
        open,
      ];
}
