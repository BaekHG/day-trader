import 'dart:convert';

import 'package:equatable/equatable.dart';

class DailyReport extends Equatable {
  final int? id;
  final String reportDate;
  final int totalTrades;
  final int totalPnl;
  final double totalPnlPct;
  final int winCount;
  final int lossCount;
  final List<dynamic> trades;
  final List<dynamic> remainingPositions;

  const DailyReport({
    this.id,
    required this.reportDate,
    required this.totalTrades,
    required this.totalPnl,
    required this.totalPnlPct,
    required this.winCount,
    required this.lossCount,
    required this.trades,
    required this.remainingPositions,
  });

  bool get isProfit => totalPnl >= 0;
  double get winRate => totalTrades > 0 ? (winCount / totalTrades) * 100 : 0.0;

  DailyReport copyWith({
    int? id,
    String? reportDate,
    int? totalTrades,
    int? totalPnl,
    double? totalPnlPct,
    int? winCount,
    int? lossCount,
    List<dynamic>? trades,
    List<dynamic>? remainingPositions,
  }) {
    return DailyReport(
      id: id ?? this.id,
      reportDate: reportDate ?? this.reportDate,
      totalTrades: totalTrades ?? this.totalTrades,
      totalPnl: totalPnl ?? this.totalPnl,
      totalPnlPct: totalPnlPct ?? this.totalPnlPct,
      winCount: winCount ?? this.winCount,
      lossCount: lossCount ?? this.lossCount,
      trades: trades ?? this.trades,
      remainingPositions: remainingPositions ?? this.remainingPositions,
    );
  }

  static List<dynamic> _parseList(dynamic value) {
    if (value == null) return [];
    if (value is List) return value;
    if (value is String) {
      try {
        final decoded = json.decode(value);
        if (decoded is List) return decoded;
      } catch (_) {}
    }
    return [];
  }

  factory DailyReport.fromJson(Map<String, dynamic> json) {
    return DailyReport(
      id: json['id'] as int?,
      reportDate: json['report_date'] as String? ?? '',
      totalTrades: (json['total_trades'] as num?)?.toInt() ?? 0,
      totalPnl: (json['total_pnl'] as num?)?.toInt() ?? 0,
      totalPnlPct: (json['total_pnl_pct'] as num?)?.toDouble() ?? 0.0,
      winCount: (json['win_count'] as num?)?.toInt() ?? 0,
      lossCount: (json['loss_count'] as num?)?.toInt() ?? 0,
      trades: _parseList(json['trades']),
      remainingPositions: _parseList(json['remaining_positions']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'report_date': reportDate,
      'total_trades': totalTrades,
      'total_pnl': totalPnl,
      'total_pnl_pct': totalPnlPct,
      'win_count': winCount,
      'loss_count': lossCount,
      'trades': json.encode(trades),
      'remaining_positions': json.encode(remainingPositions),
    };
  }

  @override
  List<Object?> get props => [
    id,
    reportDate,
    totalTrades,
    totalPnl,
    totalPnlPct,
    winCount,
    lossCount,
    trades,
    remainingPositions,
  ];
}
