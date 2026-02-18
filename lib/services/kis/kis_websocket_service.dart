import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../core/constants/app_constants.dart';

class KisWebSocketService {
  KisWebSocketService({
    required this.appKey,
    required this.appSecret,
    String? wsUrl,
  }) : _wsUrl = wsUrl ?? AppConstants.kisWebSocket;

  final String appKey;
  final String appSecret;
  final String _wsUrl;

  WebSocketChannel? _channel;
  String? _approvalKey;

  final _priceController = StreamController<Map<String, dynamic>>.broadcast();
  final Set<String> _subscribedCodes = {};
  Timer? _reconnectTimer;
  bool _isDisposed = false;

  Stream<Map<String, dynamic>> get priceStream => _priceController.stream;

  Future<String> getApprovalKey() async {
    if (_approvalKey != null) return _approvalKey!;

    final dio = Dio(BaseOptions(
      baseUrl: AppConstants.kisApiBase,
      headers: {'content-type': 'application/json; charset=utf-8'},
    ));

    try {
      final response = await dio.post(
        '/oauth2/Approval',
        data: {
          'grant_type': 'client_credentials',
          'appkey': appKey,
          'secretkey': appSecret,
        },
      );

      _approvalKey = response.data['approval_key'] as String;
      return _approvalKey!;
    } on DioException catch (e) {
      throw Exception(
        'KIS 웹소켓 인증키 발급 실패: ${e.response?.statusCode} ${e.message}',
      );
    } finally {
      dio.close();
    }
  }

  Future<void> connect() async {
    if (_channel != null) return;

    await getApprovalKey();
    final uri = Uri.parse('$_wsUrl/tryitout');
    _channel = WebSocketChannel.connect(uri);

    _channel!.stream.listen(
      _onData,
      onError: _onError,
      onDone: _onDone,
    );
  }

  void _onData(dynamic data) {
    try {
      if (data is String) {
        if (data.startsWith('{')) {
          final json = jsonDecode(data) as Map<String, dynamic>;
          _priceController.add(json);
        } else {
          final parsed = _parseRealtimeData(data);
          if (parsed != null) {
            _priceController.add(parsed);
          }
        }
      }
    } catch (e) {
      // Ignore malformed messages
    }
  }

  Map<String, dynamic>? _parseRealtimeData(String raw) {
    final parts = raw.split('|');
    if (parts.length < 4) return null;

    final trId = parts[1];
    final body = parts[3];

    if (trId == 'H0STCNT0') {
      final fields = body.split('^');
      if (fields.length < 13) return null;

      return {
        'tr_id': trId,
        'stock_code': fields[0],
        'current_price': fields[2],
        'change_sign': fields[3],
        'change_amount': fields[4],
        'change_rate': fields[5],
        'volume': fields[9],
        'accumulated_volume': fields[12],
      };
    }

    return null;
  }

  void _onError(Object error) {
    if (!_isDisposed) {
      _scheduleReconnect();
    }
  }

  void _onDone() {
    _channel = null;
    if (!_isDisposed) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(AppConstants.wsReconnectDelay, () async {
      if (_isDisposed) return;

      try {
        await connect();
        for (final code in _subscribedCodes) {
          await _sendSubscription(code, '1');
        }
      } catch (_) {
        _scheduleReconnect();
      }
    });
  }

  Future<void> subscribe(String stockCode) async {
    if (_channel == null) {
      await connect();
    }

    _subscribedCodes.add(stockCode);
    await _sendSubscription(stockCode, '1');
  }

  Future<void> unsubscribe(String stockCode) async {
    _subscribedCodes.remove(stockCode);
    if (_channel != null) {
      await _sendSubscription(stockCode, '2');
    }
  }

  Future<void> _sendSubscription(String stockCode, String trType) async {
    final approvalKey = await getApprovalKey();

    final message = jsonEncode({
      'header': {
        'approval_key': approvalKey,
        'custtype': 'P',
        'tr_type': trType,
        'content-type': 'utf-8',
      },
      'body': {
        'input': {
          'tr_id': 'H0STCNT0',
          'tr_key': stockCode,
        },
      },
    });

    _channel?.sink.add(message);
  }

  void dispose() {
    _isDisposed = true;
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _priceController.close();
    _subscribedCodes.clear();
  }
}
