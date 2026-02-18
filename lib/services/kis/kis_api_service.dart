import 'package:dio/dio.dart';

import '../../core/constants/app_constants.dart';

class KisApiService {
  KisApiService({
    required this.appKey,
    required this.appSecret,
    required this.accountNo,
    String? baseUrl,
  }) : _dio = Dio(
         BaseOptions(
           baseUrl: baseUrl ?? AppConstants.kisApiBase,
           headers: {'content-type': 'application/json; charset=utf-8'},
         ),
       );

  final String appKey;
  final String appSecret;
  final String accountNo;
  final Dio _dio;

  String? _accessToken;
  DateTime? _tokenExpiry;

  Future<String> getAccessToken() async {
    if (_accessToken != null &&
        _tokenExpiry != null &&
        DateTime.now().isBefore(_tokenExpiry!)) {
      return _accessToken!;
    }

    try {
      final response = await _dio.post(
        '/oauth2/tokenP',
        data: {
          'grant_type': 'client_credentials',
          'appkey': appKey,
          'appsecret': appSecret,
        },
      );

      final data = response.data as Map<String, dynamic>;
      _accessToken = data['access_token'] as String;
      final expiresIn = data['access_token_token_expired'] as String;
      _tokenExpiry = DateTime.parse(expiresIn);

      return _accessToken!;
    } on DioException catch (e) {
      throw Exception('KIS 토큰 발급 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  Map<String, String> _buildHeaders(String trId) {
    return {
      'content-type': 'application/json; charset=utf-8',
      'authorization': 'Bearer $_accessToken',
      'appkey': appKey,
      'appsecret': appSecret,
      'tr_id': trId,
    };
  }

  Future<Map<String, dynamic>> getCurrentPrice(String stockCode) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/inquire-price',
        options: Options(headers: _buildHeaders('FHKST01010100')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_INPUT_ISCD': stockCode,
        },
      );

      final output = response.data['output'] as Map<String, dynamic>;

      return {
        'stck_prpr': output['stck_prpr'],
        'prdy_ctrt': output['prdy_ctrt'],
        'acml_vol': output['acml_vol'],
        'stck_oprc': output['stck_oprc'],
        'stck_hgpr': output['stck_hgpr'],
        'stck_lwpr': output['stck_lwpr'],
        'stck_sdpr': output['stck_sdpr'],
      };
    } on DioException catch (e) {
      throw Exception('KIS 현재가 조회 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  Future<List<Map<String, dynamic>>> getDailyCandles(
    String stockCode, {
    String period = 'D',
  }) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    final now = DateTime.now();
    final startDate = now.subtract(const Duration(days: 365));
    final dateFormat =
        '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}';
    final startDateFormat =
        '${startDate.year}${startDate.month.toString().padLeft(2, '0')}${startDate.day.toString().padLeft(2, '0')}';

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice',
        options: Options(headers: _buildHeaders('FHKST03010100')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_INPUT_ISCD': stockCode,
          'FID_INPUT_DATE_1': startDateFormat,
          'FID_INPUT_DATE_2': dateFormat,
          'FID_PERIOD_DIV_CODE': period,
          'FID_ORG_ADJ_PRC': '0',
        },
      );

