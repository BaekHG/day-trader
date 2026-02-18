import 'package:equatable/equatable.dart';

class Candle extends Equatable {
  final DateTime dateTime;
  final double open;
  final double high;
  final double low;
  final double close;
  final int volume;

  const Candle({
    required this.dateTime,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
  });

  bool get isBullish => close >= open;

  double get bodySize => (close - open).abs();

  double get range => high - low;

  Candle copyWith({
    DateTime? dateTime,
    double? open,
    double? high,
    double? low,
    double? close,
    int? volume,
  }) {
    return Candle(
      dateTime: dateTime ?? this.dateTime,
      open: open ?? this.open,
      high: high ?? this.high,
      low: low ?? this.low,
      close: close ?? this.close,
      volume: volume ?? this.volume,
    );
  }

  factory Candle.fromJson(Map<String, dynamic> json) {
    return Candle(
      dateTime: DateTime.parse(json['dateTime'] as String),
      open: (json['open'] as num).toDouble(),
      high: (json['high'] as num).toDouble(),
      low: (json['low'] as num).toDouble(),
      close: (json['close'] as num).toDouble(),
      volume: json['volume'] as int,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'dateTime': dateTime.toIso8601String(),
      'open': open,
      'high': high,
      'low': low,
      'close': close,
      'volume': volume,
    };
  }

  factory Candle.fromKisJson(Map<String, dynamic> json) {
    final date = json['stck_bsop_date'] as String;
    final time = json['stck_cntg_hour'] as String? ?? '000000';
    return Candle(
      dateTime: DateTime.parse(
        '${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}'
        'T${time.substring(0, 2)}:${time.substring(2, 4)}:${time.substring(4, 6)}',
      ),
      open: double.parse(json['stck_oprc'] as String),
      high: double.parse(json['stck_hgpr'] as String),
      low: double.parse(json['stck_lwpr'] as String),
      close: double.parse(json['stck_clpr'] as String),
      volume: int.parse(json['acml_vol'] as String),
    );
  }

  factory Candle.fromAlpacaJson(Map<String, dynamic> json) {
    return Candle(
      dateTime: DateTime.parse(json['t'] as String),
      open: (json['o'] as num).toDouble(),
      high: (json['h'] as num).toDouble(),
      low: (json['l'] as num).toDouble(),
      close: (json['c'] as num).toDouble(),
      volume: json['v'] as int,
    );
  }

  @override
  List<Object?> get props => [dateTime, open, high, low, close, volume];
}
