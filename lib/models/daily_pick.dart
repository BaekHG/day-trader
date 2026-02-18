import 'package:equatable/equatable.dart';

class DailyPickReason extends Equatable {
  final String news;
  final String supply;
  final String chart;

  const DailyPickReason({
    required this.news,
    required this.supply,
    required this.chart,
  });

  factory DailyPickReason.fromJson(Map<String, dynamic> json) {
    return DailyPickReason(
      news: json['news'] as String? ?? '',
      supply: json['supply'] as String? ?? '',
      chart: json['chart'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {'news': news, 'supply': supply, 'chart': chart};
  }

  @override
  List<Object?> get props => [news, supply, chart];
}

class EntryZone extends Equatable {
  final double low;
  final double high;

  const EntryZone({required this.low, required this.high});

  factory EntryZone.fromJson(Map<String, dynamic> json) {
    return EntryZone(
      low: (json['low'] as num?)?.toDouble() ?? 0,
      high: (json['high'] as num?)?.toDouble() ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {'low': low, 'high': high};

  @override
  List<Object?> get props => [low, high];
}

class SellStrategy extends Equatable {
  final String breakoutHold;
  final String breakoutFail;
  final String volumeDrop;
  final String sideways;

  const SellStrategy({
    required this.breakoutHold,
    required this.breakoutFail,
    required this.volumeDrop,
    required this.sideways,
  });

  factory SellStrategy.fromJson(Map<String, dynamic> json) {
    return SellStrategy(
      breakoutHold: json['breakoutHold'] as String? ?? '',
      breakoutFail: json['breakoutFail'] as String? ?? '',
      volumeDrop: json['volumeDrop'] as String? ?? '',
      sideways: json['sideways'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'breakoutHold': breakoutHold,
      'breakoutFail': breakoutFail,
      'volumeDrop': volumeDrop,
      'sideways': sideways,
    };
  }

  @override
  List<Object?> get props => [breakoutHold, breakoutFail, volumeDrop, sideways];
}

class RiskAnalysis extends Equatable {
  final String failureFactors;
  final int successProbability;

  const RiskAnalysis({
    required this.failureFactors,
    required this.successProbability,
  });

  factory RiskAnalysis.fromJson(Map<String, dynamic> json) {
    return RiskAnalysis(
      failureFactors: json['failureFactors'] as String? ?? '',
      successProbability: (json['successProbability'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'failureFactors': failureFactors,
      'successProbability': successProbability,
    };
  }

  @override
  List<Object?> get props => [failureFactors, successProbability];
}

class MarketAssessment extends Equatable {
  final int score;
  final String riskFactors;
  final List<String> favorableThemes;
  final String recommendation;

  const MarketAssessment({
    required this.score,
    required this.riskFactors,
    required this.favorableThemes,
    required this.recommendation,
  });

  bool get isRecommended => recommendation.contains('매매추천');

  factory MarketAssessment.fromJson(Map<String, dynamic> json) {
    return MarketAssessment(
      score: (json['score'] as num?)?.toInt() ?? 0,
      riskFactors: json['riskFactors'] as String? ?? '',
      favorableThemes:
          (json['favorableThemes'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      recommendation: json['recommendation'] as String? ?? '매매비추천',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'score': score,
      'riskFactors': riskFactors,
      'favorableThemes': favorableThemes,
      'recommendation': recommendation,
    };
  }

  @override
  List<Object?> get props => [
    score,
    riskFactors,
    favorableThemes,
    recommendation,
  ];
}

class DailyPick extends Equatable {
  final int rank;
  final String symbol;
  final String name;
  final double currentPrice;
  final DailyPickReason reason;
  final double positionFromHigh;
  final EntryZone entryZone;
  final double stopLoss;
  final double target1;
  final double target2;
  final double confidence;
  final List<String> tags;
  final int allocation;
  final SellStrategy sellStrategy;

  const DailyPick({
    required this.rank,
    required this.symbol,
    required this.name,
    required this.currentPrice,
    required this.reason,
    required this.positionFromHigh,
    required this.entryZone,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.confidence,
    required this.tags,
    required this.allocation,
    required this.sellStrategy,
  });

  double get expectedReturn => entryZone.high > 0
      ? ((target1 - entryZone.high) / entryZone.high) * 100
      : 0;

  double get riskPercent => entryZone.low > 0
      ? ((entryZone.low - stopLoss) / entryZone.low) * 100
      : 0;

  DailyPick copyWith({
    int? rank,
    String? symbol,
    String? name,
    double? currentPrice,
    DailyPickReason? reason,
    double? positionFromHigh,
    EntryZone? entryZone,
    double? stopLoss,
    double? target1,
    double? target2,
    double? confidence,
    List<String>? tags,
    int? allocation,
    SellStrategy? sellStrategy,
  }) {
    return DailyPick(
      rank: rank ?? this.rank,
      symbol: symbol ?? this.symbol,
      name: name ?? this.name,
      currentPrice: currentPrice ?? this.currentPrice,
      reason: reason ?? this.reason,
      positionFromHigh: positionFromHigh ?? this.positionFromHigh,
      entryZone: entryZone ?? this.entryZone,
      stopLoss: stopLoss ?? this.stopLoss,
      target1: target1 ?? this.target1,
      target2: target2 ?? this.target2,
      confidence: confidence ?? this.confidence,
      tags: tags ?? this.tags,
      allocation: allocation ?? this.allocation,
      sellStrategy: sellStrategy ?? this.sellStrategy,
    );
  }

  factory DailyPick.fromJson(Map<String, dynamic> json) {
    return DailyPick(
      rank: (json['rank'] as num?)?.toInt() ?? 1,
      symbol: json['symbol'] as String? ?? '',
      name: json['name'] as String? ?? '',
      currentPrice: (json['currentPrice'] as num?)?.toDouble() ?? 0,
      reason: DailyPickReason.fromJson(
        json['reason'] as Map<String, dynamic>? ?? {},
      ),
      positionFromHigh: (json['positionFromHigh'] as num?)?.toDouble() ?? 0,
      entryZone: EntryZone.fromJson(
        json['entryZone'] as Map<String, dynamic>? ?? {},
      ),
      stopLoss: (json['stopLoss'] as num?)?.toDouble() ?? 0,
      target1: (json['target1'] as num?)?.toDouble() ?? 0,
      target2: (json['target2'] as num?)?.toDouble() ?? 0,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      tags:
          (json['tags'] as List<dynamic>?)?.map((e) => e as String).toList() ??
          [],
      allocation: (json['allocation'] as num?)?.toInt() ?? 0,
      sellStrategy: SellStrategy.fromJson(
        json['sellStrategy'] as Map<String, dynamic>? ?? {},
      ),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'rank': rank,
      'symbol': symbol,
      'name': name,
      'currentPrice': currentPrice,
      'reason': reason.toJson(),
      'positionFromHigh': positionFromHigh,
      'entryZone': entryZone.toJson(),
      'stopLoss': stopLoss,
      'target1': target1,
      'target2': target2,
      'confidence': confidence,
      'tags': tags,
      'allocation': allocation,
      'sellStrategy': sellStrategy.toJson(),
    };
  }

  @override
  List<Object?> get props => [
    rank,
    symbol,
    name,
    currentPrice,
    reason,
    positionFromHigh,
    entryZone,
    stopLoss,
    target1,
    target2,
    confidence,
    tags,
    allocation,
    sellStrategy,
  ];
}

class DailyPicksResult extends Equatable {
  final MarketAssessment marketAssessment;
  final List<DailyPick> picks;
  final RiskAnalysis riskAnalysis;
  final String marketSummary;
  final String analysisTime;
  final int marketScore;
  final List<String> newsHeadlines;

  const DailyPicksResult({
    required this.marketAssessment,
    this.picks = const [],
    required this.riskAnalysis,
    required this.marketSummary,
    required this.analysisTime,
    required this.marketScore,
    this.newsHeadlines = const [],
  });

  /// Backward-compat: first pick (if any)
  DailyPick? get pick => picks.isNotEmpty ? picks.first : null;

  /// Total allocation across all picks (should sum to 100 when recommended)
  int get totalAllocation => picks.fold(0, (sum, p) => sum + p.allocation);

  DailyPicksResult copyWith({
    MarketAssessment? marketAssessment,
    List<DailyPick>? picks,
    RiskAnalysis? riskAnalysis,
    String? marketSummary,
    String? analysisTime,
    int? marketScore,
    List<String>? newsHeadlines,
  }) {
    return DailyPicksResult(
      marketAssessment: marketAssessment ?? this.marketAssessment,
      picks: picks ?? this.picks,
      riskAnalysis: riskAnalysis ?? this.riskAnalysis,
      marketSummary: marketSummary ?? this.marketSummary,
      analysisTime: analysisTime ?? this.analysisTime,
      marketScore: marketScore ?? this.marketScore,
      newsHeadlines: newsHeadlines ?? this.newsHeadlines,
    );
  }

  factory DailyPicksResult.fromJson(Map<String, dynamic> json) {
    final assessment = MarketAssessment.fromJson(
      json['marketAssessment'] as Map<String, dynamic>? ?? {},
    );

    // Parse picks array (new TOP 3 format)
    List<DailyPick> picks = [];
    if (assessment.isRecommended) {
      final picksJson = json['picks'] as List<dynamic>?;
      if (picksJson != null) {
        picks = picksJson
            .map((e) => DailyPick.fromJson(e as Map<String, dynamic>))
            .toList();
        // Sort by rank
        picks.sort((a, b) => a.rank.compareTo(b.rank));
      } else if (json['pick'] != null) {
        // Backward compat: old single-pick format
        final pickJson = json['pick'] as Map<String, dynamic>;
        final sellJson = json['sellStrategy'] as Map<String, dynamic>?;
        if (sellJson != null) {
          pickJson['sellStrategy'] = sellJson;
        }
        pickJson['rank'] = 1;
        pickJson['allocation'] = 100;
        picks = [DailyPick.fromJson(pickJson)];
      }
    }

    return DailyPicksResult(
      marketAssessment: assessment,
      picks: picks,
      riskAnalysis: RiskAnalysis.fromJson(
        json['riskAnalysis'] as Map<String, dynamic>? ?? {},
      ),
      marketSummary: json['marketSummary'] as String? ?? '',
      analysisTime: json['analysisTime'] as String? ?? '',
      marketScore: (json['marketScore'] as num?)?.toInt() ?? 0,
      newsHeadlines:
          (json['newsHeadlines'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'marketAssessment': marketAssessment.toJson(),
      'picks': picks.map((p) => p.toJson()).toList(),
      'riskAnalysis': riskAnalysis.toJson(),
      'marketSummary': marketSummary,
      'analysisTime': analysisTime,
      'marketScore': marketScore,
      'newsHeadlines': newsHeadlines,
    };
  }

  @override
  List<Object?> get props => [
    marketAssessment,
    picks,
    riskAnalysis,
    marketSummary,
    analysisTime,
    marketScore,
    newsHeadlines,
  ];
}
