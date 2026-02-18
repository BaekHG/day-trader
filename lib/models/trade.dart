import 'package:equatable/equatable.dart';
import 'package:uuid/uuid.dart';

import '../core/constants/enums.dart';

class Trade extends Equatable {
  final String id;
  final String symbol;
  final String name;
  final Market market;
  final TradeType type;
  final double price;
  final int quantity;
  final double totalAmount;
  final double fee;
  final DateTime timestamp;
  final String memo;
  final TradeStatus status;

  Trade({
    String? id,
    required this.symbol,
    required this.name,
    required this.market,
    required this.type,
    required this.price,
    required this.quantity,
    double? totalAmount,
    this.fee = 0,
    DateTime? timestamp,
    this.memo = '',
    this.status = TradeStatus.open,
  })  : id = id ?? const Uuid().v4(),
        totalAmount = totalAmount ?? price * quantity,
        timestamp = timestamp ?? DateTime.now();

  double profitLoss(double currentPrice) {
    if (type == TradeType.buy) {
      return (currentPrice - price) * quantity - fee;
    }
    return (price - currentPrice) * quantity - fee;
  }

  double profitLossPercent(double currentPrice) {
    if (totalAmount == 0) return 0;
    return (profitLoss(currentPrice) / totalAmount) * 100;
  }

  Trade copyWith({
    String? id,
    String? symbol,
    String? name,
    Market? market,
    TradeType? type,
    double? price,
    int? quantity,
    double? totalAmount,
    double? fee,
    DateTime? timestamp,
    String? memo,
    TradeStatus? status,
  }) {
    return Trade(
      id: id ?? this.id,
      symbol: symbol ?? this.symbol,
      name: name ?? this.name,
      market: market ?? this.market,
      type: type ?? this.type,
      price: price ?? this.price,
      quantity: quantity ?? this.quantity,
      totalAmount: totalAmount ?? this.totalAmount,
      fee: fee ?? this.fee,
      timestamp: timestamp ?? this.timestamp,
      memo: memo ?? this.memo,
      status: status ?? this.status,
    );
  }

  factory Trade.fromJson(Map<String, dynamic> json) {
    return Trade(
      id: json['id'] as String,
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      market: Market.values.firstWhere(
        (e) => e.name == json['market'],
        orElse: () => Market.kr,
      ),
      type: TradeType.values.firstWhere(
        (e) => e.name == json['type'],
        orElse: () => TradeType.buy,
      ),
      price: (json['price'] as num).toDouble(),
      quantity: json['quantity'] as int,
      totalAmount: (json['totalAmount'] as num).toDouble(),
      fee: (json['fee'] as num?)?.toDouble() ?? 0,
      timestamp: DateTime.parse(json['timestamp'] as String),
      memo: json['memo'] as String? ?? '',
      status: TradeStatus.values.firstWhere(
        (e) => e.name == json['status'],
        orElse: () => TradeStatus.open,
      ),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'symbol': symbol,
      'name': name,
      'market': market.name,
      'type': type.name,
      'price': price,
      'quantity': quantity,
      'totalAmount': totalAmount,
      'fee': fee,
      'timestamp': timestamp.toIso8601String(),
      'memo': memo,
      'status': status.name,
    };
  }

  @override
  List<Object?> get props => [
        id,
        symbol,
        name,
        market,
        type,
        price,
        quantity,
        totalAmount,
        fee,
        timestamp,
        memo,
        status,
      ];
}
