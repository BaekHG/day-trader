import 'package:equatable/equatable.dart';

class BotTrade extends Equatable {
  final int? id;
  final String stockCode;
  final String stockName;
  final String action;
  final int quantity;
  final int price;
  final int amount;
  final String reason;
  final int pnlAmount;
  final double pnlPct;
  final DateTime tradedAt;
  final String exitType;
  final double holdMinutes;
  final double highWaterMarkPct;

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
    this.exitType = '',
    this.holdMinutes = 0.0,
    this.highWaterMarkPct = 0.0,
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
    String? exitType,
    double? holdMinutes,
    double? highWaterMarkPct,
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
      exitType: exitType ?? this.exitType,
      holdMinutes: holdMinutes ?? this.holdMinutes,
      highWaterMarkPct: highWaterMarkPct ?? this.highWaterMarkPct,
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
      exitType: json['exit_type'] as String? ?? '',
      holdMinutes: (json['hold_minutes'] as num?)?.toDouble() ?? 0.0,
      highWaterMarkPct:
          (json['high_water_mark_pct'] as num?)?.toDouble() ?? 0.0,
    );
  }

  String get exitTypeLabel {
    return switch (exitType) {
      'trailing' => '트레일링',
      'stop_loss' => '손절',
      'time_exit' => '시간청산',
      'force_close' => '강제청산',
      'manual' => '수동',
      _ => exitType.isEmpty ? _inferExitType() : exitType,
    };
  }

  String _inferExitType() {
    if (reason.contains('트레일링')) return '트레일링';
    if (reason.contains('손절')) return '손절';
    if (reason.contains('횡보')) return '시간청산';
    if (reason.contains('강제')) return '강제청산';
    return '기타';
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
      'exit_type': exitType,
      'hold_minutes': holdMinutes,
      'high_water_mark_pct': highWaterMarkPct,
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
    exitType,
    holdMinutes,
    highWaterMarkPct,
  ];
}
