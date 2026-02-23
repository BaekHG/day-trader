import 'dart:convert';

import 'package:equatable/equatable.dart';

class AiAnalysis extends Equatable {
  final int? id;
  final int marketScore;
  final String recommendation;
  final String riskFactors;
  final List<String> favorableThemes;
  final List<dynamic> picks;
  final Map<String, dynamic> riskAnalysis;
  final String marketSummary;
  final double successProbability;
  final DateTime analyzedAt;

  const AiAnalysis({
    this.id,
    required this.marketScore,
    required this.recommendation,
    required this.riskFactors,
    required this.favorableThemes,
    required this.picks,
    required this.riskAnalysis,
    required this.marketSummary,
    required this.successProbability,
    required this.analyzedAt,
  });

  AiAnalysis copyWith({
    int? id,
    int? marketScore,
    String? recommendation,
    String? riskFactors,
    List<String>? favorableThemes,
    List<dynamic>? picks,
    Map<String, dynamic>? riskAnalysis,
    String? marketSummary,
    double? successProbability,
    DateTime? analyzedAt,
  }) {
    return AiAnalysis(
      id: id ?? this.id,
      marketScore: marketScore ?? this.marketScore,
      recommendation: recommendation ?? this.recommendation,
      riskFactors: riskFactors ?? this.riskFactors,
      favorableThemes: favorableThemes ?? this.favorableThemes,
      picks: picks ?? this.picks,
      riskAnalysis: riskAnalysis ?? this.riskAnalysis,
      marketSummary: marketSummary ?? this.marketSummary,
      successProbability: successProbability ?? this.successProbability,
      analyzedAt: analyzedAt ?? this.analyzedAt,
    );
  }

  static List<String> _parseStringList(dynamic value) {
    if (value == null) return [];
    if (value is List) {
      return value.map((e) => e.toString()).toList();
    }
    if (value is String) {
      try {
        final decoded = json.decode(value);
        if (decoded is List) {
          return decoded.map((e) => e.toString()).toList();
        }
      } catch (_) {}
    }
    return [];
  }

  static List<dynamic> _parseList(dynamic value) {
    if (value == null) return [];
    if (value is List) return value;
    if (value is String) {
      try {
        final decoded = json.decode(value);
        if (decoded is List) return decoded;
      } catch (_) {}
    }
    return [];
  }

  static Map<String, dynamic> _parseMap(dynamic value) {
    if (value == null) return {};
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    if (value is String) {
      try {
        final decoded = json.decode(value);
        if (decoded is Map) return Map<String, dynamic>.from(decoded);
      } catch (_) {}
    }
    return {};
  }

  factory AiAnalysis.fromJson(Map<String, dynamic> json) {
    return AiAnalysis(
      id: json['id'] as int?,
      marketScore: json['market_score'] as int? ?? 0,
      recommendation: json['recommendation'] as String? ?? '',
      riskFactors: json['risk_factors'] as String? ?? '',
      favorableThemes: _parseStringList(json['favorable_themes']),
      picks: _parseList(json['picks']),
      riskAnalysis: _parseMap(json['risk_analysis']),
      marketSummary: json['market_summary'] as String? ?? '',
      successProbability:
          (json['success_probability'] as num?)?.toDouble() ?? 0.0,
      analyzedAt: json['analyzed_at'] != null
          ? DateTime.parse(json['analyzed_at'] as String)
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'market_score': marketScore,
      'recommendation': recommendation,
      'risk_factors': riskFactors,
      'favorable_themes': json.encode(favorableThemes),
      'picks': json.encode(picks),
      'risk_analysis': json.encode(riskAnalysis),
      'market_summary': marketSummary,
      'success_probability': successProbability,
      'analyzed_at': analyzedAt.toIso8601String(),
    };
  }

  @override
  List<Object?> get props => [
    id,
    marketScore,
    recommendation,
    riskFactors,
    favorableThemes,
    picks,
    riskAnalysis,
    marketSummary,
    successProbability,
    analyzedAt,
  ];
}
