enum Market {
  kr('한국', 'KRW'),
  us('미국', 'USD');

  const Market(this.label, this.currency);
  final String label;
  final String currency;
}

enum TradeType {
  buy('매수'),
  sell('매도');

  const TradeType(this.label);
  final String label;
}

enum TradeStatus {
  open('보유중'),
  closed('청산');

  const TradeStatus(this.label);
  final String label;
}

enum ChartInterval {
  min1('1분', Duration(minutes: 1)),
  min5('5분', Duration(minutes: 5)),
  min15('15분', Duration(minutes: 15)),
  min30('30분', Duration(minutes: 30)),
  hour1('1시간', Duration(hours: 1)),
  daily('일봉', Duration(days: 1));

  const ChartInterval(this.label, this.duration);
  final String label;
  final Duration duration;
}

enum OrderType {
  market('시장가'),
  limit('지정가');

  const OrderType(this.label);
  final String label;
}