      final output2 = response.data['output2'] as List<dynamic>;
      return output2.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception('KIS 일봉 조회 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  Future<List<Map<String, dynamic>>> getMinuteCandles(
    String stockCode, {
    String interval = '1',
  }) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    final now = DateTime.now();
    final timeFormat =
        '${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}00';

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice',
        options: Options(headers: _buildHeaders('FHKST03010200')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_INPUT_ISCD': stockCode,
          'FID_INPUT_HOUR_1': timeFormat,
          'FID_PW_DATA_INCU_YN': 'Y',
        },
      );

      final output2 = response.data['output2'] as List<dynamic>;
      return output2.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception('KIS 분봉 조회 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  Future<List<Map<String, dynamic>>> searchStock(String keyword) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/search-stock-info',
        options: Options(headers: _buildHeaders('CTPF1604R')),
        queryParameters: {'PRDT_TYPE_CD': '300', 'PDNO': keyword},
      );

      final output = response.data['output2'];
      if (output == null) return [];

      final results = output as List<dynamic>;
      return results.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception('KIS 종목 검색 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  /// 거래량 순위
  Future<List<Map<String, dynamic>>> getVolumeRanking() async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/volume-rank',
        options: Options(headers: _buildHeaders('FHPST01710000')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_COND_SCR_DIV_CODE': '20101',
          'FID_INPUT_ISCD': '0000',
          'FID_DIV_CLS_CODE': '0',
          'FID_BLNG_CLS_CODE': '0',
          'FID_TRGT_CLS_CODE': '111111111',
          'FID_TRGT_EXLS_CLS_CODE': '000000',
          'FID_INPUT_PRICE_1': '0',
          'FID_INPUT_PRICE_2': '0',
          'FID_VOL_CNT': '0',
          'FID_INPUT_DATE_1': '',
        },
      );

      final output = response.data['output'] as List<dynamic>?;
      if (output == null) return [];
      return output.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception(
        'KIS 거래량 순위 조회 실패: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  /// 등락률 순위
  Future<List<Map<String, dynamic>>> getFluctuationRanking({
    bool isUp = true,
  }) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/ranking/fluctuation',
        options: Options(headers: _buildHeaders('FHPST01700000')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_COND_SCR_DIV_CODE': isUp ? '20170' : '20175',
          'FID_INPUT_ISCD': '0000',
          'FID_DIV_CLS_CODE': '0',
          'FID_BLNG_CLS_CODE': '0',
          'FID_TRGT_CLS_CODE': '111111111',
          'FID_TRGT_EXLS_CLS_CODE': '000000',
          'FID_INPUT_PRICE_1': '0',
          'FID_INPUT_PRICE_2': '0',
          'FID_VOL_CNT': '0',
          'FID_INPUT_DATE_1': '',
        },
      );

      final output = response.data['output'] as List<dynamic>?;
      if (output == null) return [];
      return output.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception(
        'KIS 등락률 순위 조회 실패: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  /// 외국인/기관 순매수
  Future<List<Map<String, dynamic>>> getForeignInstitutionTotal(
    String stockCode,
  ) async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/foreign-institution-total',
        options: Options(headers: _buildHeaders('FHPTJ04400000')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'J',
          'FID_INPUT_ISCD': stockCode,
        },
      );

      final output = response.data['output'] as List<dynamic>?;
      if (output == null) return [];
      return output.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception(
        'KIS 외국인/기관 순매수 조회 실패: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  /// KOSPI 종합지수 조회
  Future<Map<String, dynamic>> getKospiIndex() async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/inquire-index-price',
        options: Options(headers: _buildHeaders('FHPUP02100000')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'U',
          'FID_INPUT_ISCD': '0001',
        },
      );

      final output = response.data['output'] as Map<String, dynamic>?;
      if (output == null) return {};

      return {
        'index_price': output['bstp_nmix_prpr'] ?? '',
        'change_rate': output['bstp_nmix_prdy_ctrt'] ?? '',
        'change_value': output['bstp_nmix_prdy_vrss'] ?? '',
        'volume': output['acml_vol'] ?? '',
        'trading_value': output['acml_tr_pbmn'] ?? '',
      };
    } on DioException catch (_) {
      return {};
    }
  }

  /// KOSDAQ 종합지수 조회
  Future<Map<String, dynamic>> getKosdaqIndex() async {
    final accessToken = await getAccessToken();
    _accessToken = accessToken;

    try {
      final response = await _dio.get(
        '/uapi/domestic-stock/v1/quotations/inquire-index-price',
        options: Options(headers: _buildHeaders('FHPUP02100000')),
        queryParameters: {
          'FID_COND_MRKT_DIV_CODE': 'U',
          'FID_INPUT_ISCD': '2001',
        },
      );

      final output = response.data['output'] as Map<String, dynamic>?;
      if (output == null) return {};

      return {
        'index_price': output['bstp_nmix_prpr'] ?? '',
        'change_rate': output['bstp_nmix_prdy_ctrt'] ?? '',
        'change_value': output['bstp_nmix_prdy_vrss'] ?? '',
        'volume': output['acml_vol'] ?? '',
        'trading_value': output['acml_tr_pbmn'] ?? '',
      };
    } on DioException catch (_) {
      return {};
    }
  }

  /// 환율 조회 (USD/KRW) — 실패 시 빈 맵 반환
  Future<Map<String, dynamic>> getExchangeRate() async {
    try {
      final dio = Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5),
        ),
      );
      final response = await dio.get(
        'https://m.stock.naver.com/front-api/marketIndex/productDetail',
        queryParameters: {'category': 'exchange', 'reutersCode': 'FX_USDKRW'},
      );

      final data = response.data;
      if (data is Map<String, dynamic>) {
        final result = data['result'] as Map<String, dynamic>?;
        if (result != null) {
          return {
            'exchange_rate': result['closePrice'] ?? '',
            'change_rate': result['compareToPreviousClosePrice'] ?? '',
          };
        }
      }
      return {};
    } catch (_) {
      return {};
    }
  }

  void dispose() {
    _dio.close();
  }
}
