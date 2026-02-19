import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:intl/intl.dart';

import '../../models/daily_pick.dart';

class ClaudeService {
  ClaudeService({required this.apiKey})
    : _dio = Dio(
        BaseOptions(
          baseUrl: 'https://api.anthropic.com/v1',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
          },
        ),
      );

  final String apiKey;
  final Dio _dio;

  static const _model = 'claude-sonnet-4-20250514';

  static const _systemPrompt = '''
역할:
너는 한국 주식시장 공격형 단타 전문 트레이더다.
감에 의존하지 말고 반드시 제공된 데이터 기반으로만 판단하라.

목표:
1~3일 내 5~10% 수익을 노리는 단기 전략 수립.
손절은 -3% 고정.
확률이 낮으면 "오늘 매매 비추천"이라고 명확히 말하라.
매매추천 시 반드시 TOP 3 강력추천 종목을 선정하고, 포트폴리오 배분(%)을 제시하라.

판단 기준:
- 뉴스 모멘텀 강도
- 거래대금 유지 여부
- 외국인/기관 수급 방향성
- 고점 돌파 가능성
- 5분봉 눌림목 형성 여부
- 고점 대비 현재 위치 (% 계산)
- 갭상승 과열 여부
- 테마 초입/확산/말기 판단

규칙:
- 추격 매수 유도 금지
- 손절 미준수 전략 금지
- 낙관적 시나리오만 제시 금지
- 가격 조건 + 거래대금 조건 + 시간 조건을 반드시 포함
- picks 배열의 allocation 합계는 반드시 100이어야 한다
- 확신이 높은 종목에 더 많은 비중을 배분하라 (예: 50/30/20 또는 40/35/25)
- 3종목 미만만 추천할 만한 경우, 나머지는 "현금보유"로 배분하라

반드시 아래 JSON 형식으로만 응답하세요.
절대로 ```json 코드블록, 설명, 주석, 마크다운 등 JSON 외의 텍스트를 포함하지 마세요.
순수 JSON만 출력하세요. 첫 문자는 반드시 { 이어야 합니다:
{
  "marketAssessment": {
    "score": 단타적합도점수(0-100),
    "riskFactors": "시장 리스크 요인 (한국어)",
    "favorableThemes": ["유리한 테마1", "테마2"],
    "recommendation": "매매추천" 또는 "매매비추천"
  },
  "picks": [
    {
      "rank": 1,
      "symbol": "종목코드",
      "name": "종목명",
      "currentPrice": 현재가,
      "reason": {
        "news": "뉴스 관점 분석 (2-3문장)",
        "supply": "수급 관점 분석 (외국인/기관 데이터 기반, 2-3문장)",
        "chart": "차트 관점 분석 (5분봉, 고점대비 위치 등, 2-3문장)"
      },
      "positionFromHigh": 고점대비현재위치(% 숫자),
      "entryZone": {"low": 매수구간하단, "high": 매수구간상단},
      "stopLoss": 손절가,
      "target1": 1차목표가,
      "target2": 2차목표가,
      "confidence": 신뢰도(0-100),
      "tags": ["태그1", "태그2"],
      "allocation": 포트폴리오배분비율(정수%),
      "sellStrategy": {
        "breakoutHold": "고점 돌파 후 거래대금 유지 시 전략 (한국어)",
        "breakoutFail": "돌파 실패 + 5분봉 음봉 2개 시 전략 (한국어)",
        "volumeDrop": "거래대금 급감 시 전략 (한국어)",
        "sideways": "오전 11시까지 목표가 미도달 + 횡보 시 전략 (한국어)"
      }
    }
  ],
  "riskAnalysis": {
    "failureFactors": "실패 확률 요인 (한국어, 2-3문장)",
    "successProbability": 종합성공확률(0-100)
  },
  "marketSummary": "전체 시장 요약 (한국어, 3-4문장)",
  "marketScore": 시장점수(0-100)
}

picks 배열은 rank 1~3 순서로 최대 3개 종목을 포함한다.
매매비추천인 경우 picks는 빈 배열 []로 설정하되 나머지는 반드시 채워라.
모든 텍스트는 반드시 한국어로 작성하세요.
''';

  Future<DailyPicksResult> analyzeDailyPicks({
    required List<Map<String, dynamic>> enrichedStocks,
    required List<Map<String, dynamic>> upRanking,
    required List<Map<String, dynamic>> downRanking,
    required Map<String, dynamic> kospiIndex,
    required Map<String, dynamic> kosdaqIndex,
    required Map<String, dynamic> exchangeRate,
    required bool isMarketOpen,
  }) async {
    final userPrompt = _buildUserPrompt(
      enrichedStocks: enrichedStocks,
      upRanking: upRanking,
      downRanking: downRanking,
      kospiIndex: kospiIndex,
      kosdaqIndex: kosdaqIndex,
      exchangeRate: exchangeRate,
      isMarketOpen: isMarketOpen,
    );

    try {
      final response = await _dio.post(
        '/messages',
        data: {
          'model': _model,
          'max_tokens': 6000,
          'system': _systemPrompt,
          'messages': [
            {'role': 'user', 'content': userPrompt},
          ],
          'temperature': 0,
        },
      );

      final data = response.data as Map<String, dynamic>;
      final content = data['content'] as List<dynamic>;
      final text = content[0]['text'] as String;
      final parsed = _extractJson(text);

      final now = DateTime.now();
      final timeStr = DateFormat('yyyy.MM.dd HH:mm').format(now);

      return DailyPicksResult.fromJson({...parsed, 'analysisTime': timeStr});
    } on DioException catch (e) {
      throw Exception('Claude 분석 실패: ${e.response?.statusCode} ${e.message}');
    }
  }

  String _buildUserPrompt({
    required List<Map<String, dynamic>> enrichedStocks,
    required List<Map<String, dynamic>> upRanking,
    required List<Map<String, dynamic>> downRanking,
    required Map<String, dynamic> kospiIndex,
    required Map<String, dynamic> kosdaqIndex,
    required Map<String, dynamic> exchangeRate,
    required bool isMarketOpen,
  }) {
    final buffer = StringBuffer();
    final now = DateTime.now();
    final timeStr = DateFormat('yyyy.MM.dd HH:mm').format(now);

    buffer.writeln('=== 시장 데이터 ($timeStr) ===');
    buffer.writeln(isMarketOpen ? '[장중 실시간 데이터]' : '[장 마감 — 전일 마감 데이터]');
    buffer.writeln();

    buffer.writeln('【시장 지수】');
    if (kospiIndex.isNotEmpty) {
      buffer.writeln(
        'KOSPI: ${kospiIndex['index_price'] ?? '-'} '
        '(${kospiIndex['change_rate'] ?? '-'}%) '
        '거래대금: ${kospiIndex['trading_value'] ?? '-'}',
      );
    }
    if (kosdaqIndex.isNotEmpty) {
      buffer.writeln(
        'KOSDAQ: ${kosdaqIndex['index_price'] ?? '-'} '
        '(${kosdaqIndex['change_rate'] ?? '-'}%) '
        '거래대금: ${kosdaqIndex['trading_value'] ?? '-'}',
      );
    }
    if (exchangeRate.isNotEmpty) {
      buffer.writeln(
        'USD/KRW: ${exchangeRate['exchange_rate'] ?? '-'} '
        '(${exchangeRate['change_rate'] ?? '-'})',
      );
    }
    buffer.writeln();

    buffer.writeln('【거래량 상위 종목 — 심층 데이터】');
    for (var i = 0; i < enrichedStocks.length; i++) {
      final item = enrichedStocks[i];
      final name = item['hts_kor_isnm'] ?? '';
      final code = item['mksc_shrn_iscd'] ?? '';
      final price = item['stck_prpr'] ?? '';
      final rate = item['prdy_ctrt'] ?? '';
      final vol = item['acml_vol'] ?? '';
      final tradingValue = item['acml_tr_pbmn'] ?? '';

      buffer.writeln('${i + 1}. $name ($code)');
      buffer.writeln(
        '   현재가: $price | 등락률: $rate% | '
        '거래량: $vol | 거래대금: $tradingValue',
      );

      final posFromHigh = item['position_from_high'];
      final high20d = item['high_20d'];
      if (posFromHigh != null && high20d != null) {
        buffer.writeln(
          '   20일고점: $high20d | 고점대비: '
          '${(posFromHigh as double).toStringAsFixed(1)}%',
        );
      }

      final foreignData =
          item['foreign_institution'] as List<Map<String, dynamic>>?;
      if (foreignData != null && foreignData.isNotEmpty) {
        buffer.write('   수급(최근${foreignData.length}일):');
        for (var j = 0; j < foreignData.length && j < 5; j++) {
          final d = foreignData[j];
          buffer.write(
            ' [${d['stck_bsop_date'] ?? 'D-$j'}]'
            '외${d['frgn_ntby_qty'] ?? '-'}'
            '/기${d['orgn_ntby_qty'] ?? '-'}',
          );
        }
        buffer.writeln();

        int fgnConsec = 0;
        for (final d in foreignData.take(5)) {
          final qty =
              int.tryParse(
                '${d['frgn_ntby_qty'] ?? '0'}'.replaceAll(',', ''),
              ) ??
              0;
          if (qty > 0) {
            fgnConsec++;
          } else {
            break;
          }
        }
        if (fgnConsec >= 2) {
          buffer.writeln('   → 외국인 $fgnConsec일 연속 순매수');
        }
      }

      final recentCandles =
          item['recent_daily_candles'] as List<Map<String, dynamic>>?;
      if (recentCandles != null && recentCandles.isNotEmpty) {
        buffer.writeln('   최근일봉:');
        for (final c in recentCandles) {
          buffer.writeln(
            '     ${c['date']} 시${c['open']} 고${c['high']} '
            '저${c['low']} 종${c['close']} 거래량${c['volume']}',
          );
        }
      }

      final minuteCandles =
          item['minute_candles_5m'] as List<Map<String, dynamic>>?;
      if (minuteCandles != null && minuteCandles.isNotEmpty) {
        buffer.writeln('   5분봉(최근1시간):');
        for (final c in minuteCandles) {
          buffer.writeln(
            '     ${c['time']} 시${c['open']} 고${c['high']} '
            '저${c['low']} 종${c['close']} 거래량${c['volume']}',
          );
        }
      }

      final news = item['news_headlines'] as List<String>?;
      if (news != null && news.isNotEmpty) {
        buffer.writeln('   뉴스: ${news.take(5).join(' | ')}');
      }

      buffer.writeln();
    }

    buffer.writeln('【상승률 상위 TOP 15】');
    for (var i = 0; i < upRanking.length && i < 15; i++) {
      final item = upRanking[i];
      buffer.writeln(
        '${i + 1}. ${item['hts_kor_isnm'] ?? ''} '
        '(${item['mksc_shrn_iscd'] ?? ''}) '
        '${item['stck_prpr'] ?? ''} '
        '${item['prdy_ctrt'] ?? ''}% '
        '거래량${item['acml_vol'] ?? ''} '
        '거래대금${item['acml_tr_pbmn'] ?? ''}',
      );
    }
    buffer.writeln();

    buffer.writeln('【하락률 상위 TOP 15】');
    for (var i = 0; i < downRanking.length && i < 15; i++) {
      final item = downRanking[i];
      buffer.writeln(
        '${i + 1}. ${item['hts_kor_isnm'] ?? ''} '
        '(${item['mksc_shrn_iscd'] ?? ''}) '
        '${item['stck_prpr'] ?? ''} '
        '${item['prdy_ctrt'] ?? ''}% '
        '거래량${item['acml_vol'] ?? ''} '
        '거래대금${item['acml_tr_pbmn'] ?? ''}',
      );
    }

    buffer.writeln();
    buffer.writeln(
      '위 데이터를 기반으로 단타 매매에 가장 적합한 TOP 3 종목을 선정하고, '
      '각 종목별 포트폴리오 배분 비율(합계 100%)을 제시하세요. '
      '적합한 종목이 없으면 매매비추천으로 판단하세요. '
      '일봉 추세, 수급 연속성, 고점대비 위치, '
      '${isMarketOpen ? '5분봉 눌림목 패턴, ' : ''}'
      '거래대금 추세를 종합 판단하세요. '
      '확신이 높은 종목에 더 높은 비중을 배분하세요. '
      '반드시 데이터 기반으로 판단하고, JSON 형식으로 응답하세요.',
    );

    return buffer.toString();
  }

  static Map<String, dynamic> _extractJson(String text) {
    final stripped = text.trim();
    if (stripped.startsWith('{')) {
      try {
        return jsonDecode(stripped) as Map<String, dynamic>;
      } on FormatException {
        // fall through
      }
    }

    final mdMatch = RegExp(
      r'```(?:json)?\s*\n?(.*?)\n?```',
      dotAll: true,
    ).firstMatch(text);
    if (mdMatch != null) {
      try {
        return jsonDecode(mdMatch.group(1)!.trim()) as Map<String, dynamic>;
      } on FormatException {
        // fall through
      }
    }

    final first = text.indexOf('{');
    final last = text.lastIndexOf('}');
    if (first != -1 && last != -1 && last > first) {
      try {
        return jsonDecode(text.substring(first, last + 1))
            as Map<String, dynamic>;
      } on FormatException {
        // fall through
      }
    }

    throw FormatException(
      'Claude 응답에서 유효한 JSON을 추출할 수 없습니다: '
      '${text.substring(0, text.length > 200 ? 200 : text.length)}...',
    );
  }

  void dispose() {
    _dio.close();
  }
}
