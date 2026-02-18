import 'package:intl/intl.dart';

abstract final class Formatters {
  static final _krwFormat = NumberFormat('#,###', 'ko_KR');
  static final _usdFormat = NumberFormat('#,##0.00', 'en_US');
  static final _percentFormat = NumberFormat('0.00', 'ko_KR');
  static final _dateFormat = DateFormat('yyyy.MM.dd');
  static final _timeFormat = DateFormat('HH:mm:ss');
  static final _dateTimeFormat = DateFormat('yyyy.MM.dd HH:mm');
  static final _shortDateFormat = DateFormat('MM/dd');
  static final _monthDayTimeFormat = DateFormat('MM.dd HH:mm');

  static String formatKRW(int price) {
    return '₩${_krwFormat.format(price)}';
  }

  static String formatUSD(double price) {
    return '\$${_usdFormat.format(price)}';
  }

  static String formatPercent(double pct) {
    final sign = pct >= 0 ? '+' : '';
    return '$sign${_percentFormat.format(pct)}%';
  }

  static String formatVolume(int vol) {
    if (vol >= 1000000000) {
      return '${(vol / 1000000000).toStringAsFixed(1)}B';
    } else if (vol >= 1000000) {
      return '${(vol / 1000000).toStringAsFixed(1)}M';
    } else if (vol >= 1000) {
      return '${(vol / 1000).toStringAsFixed(1)}K';
    }
    return _krwFormat.format(vol);
  }

  static String formatDate(DateTime dt) => _dateFormat.format(dt);

  static String formatTime(DateTime dt) => _timeFormat.format(dt);

  static String formatDateTime(DateTime dt) => _dateTimeFormat.format(dt);

  static String formatShortDate(DateTime dt) => _shortDateFormat.format(dt);

  static String formatMonthDayTime(DateTime dt) =>
      _monthDayTimeFormat.format(dt);

  static String formatPriceByMarket(double price, String market) {
    if (market == 'kr') {
      return formatKRW(price.toInt());
    }
    return formatUSD(price);
  }
}
