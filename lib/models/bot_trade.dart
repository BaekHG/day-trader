import 'package:equatable/equatable.dart';

class BotTrade extends Equatable {
  final int? id;
  final String stockCode;
  final String stockName;
  final String action; // 'buy' or 'sell'
  final int quantity;
  final int price;
  final int amount;
  final String reason;
  final int pnlAmount;
  final double pnlPct;
  final DateTime tradedAt;

  const BotTrade({
    this.id,
    required this.stockCode,
    required this.stockName,
    required this.action,
    required this.quantity,
    required this.price,
    required this.amount,
    required this.reason,
    required this.pnlAmount,
    required this.pnlPct,
    required this.tradedAt,
  });

  bool get isBuy => action == 'buy';
  bool get isSell => action == 'sell';

  BotTrade copyWith({
    int? id,
    String? stockCode,
    String? stockName,
    String? action,
    int? quantity,
    int? price,
    int? amount,
    String? reason,
    int? pnlAmount,
    double? pnlPct,
    DateTime? tradedAt,
  }) {
    return BotTrade(
      id: id ?? this.id,
      stockCode: stockCode ?? this.stockCode,
      stockName: stockName ?? this.stockName,
      action: action ?? this.action,
      quantity: quantity ?? this.quantity,
      price: price ?? this.price,
      amount: amount ?? this.amount,
      reason: reason ?? this.reason,
      pnlAmount: pnlAmount ?? this.pnlAmount,
      pnlPct: pnlPct ?? this.pnlPct,
      tradedAt: tradedAt ?? this.tradedAt,
    );
  }

  factory BotTrade.fromJson(Map<String, dynamic> json) {
    return BotTrade(
      id: json['id'] as int?,
      stockCode: json['stock_code'] as String? ?? '',
      stockName: json['stock_name'] as String? ?? '',
      action: json['action'] as String? ?? 'buy',
      quantity: (json['quantity'] as num?)?.toInt() ?? 0,
      price: (json['price'] as num?)?.toInt() ?? 0,
      amount: (json['amount'] as num?)?.toInt() ?? 0,
      reason: json['reason'] as String? ?? '',
      pnlAmount: (json['pnl_amount'] as num?)?.toInt() ?? 0,
      pnlPct: (json['pnl_pct'] as num?)?.toDouble() ?? 0.0,
      tradedAt: json['traded_at'] != null
          ? DateTime.parse(json['traded_at'] as String).toLocal()
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'stock_code': stockCode,
      'stock_name': stockName,
      'action': action,
      'quantity': quantity,
      'price': price,
      'amount': amount,
      'reason': reason,
      'pnl_amount': pnlAmount,
      'pnl_pct': pnlPct,
      'traded_at': tradedAt.toIso8601String(),
    };
  }

  @override
  List<Object?> get props => [
    id,
    stockCode,
    stockName,
    action,
    quantity,
    price,
    amount,
    reason,
    pnlAmount,
    pnlPct,
    tradedAt,
  ];
}
