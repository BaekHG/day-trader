import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../../core/constants/app_constants.dart';

class AlpacaWebSocketService {
  AlpacaWebSocketService({
    required this.apiKeyId,
    required this.apiSecretKey,
    String? wsUrl,
  }) : _wsUrl = wsUrl ?? AppConstants.alpacaStream;

  final String apiKeyId;
  final String apiSecretKey;
  final String _wsUrl;

  WebSocketChannel? _channel;

  final _tradeController = StreamController<Map<String, dynamic>>.broadcast();
  final _quoteController = StreamController<Map<String, dynamic>>.broadcast();
  final _barController = StreamController<Map<String, dynamic>>.broadcast();

  final Set<String> _subscribedSymbols = {};
  Timer? _reconnectTimer;
  bool _isDisposed = false;
  bool _isAuthenticated = false;

  Stream<Map<String, dynamic>> get tradeStream => _tradeController.stream;
  Stream<Map<String, dynamic>> get quoteStream => _quoteController.stream;
  Stream<Map<String, dynamic>> get barStream => _barController.stream;

  Future<void> connect() async {
    if (_channel != null) return;

    final uri = Uri.parse(_wsUrl);
    _channel = WebSocketChannel.connect(uri);
    _isAuthenticated = false;

    _channel!.stream.listen(
      _onData,
      onError: _onError,
      onDone: _onDone,
    );

    _authenticate();
  }

  void _authenticate() {
    final authMessage = jsonEncode({
      'action': 'auth',
      'key': apiKeyId,
      'secret': apiSecretKey,
    });

    _channel?.sink.add(authMessage);
  }

  void _onData(dynamic data) {
    try {
      final messages = jsonDecode(data as String) as List<dynamic>;

      for (final msg in messages) {
        final message = msg as Map<String, dynamic>;
        final type = message['T'] as String?;

        switch (type) {
          case 'success':
            if (message['msg'] == 'authenticated') {
              _isAuthenticated = true;
              if (_subscribedSymbols.isNotEmpty) {
                _sendSubscription(
                  'subscribe',
                  _subscribedSymbols.toList(),
                );
              }
            }
          case 't':
            _tradeController.add(message);
          case 'q':
            _quoteController.add(message);
          case 'b':
            _barController.add(message);
        }
      }
    } catch (e) {
      // Ignore malformed messages
    }
  }

  void _onError(Object error) {
    _isAuthenticated = false;
    if (!_isDisposed) {
      _scheduleReconnect();
    }
  }

  void _onDone() {
    _channel = null;
    _isAuthenticated = false;
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
      } catch (_) {
        _scheduleReconnect();
      }
    });
  }

  Future<void> subscribe(List<String> symbols) async {
    if (_channel == null) {
      await connect();
    }

    _subscribedSymbols.addAll(symbols);

    if (_isAuthenticated) {
      _sendSubscription('subscribe', symbols);
    }
  }

  Future<void> unsubscribe(List<String> symbols) async {
    _subscribedSymbols.removeAll(symbols);

    if (_channel != null && _isAuthenticated) {
      _sendSubscription('unsubscribe', symbols);
    }
  }

  void _sendSubscription(String action, List<String> symbols) {
    final message = jsonEncode({
      'action': action,
      'trades': symbols,
      'quotes': symbols,
      'bars': symbols,
    });

    _channel?.sink.add(message);
  }

  void dispose() {
    _isDisposed = true;
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _tradeController.close();
    _quoteController.close();
    _barController.close();
    _subscribedSymbols.clear();
  }
}
