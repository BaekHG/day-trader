import 'package:dio/dio.dart';

/// Naver Finance API — 장 마감 후에도 최신 데이터 제공.
/// KIS 랭킹 API가 장 종료 후 빈 데이터를 반환할 때 fallback으로 사용.
class NaverFinanceService {
  NaverFinanceService()
    : _dio = Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 8),
          receiveTimeout: const Duration(seconds: 8),
        ),
      );

  final Dio _dio;

  static const _baseUrl = 'https://m.stock.naver.com/api/stocks';

  /// 거래량 상위 종목 (KOSPI+KOSDAQ 상승/하락 합쳐서 거래량순 정렬).
  /// KIS 필드명으로 매핑하여 반환 → UI/AI 코드 변경 불필요.
  Future<List<Map<String, dynamic>>> getVolumeRanking({int count = 10}) async {
    final allStocks = <Map<String, dynamic>>[];

    // KOSPI + KOSDAQ, 상승 + 하락 종목 30개씩 가져오기
    final futures = <Future<Response>>[];
    for (final market in ['KOSPI', 'KOSDAQ']) {
      for (final direction in ['up', 'down']) {
        futures.add(
          _dio.get(
            '$_baseUrl/$direction/$market',
            queryParameters: {'page': 1, 'pageSize': 30},
          ),
        );
      }
    }

    final responses = await Future.wait(futures, eagerError: false);
    for (final resp in responses) {
      final data = resp.data;
      if (data is Map<String, dynamic>) {
        final stocks = data['stocks'] as List<dynamic>?;
        if (stocks != null) {
          allStocks.addAll(stocks.cast<Map<String, dynamic>>());
        }
      }
    }

    if (allStocks.isEmpty) return [];

    // 중복 제거 (같은 종목코드)
    final seen = <String>{};
    final unique = <Map<String, dynamic>>[];
    for (final s in allStocks) {
      final code = s['itemCode'] as String? ?? '';
      if (code.isNotEmpty && seen.add(code)) {
        unique.add(s);
      }
    }

    // 거래량순 정렬
    unique.sort((a, b) {
      final volA = _parseVolume(a['accumulatedTradingVolume']);
      final volB = _parseVolume(b['accumulatedTradingVolume']);
      return volB.compareTo(volA);
    });

    // KIS 필드명으로 매핑
    return unique.take(count).map(_toKisFormat).toList();
  }

  /// 상승률 상위 종목 (KOSPI + KOSDAQ).
  Future<List<Map<String, dynamic>>> getUpRanking({int count = 15}) async {
    return _getRanking('up', count: count);
  }

  /// 하락률 상위 종목 (KOSPI + KOSDAQ).
  Future<List<Map<String, dynamic>>> getDownRanking({int count = 15}) async {
    return _getRanking('down', count: count);
  }

  Future<List<Map<String, dynamic>>> _getRanking(
    String direction, {
    int count = 15,
  }) async {
    final allStocks = <Map<String, dynamic>>[];

    final responses = await Future.wait([
      _dio.get(
        '$_baseUrl/$direction/KOSPI',
        queryParameters: {'page': 1, 'pageSize': count},
      ),
      _dio.get(
        '$_baseUrl/$direction/KOSDAQ',
        queryParameters: {'page': 1, 'pageSize': count},
      ),
    ]);

    for (final resp in responses) {
      final data = resp.data;
      if (data is Map<String, dynamic>) {
        final stocks = data['stocks'] as List<dynamic>?;
        if (stocks != null) {
          allStocks.addAll(stocks.cast<Map<String, dynamic>>());
        }
      }
    }

    // 등락률 절대값 기준 정렬
    allStocks.sort((a, b) {
      final rateA =
          double.tryParse('${a['fluctuationsRatio'] ?? '0'}')?.abs() ?? 0;
      final rateB =
          double.tryParse('${b['fluctuationsRatio'] ?? '0'}')?.abs() ?? 0;
      return rateB.compareTo(rateA);
    });

    return allStocks.take(count).map(_toKisFormat).toList();
  }

  /// Naver 응답 → KIS 필드명으로 매핑.
  Map<String, dynamic> _toKisFormat(Map<String, dynamic> naver) {
    final price = _removeComma(naver['closePrice']);
    return {
      'hts_kor_isnm': naver['stockName'] ?? '',
      'mksc_shrn_iscd': naver['itemCode'] ?? '',
      'stck_prpr': price,
      'prdy_ctrt': '${naver['fluctuationsRatio'] ?? '0'}',
      'acml_vol': _removeComma(naver['accumulatedTradingVolume']),
      'acml_tr_pbmn': _removeComma(naver['accumulatedTradingValue']),
      'stck_hgpr': price, // 고가 데이터 없음 → 종가로 대체
      'stck_sdpr': price, // 기준가도 종가로 대체
      // 원본 Naver 데이터 보존 (필요시)
      '_naver_market_status': naver['marketStatus'] ?? '',
      '_naver_trading_value_label':
          naver['accumulatedTradingValueKrwHangeul'] ?? '',
    };
  }

  int _parseVolume(dynamic vol) {
    if (vol == null) return 0;
    return int.tryParse('$vol'.replaceAll(',', '')) ?? 0;
  }

  String _removeComma(dynamic val) {
    if (val == null) return '0';
    return '$val'.replaceAll(',', '');
  }

  void dispose() {
    _dio.close();
  }
}
