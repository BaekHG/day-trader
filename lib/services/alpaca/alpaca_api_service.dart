import 'package:dio/dio.dart';

import '../../core/constants/app_constants.dart';

class AlpacaApiService {
  AlpacaApiService({
    required this.apiKeyId,
    required this.apiSecretKey,
    String? dataBaseUrl,
    String? tradingBaseUrl,
  })  : _dataDio = Dio(BaseOptions(
          baseUrl: dataBaseUrl ?? AppConstants.alpacaDataBase,
          headers: {
            'APCA-API-KEY-ID': apiKeyId,
            'APCA-API-SECRET-KEY': apiSecretKey,
          },
        )),
        _tradingDio = Dio(BaseOptions(
          baseUrl: tradingBaseUrl ?? AppConstants.alpacaTradingBase,
          headers: {
            'APCA-API-KEY-ID': apiKeyId,
            'APCA-API-SECRET-KEY': apiSecretKey,
          },
        ));

  final String apiKeyId;
  final String apiSecretKey;
  final Dio _dataDio;
  final Dio _tradingDio;

  Future<Map<String, dynamic>> getLatestQuote(String symbol) async {
    try {
      final response = await _dataDio.get(
        '/v2/stocks/$symbol/quotes/latest',
      );

      return response.data['quote'] as Map<String, dynamic>;
    } on DioException catch (e) {
      throw Exception(
        'Alpaca latest quote failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  Future<Map<String, dynamic>> getLatestTrade(String symbol) async {
    try {
      final response = await _dataDio.get(
        '/v2/stocks/$symbol/trades/latest',
      );

      return response.data['trade'] as Map<String, dynamic>;
    } on DioException catch (e) {
      throw Exception(
        'Alpaca latest trade failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  Future<List<Map<String, dynamic>>> getBars(
    String symbol, {
    String timeframe = '1Min',
    int limit = 100,
    String? start,
    String? end,
  }) async {
    try {
      final queryParameters = <String, dynamic>{
        'timeframe': timeframe,
        'limit': limit,
      };
      if (start != null) queryParameters['start'] = start;
      if (end != null) queryParameters['end'] = end;

      final response = await _dataDio.get(
        '/v2/stocks/$symbol/bars',
        queryParameters: queryParameters,
      );

      final bars = response.data['bars'] as List<dynamic>?;
      if (bars == null) return [];

      return bars.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } on DioException catch (e) {
      throw Exception(
        'Alpaca bars failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  Future<Map<String, List<Map<String, dynamic>>>> getMultiBars(
    List<String> symbols, {
    String timeframe = '1Day',
    int limit = 50,
  }) async {
    try {
      final response = await _dataDio.get(
        '/v2/stocks/bars',
        queryParameters: {
          'symbols': symbols.join(','),
          'timeframe': timeframe,
          'limit': limit,
        },
      );

      final barsMap = response.data['bars'] as Map<String, dynamic>?;
      if (barsMap == null) return {};

      return barsMap.map((key, value) {
        final list = (value as List<dynamic>)
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
        return MapEntry(key, list);
      });
    } on DioException catch (e) {
      throw Exception(
        'Alpaca multi bars failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  Future<Map<String, dynamic>> getSnapshot(String symbol) async {
    try {
      final response = await _dataDio.get(
        '/v2/stocks/$symbol/snapshot',
      );

      return response.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw Exception(
        'Alpaca snapshot failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  Future<List<Map<String, dynamic>>> searchAssets(String query) async {
    try {
      final response = await _tradingDio.get(
        '/v2/assets',
        queryParameters: {
          'status': 'active',
          'asset_class': 'us_equity',
        },
      );

      final assets = (response.data as List<dynamic>)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .where((asset) {
            final symbol = (asset['symbol'] as String?)?.toLowerCase() ?? '';
            final name = (asset['name'] as String?)?.toLowerCase() ?? '';
            final lowerQuery = query.toLowerCase();
            return symbol.contains(lowerQuery) || name.contains(lowerQuery);
          })
          .take(20)
          .toList();

      return assets;
    } on DioException catch (e) {
      throw Exception(
        'Alpaca asset search failed: ${e.response?.statusCode} ${e.message}',
      );
    }
  }

  void dispose() {
    _dataDio.close();
    _tradingDio.close();
  }
}
