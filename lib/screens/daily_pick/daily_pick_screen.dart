import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shimmer/shimmer.dart';

import 'package:day_trader/core/theme/app_theme.dart';
import 'package:day_trader/core/utils/formatters.dart';
import 'package:day_trader/models/daily_pick.dart';
import 'package:day_trader/providers/daily_pick_provider.dart';
import 'package:day_trader/providers/market_data_provider.dart';
import 'package:url_launcher/url_launcher.dart';

class DailyPickScreen extends ConsumerStatefulWidget {
  const DailyPickScreen({super.key});

  @override
  ConsumerState<DailyPickScreen> createState() => _DailyPickScreenState();
}

class _DailyPickScreenState extends ConsumerState<DailyPickScreen> {
  @override
  void initState() {
    super.initState();
    // Auto-fetch free market data on tab open
    Future.microtask(
      () => ref.read(marketDataProvider.notifier).fetchIfNeeded(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final marketAsync = ref.watch(marketDataProvider);
    final picksAsync = ref.watch(dailyPicksProvider);

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.accent,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            const Text('데일리픽'),
          ],
        ),
        actions: const [SizedBox(width: 4)],
      ),
      body: RefreshIndicator(
        color: AppColors.accent,
        backgroundColor: AppColors.card,
        onRefresh: () => ref.read(marketDataProvider.notifier).refresh(),
        child: marketAsync.when(
          data: (data) {
            if (data == null) {
              // Still initial — show shimmer
              return const _FreeDataShimmer();
            }
            return _MainContent(marketData: data, picksAsync: picksAsync);
          },
          loading: () => const _FreeDataShimmer(),
          error: (error, _) => _FreeDataError(
            error: error.toString(),
            onRetry: () => ref.read(marketDataProvider.notifier).refresh(),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Main Content — Free Data + AI Section
// ─────────────────────────────────────────────

class _MainContent extends ConsumerWidget {
  const _MainContent({required this.marketData, required this.picksAsync});

  final MarketData marketData;
  final AsyncValue<DailyPicksResult?> picksAsync;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: 100),
      children: [
        // ── 장 마감시 안내 배너 ──
        if (!marketData.isMarketOpen)
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppColors.warning.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: AppColors.warning.withValues(alpha: 0.2),
                width: 0.5,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.schedule_rounded,
                  size: 14,
                  color: AppColors.warning.withValues(alpha: 0.8),
                ),
                const SizedBox(width: 6),
                Text(
                  '장 마감 — 전일 마감 데이터입니다',
                  style: TextStyle(
                    color: AppColors.warning.withValues(alpha: 0.9),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        // ── Free Data Section (auto-loaded) ──
        _KosdaqIndexCard(kosdaqIndex: marketData.kosdaqIndex),
        const SizedBox(height: 8),
        _VolumeRankingCard(volumeRanking: marketData.topVolumeStocks),
        const SizedBox(height: 8),
        _FluctuationToggleCard(
          upRanking: marketData.upRanking,
          downRanking: marketData.downRanking,
        ),
        const SizedBox(height: 8),
        if (marketData.stockNews.isNotEmpty) ...[
          _StockNewsCard(stockNews: marketData.stockNews),
          const SizedBox(height: 8),
        ],

        // ── AI Analysis Section (manual) ──
        picksAsync.when(
          data: (result) {
            if (result == null) {
              return _AiAnalysisButton(
                onAnalyze: () => ref
                    .read(dailyPicksProvider.notifier)
                    .analyzeWithMarketData(marketData),
              );
            }
            return _AiResultSection(result: result, marketData: marketData);
          },
          loading: () => const _AiLoadingState(),
          error: (error, _) => _AiErrorState(
            error: error.toString(),
            onRetry: () => ref
                .read(dailyPicksProvider.notifier)
                .analyzeWithMarketData(marketData),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────
// KOSDAQ Index Card
// ─────────────────────────────────────────────

class _KosdaqIndexCard extends StatelessWidget {
  const _KosdaqIndexCard({required this.kosdaqIndex});

  final Map<String, dynamic> kosdaqIndex;

  @override
  Widget build(BuildContext context) {
    final indexPrice = kosdaqIndex['index_price'] as String? ?? '';
    final changeRate = kosdaqIndex['change_rate'] as String? ?? '';
    final changeValue = kosdaqIndex['change_value'] as String? ?? '';

    final rateNum = double.tryParse(changeRate) ?? 0;
    final isUp = rateNum >= 0;
    final color = isUp ? AppColors.profit : AppColors.loss;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [color.withValues(alpha: 0.06), AppColors.card],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.15), width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(Icons.show_chart_rounded, size: 18, color: color),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '코스닥 지수',
                style: TextStyle(
                  color: AppColors.textTertiary,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                indexPrice,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ],
          ),
          const Spacer(),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${isUp ? '+' : ''}$changeValue',
                style: TextStyle(
                  color: color,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(height: 2),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  '${isUp ? '+' : ''}$changeRate%',
                  style: TextStyle(
                    color: color,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Volume Ranking Card
// ─────────────────────────────────────────────

class _VolumeRankingCard extends StatelessWidget {
  const _VolumeRankingCard({required this.volumeRanking});

  final List<Map<String, dynamic>> volumeRanking;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
            child: Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: AppColors.warning.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Icon(
                    Icons.local_fire_department_rounded,
                    size: 16,
                    color: AppColors.warning,
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  '거래량 TOP',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const Spacer(),
                Text(
                  '${volumeRanking.length}종목',
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          Container(
            width: double.infinity,
            height: 0.5,
            color: AppColors.border,
          ),
          ...volumeRanking.asMap().entries.map((entry) {
            final i = entry.key;
            final stock = entry.value;
            return _VolumeRankRow(rank: i + 1, stock: stock);
          }),
        ],
      ),
    );
  }
}

class _VolumeRankRow extends StatelessWidget {
  const _VolumeRankRow({required this.rank, required this.stock});

  final int rank;
  final Map<String, dynamic> stock;

  @override
  Widget build(BuildContext context) {
    final name = stock['hts_kor_isnm'] as String? ?? '';
    final price = stock['stck_prpr'] as String? ?? '0';
    final changeRate = stock['prdy_ctrt'] as String? ?? '0';
    final volume = stock['acml_vol'] as String? ?? '0';

    final rateNum = double.tryParse(changeRate) ?? 0;
    final isUp = rateNum >= 0;
    final color = rateNum == 0
        ? AppColors.textSecondary
        : isUp
        ? AppColors.profit
        : AppColors.loss;

    final volInt = int.tryParse(volume) ?? 0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: AppColors.border.withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 22,
            child: Text(
              '$rank',
              style: TextStyle(
                color: rank <= 3 ? AppColors.warning : AppColors.textTertiary,
                fontSize: 12,
                fontWeight: rank <= 3 ? FontWeight.w800 : FontWeight.w600,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              name,
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            Formatters.formatVolume(volInt),
            style: const TextStyle(
              color: AppColors.textTertiary,
              fontSize: 11,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(width: 12),
          SizedBox(
            width: 72,
            child: Text(
              Formatters.formatKRW(int.tryParse(price) ?? 0),
              style: const TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
              textAlign: TextAlign.right,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 52,
            child: Text(
              '${isUp ? '+' : ''}$changeRate%',
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w700,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Up/Down Fluctuation Toggle Card
// ─────────────────────────────────────────────

class _FluctuationToggleCard extends StatefulWidget {
  const _FluctuationToggleCard({
    required this.upRanking,
    required this.downRanking,
  });

  final List<Map<String, dynamic>> upRanking;
  final List<Map<String, dynamic>> downRanking;

  @override
  State<_FluctuationToggleCard> createState() => _FluctuationToggleCardState();
}

class _FluctuationToggleCardState extends State<_FluctuationToggleCard> {
  bool _showUp = true;

  @override
  Widget build(BuildContext context) {
    final items = (_showUp ? widget.upRanking : widget.downRanking).take(10);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        children: [
          // Toggle header
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
            child: Row(
              children: [
                _FluctuationTab(
                  label: '상승 TOP',
                  icon: Icons.trending_up_rounded,
                  color: AppColors.profit,
                  selected: _showUp,
                  onTap: () => setState(() => _showUp = true),
                ),
                const SizedBox(width: 6),
                _FluctuationTab(
                  label: '하락 TOP',
                  icon: Icons.trending_down_rounded,
                  color: AppColors.loss,
                  selected: !_showUp,
                  onTap: () => setState(() => _showUp = false),
                ),
              ],
            ),
          ),
          Container(
            width: double.infinity,
            height: 0.5,
            color: AppColors.border,
          ),
          ...items.toList().asMap().entries.map((entry) {
            final i = entry.key;
            final stock = entry.value;
            return _FluctuationRow(rank: i + 1, stock: stock, isUp: _showUp);
          }),
        ],
      ),
    );
  }
}

class _FluctuationTab extends StatelessWidget {
  const _FluctuationTab({
    required this.label,
    required this.icon,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected ? color.withValues(alpha: 0.1) : AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: selected ? color.withValues(alpha: 0.3) : AppColors.border,
              width: 0.5,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                size: 14,
                color: selected ? color : AppColors.textTertiary,
              ),
              const SizedBox(width: 4),
              Text(
                label,
                style: TextStyle(
                  color: selected ? color : AppColors.textTertiary,
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FluctuationRow extends StatelessWidget {
  const _FluctuationRow({
    required this.rank,
    required this.stock,
    required this.isUp,
  });

  final int rank;
  final Map<String, dynamic> stock;
  final bool isUp;

  @override
  Widget build(BuildContext context) {
    final name = stock['hts_kor_isnm'] as String? ?? '';
    final price = stock['stck_prpr'] as String? ?? '0';
    final changeRate = stock['prdy_ctrt'] as String? ?? '0';

    final rateNum = double.tryParse(changeRate) ?? 0;
    final color = rateNum == 0
        ? AppColors.textSecondary
        : rateNum > 0
        ? AppColors.profit
        : AppColors.loss;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: AppColors.border.withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 22,
            child: Text(
              '$rank',
              style: TextStyle(
                color: rank <= 3
                    ? (isUp ? AppColors.profit : AppColors.loss)
                    : AppColors.textTertiary,
                fontSize: 12,
                fontWeight: rank <= 3 ? FontWeight.w800 : FontWeight.w600,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              name,
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 72,
            child: Text(
              Formatters.formatKRW(int.tryParse(price) ?? 0),
              style: const TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
              textAlign: TextAlign.right,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 58,
            child: Text(
              '${rateNum >= 0 ? '+' : ''}$changeRate%',
              style: TextStyle(
                color: color,
                fontSize: 13,
                fontWeight: FontWeight.w800,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Stock News Card
// ─────────────────────────────────────────────

class _StockNewsCard extends StatelessWidget {
  const _StockNewsCard({required this.stockNews});

  final Map<String, List<NewsArticle>> stockNews;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(
                  Icons.newspaper_rounded,
                  size: 14,
                  color: AppColors.accent,
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                '관련 뉴스',
                style: TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...stockNews.entries.map((entry) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      entry.key,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  ...entry.value.take(3).map((article) {
                    final hasUrl = article.url.isNotEmpty;
                    return Padding(
                      padding: const EdgeInsets.only(left: 4, bottom: 4),
                      child: GestureDetector(
                        onTap: hasUrl
                            ? () => launchUrl(
                                Uri.parse(article.url),
                                mode: LaunchMode.externalApplication,
                              )
                            : null,
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              hasUrl ? Icons.open_in_new_rounded : Icons.circle,
                              size: hasUrl ? 12 : 5,
                              color: hasUrl
                                  ? AppColors.accent
                                  : AppColors.textTertiary,
                            ),
                            SizedBox(width: hasUrl ? 6 : 8),
                            Expanded(
                              child: Text(
                                article.title,
                                style: TextStyle(
                                  color: hasUrl
                                      ? AppColors.accent
                                      : AppColors.textSecondary,
                                  fontSize: 12,
                                  height: 1.5,
                                  decoration: hasUrl
                                      ? TextDecoration.underline
                                      : TextDecoration.none,
                                  decorationColor: AppColors.accent.withValues(
                                    alpha: 0.4,
                                  ),
                                ),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (article.source.isNotEmpty) ...[
                              const SizedBox(width: 6),
                              Text(
                                article.source,
                                style: TextStyle(
                                  color: AppColors.textTertiary.withValues(
                                    alpha: 0.7,
                                  ),
                                  fontSize: 10,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    );
                  }),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// AI Analysis Button
// ─────────────────────────────────────────────

class _AiAnalysisButton extends StatelessWidget {
  const _AiAnalysisButton({required this.onAnalyze});

  final VoidCallback onAnalyze;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.accent.withValues(alpha: 0.06), AppColors.card],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.accent.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
      child: Column(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.1),
              shape: BoxShape.circle,
              border: Border.all(
                color: AppColors.accent.withValues(alpha: 0.25),
                width: 0.5,
              ),
            ),
            child: const Icon(
              Icons.auto_awesome,
              color: AppColors.accent,
              size: 22,
            ),
          ),
          const SizedBox(height: 14),
          const Text(
            '뉴스 모멘텀 + 수급 + 차트 종합 분석',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: onAnalyze,
              icon: const Icon(Icons.rocket_launch_rounded, size: 18),
              label: const Text(
                'AI 분석 시작',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.accent,
                foregroundColor: AppColors.background,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.info_outline,
                size: 12,
                color: AppColors.textTertiary,
              ),
              const SizedBox(width: 4),
              Text(
                '~120원/회 · GPT-4o 분석',
                style: TextStyle(
                  color: AppColors.textTertiary.withValues(alpha: 0.8),
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// AI Loading State (inline, below free data)
// ─────────────────────────────────────────────

class _AiLoadingState extends StatefulWidget {
  const _AiLoadingState();

  @override
  State<_AiLoadingState> createState() => _AiLoadingStateState();
}

class _AiLoadingStateState extends State<_AiLoadingState> {
  int _currentStep = 0;

  static const _steps = ['수급 데이터 수집 중...', 'AI 분석 중...', '결과 정리 중...'];

  @override
  void initState() {
    super.initState();
    _advanceSteps();
  }

  Future<void> _advanceSteps() async {
    await Future.delayed(const Duration(milliseconds: 2000));
    if (mounted) setState(() => _currentStep = 1);
    await Future.delayed(const Duration(milliseconds: 3000));
    if (mounted) setState(() => _currentStep = 2);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        children: [
          const SizedBox(
            width: 36,
            height: 36,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              color: AppColors.accent,
            ),
          ),
          const SizedBox(height: 16),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Text(
              _steps[_currentStep],
              key: ValueKey(_currentStep),
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(_steps.length, (i) {
              return Container(
                width: 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i <= _currentStep
                      ? AppColors.accent
                      : AppColors.border,
                ),
              );
            }),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// AI Error State (inline)
// ─────────────────────────────────────────────

class _AiErrorState extends StatelessWidget {
  const _AiErrorState({required this.error, required this.onRetry});

  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.loss.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
      child: Column(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.lossBg,
              shape: BoxShape.circle,
              border: Border.all(
                color: AppColors.loss.withValues(alpha: 0.3),
                width: 0.5,
              ),
            ),
            child: const Icon(
              Icons.error_outline,
              size: 22,
              color: AppColors.loss,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'AI 분석 실패',
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            error,
            style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
            textAlign: TextAlign.center,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            height: 40,
            child: OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('다시 시도'),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// AI Result Section (below free data)
// ─────────────────────────────────────────────

class _AiResultSection extends ConsumerWidget {
  const _AiResultSection({required this.result, required this.marketData});

  final DailyPicksResult result;
  final MarketData marketData;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assessment = result.marketAssessment;
    final isRecommended = assessment.isRecommended;

    return Column(
      children: [
        // Divider between free data & AI results
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Row(
            children: [
              Container(
                width: 20,
                height: 0.5,
                color: AppColors.accent.withValues(alpha: 0.3),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.auto_awesome, size: 11, color: AppColors.accent),
                    SizedBox(width: 4),
                    Text(
                      'AI 분석 결과',
                      style: TextStyle(
                        color: AppColors.accent,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Container(
                  height: 0.5,
                  color: AppColors.accent.withValues(alpha: 0.3),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 4),

        // Market Assessment Card
        _MarketAssessmentCard(result: result),
        const SizedBox(height: 8),

        // If not recommended — rest day
        if (!isRecommended) ...[_RestDayCard(), const SizedBox(height: 8)],

        // If recommended — portfolio allocation summary + TOP 3 picks
        if (isRecommended && result.picks.isNotEmpty) ...[
          _PortfolioAllocationCard(picks: result.picks),
          const SizedBox(height: 8),
          // Each pick as a unified full-detail card
          ...result.picks.expand((pick) {
            final newsKey = pick.name.isNotEmpty ? pick.name : pick.symbol;
            final articles = marketData.stockNews[newsKey] ?? [];
            return [
              _PickFullCard(pick: pick, newsArticles: articles),
              const SizedBox(height: 8),
            ];
          }),
        ],

        // Risk Analysis Card (always shown)
        _RiskAnalysisCard(riskAnalysis: result.riskAnalysis),
        const SizedBox(height: 8),

        // Market Summary
        _MarketSummaryCard(summary: result.marketSummary),
        const SizedBox(height: 16),

        // Re-analyze button
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: SizedBox(
            width: double.infinity,
            height: 44,
            child: OutlinedButton.icon(
              onPressed: () => ref
                  .read(dailyPicksProvider.notifier)
                  .analyzeWithMarketData(marketData),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('다시 분석 (~120원)'),
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Disclaimer
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border, width: 0.5),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.warning_amber_rounded,
                  size: 14,
                  color: AppColors.warning,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'AI 분석은 참고용이며, 투자 판단은 본인 책임입니다. '
                    '분석 시간: ${result.analysisTime}',
                    style: const TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 11,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────
// Free Data Loading Shimmer
// ─────────────────────────────────────────────

class _FreeDataShimmer extends StatelessWidget {
  const _FreeDataShimmer();

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Shimmer.fromColors(
          baseColor: AppColors.card,
          highlightColor: AppColors.border,
          child: Column(
            children: [
              const SizedBox(height: 12),
              // KOSDAQ index shimmer
              Container(
                height: 72,
                decoration: BoxDecoration(
                  color: AppColors.card,
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              const SizedBox(height: 14),
              // Volume ranking shimmer
              Container(
                height: 320,
                decoration: BoxDecoration(
                  color: AppColors.card,
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              const SizedBox(height: 14),
              // Fluctuation shimmer
              Container(
                height: 280,
                decoration: BoxDecoration(
                  color: AppColors.card,
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              const SizedBox(height: 14),
              // News shimmer
              Container(
                height: 200,
                decoration: BoxDecoration(
                  color: AppColors.card,
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Free Data Error
// ─────────────────────────────────────────────

class _FreeDataError extends StatelessWidget {
  const _FreeDataError({required this.error, required this.onRetry});

  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.6,
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    color: AppColors.lossBg,
                    shape: BoxShape.circle,
                    border: Border.all(color: AppColors.loss, width: 0.5),
                  ),
                  child: const Icon(
                    Icons.cloud_off_rounded,
                    size: 28,
                    color: AppColors.loss,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  '데이터 로딩 실패',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  error,
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                  textAlign: TextAlign.center,
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 20),
                ElevatedButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  label: const Text('다시 시도'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Market Assessment Card
// ─────────────────────────────────────────────

class _MarketAssessmentCard extends StatelessWidget {
  const _MarketAssessmentCard({required this.result});

  final DailyPicksResult result;

  @override
  Widget build(BuildContext context) {
    final assessment = result.marketAssessment;
    final score = assessment.score;
    final scoreColor = score >= 70
        ? AppColors.profit
        : score >= 30
        ? AppColors.warning
        : AppColors.loss;
    final isRecommended = assessment.isRecommended;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            scoreColor.withValues(alpha: 0.08),
            AppColors.card,
            AppColors.card,
          ],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: scoreColor.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.analytics_outlined, size: 16, color: scoreColor),
              const SizedBox(width: 6),
              Text(
                '단타 적합도',
                style: TextStyle(
                  color: scoreColor,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              // Recommendation badge
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: isRecommended
                      ? AppColors.profit.withValues(alpha: 0.15)
                      : AppColors.loss.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: isRecommended
                        ? AppColors.profit.withValues(alpha: 0.4)
                        : AppColors.loss.withValues(alpha: 0.4),
                    width: 0.5,
                  ),
                ),
                child: Text(
                  assessment.recommendation,
                  style: TextStyle(
                    color: isRecommended ? AppColors.profit : AppColors.loss,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _ScoreGauge(score: score, color: scoreColor),
              const SizedBox(width: 20),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '적합도 점수',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '$score점',
                      style: TextStyle(
                        color: scoreColor,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      result.analysisTime,
                      style: const TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (assessment.riskFactors.isNotEmpty) ...[
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              height: 0.5,
              color: AppColors.border,
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.shield_outlined,
                  size: 14,
                  color: AppColors.warning,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    assessment.riskFactors,
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
                ),
              ],
            ),
          ],
          if (assessment.favorableThemes.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: assessment.favorableThemes
                  .map((theme) => _ThemeChip(label: theme))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Rest Day Card (매매비추천)
// ─────────────────────────────────────────────

class _RestDayCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 20),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: AppColors.surface,
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.border, width: 0.5),
            ),
            child: const Icon(
              Icons.nightlight_round,
              size: 36,
              color: AppColors.textTertiary,
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            '오늘은 쉬는 날',
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '시장 상황이 단타 매매에 적합하지 않습니다.\n무리한 매매보다 관망이 최선의 전략입니다.',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.6,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Portfolio Allocation Card (TOP 3 Summary)
// ─────────────────────────────────────────────

class _PortfolioAllocationCard extends StatelessWidget {
  const _PortfolioAllocationCard({required this.picks});

  final List<DailyPick> picks;

  Color _rankColor(int rank) {
    switch (rank) {
      case 1:
        return const Color(0xFFFFD700);
      case 2:
        return const Color(0xFFC0C0C0);
      case 3:
        return const Color(0xFFCD7F32);
      default:
        return AppColors.accent;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.accent.withValues(alpha: 0.06), AppColors.card],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.accent.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(
                  Icons.pie_chart_rounded,
                  size: 14,
                  color: AppColors.accent,
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                '포트폴리오 배분',
                style: TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              Text(
                'TOP ${picks.length}',
                style: const TextStyle(
                  color: AppColors.accent,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // Allocation bar
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: SizedBox(
              height: 10,
              child: Row(
                children: picks.map((pick) {
                  return Expanded(
                    flex: pick.allocation,
                    child: Container(
                      margin: EdgeInsets.only(
                        right: pick.rank < picks.length ? 2 : 0,
                      ),
                      color: _rankColor(pick.rank),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // Pick summary rows
          ...picks.map((pick) {
            final color = _rankColor(pick.rank);
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: color,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '#${pick.rank}',
                    style: TextStyle(
                      color: color,
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      pick.name,
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(
                    '${pick.allocation}%',
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                  const SizedBox(width: 12),
                  _ConfidenceBadge(confidence: pick.confidence),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Pick Detail Card
// ─────────────────────────────────────────────

class _PickDetailCard extends StatelessWidget {
  const _PickDetailCard({required this.pick});

  final DailyPick pick;

  Color _rankColor(int rank) {
    switch (rank) {
      case 1:
        return const Color(0xFFFFD700); // gold
      case 2:
        return const Color(0xFFC0C0C0); // silver
      case 3:
        return const Color(0xFFCD7F32); // bronze
      default:
        return AppColors.accent;
    }
  }

  String _rankLabel(int rank) {
    switch (rank) {
      case 1:
        return '1st';
      case 2:
        return '2nd';
      case 3:
        return '3rd';
      default:
        return '#$rank';
    }
  }

  @override
  Widget build(BuildContext context) {
    final rankColor = _rankColor(pick.rank);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: pick.rank == 1
              ? rankColor.withValues(alpha: 0.3)
              : AppColors.border,
          width: pick.rank == 1 ? 1 : 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with rank badge
          Row(
            children: [
              // Rank badge
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      rankColor.withValues(alpha: 0.2),
                      rankColor.withValues(alpha: 0.08),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: rankColor.withValues(alpha: 0.4),
                    width: 0.5,
                  ),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      _rankLabel(pick.rank),
                      style: TextStyle(
                        color: rankColor,
                        fontSize: 12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            pick.name,
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 17,
                              fontWeight: FontWeight.w700,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 8),
                        // Allocation badge
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.accent.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            '${pick.allocation}%',
                            style: const TextStyle(
                              color: AppColors.accent,
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                              fontFeatures: [FontFeature.tabularFigures()],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Text(
                          pick.symbol,
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          Formatters.formatKRW(pick.currentPrice.toInt()),
                          style: const TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            fontFeatures: [FontFeature.tabularFigures()],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              _ConfidenceBadge(confidence: pick.confidence),
            ],
          ),
          const SizedBox(height: 16),

          // Position from High
          _PositionFromHighBar(positionFromHigh: pick.positionFromHigh),
          const SizedBox(height: 14),

          // Entry zone + targets
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              children: [
                _PriceLevelRow(
                  label: '매수 구간',
                  value:
                      '${Formatters.formatKRW(pick.entryZone.low.toInt())} ~ ${Formatters.formatKRW(pick.entryZone.high.toInt())}',
                  color: AppColors.accent,
                  icon: Icons.login_rounded,
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  height: 0.5,
                  color: AppColors.border,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '1차 목표',
                  value: Formatters.formatKRW(pick.target1.toInt()),
                  color: AppColors.profit,
                  icon: Icons.flag_outlined,
                  suffix: pick.entryZone.high > 0
                      ? ' (+${(((pick.target1 - pick.entryZone.high) / pick.entryZone.high) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '2차 목표',
                  value: Formatters.formatKRW(pick.target2.toInt()),
                  color: const Color(0xFF00E676),
                  icon: Icons.flag_rounded,
                  suffix: pick.entryZone.high > 0
                      ? ' (+${(((pick.target2 - pick.entryZone.high) / pick.entryZone.high) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  height: 0.5,
                  color: AppColors.border,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '손절가',
                  value: Formatters.formatKRW(pick.stopLoss.toInt()),
                  color: AppColors.loss,
                  icon: Icons.block_rounded,
                  suffix: pick.entryZone.low > 0
                      ? ' (-${(((pick.entryZone.low - pick.stopLoss) / pick.entryZone.low) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Tags
          if (pick.tags.isNotEmpty)
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: pick.tags.map((tag) => _TagChip(label: tag)).toList(),
            ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Unified Pick Full Card (all details inline)
// ─────────────────────────────────────────────

class _PickFullCard extends StatefulWidget {
  const _PickFullCard({required this.pick, this.newsArticles = const []});

  final DailyPick pick;
  final List<NewsArticle> newsArticles;

  @override
  State<_PickFullCard> createState() => _PickFullCardState();
}

class _PickFullCardState extends State<_PickFullCard>
    with SingleTickerProviderStateMixin {
  bool _expanded = true;

  Color _rankColor(int rank) {
    switch (rank) {
      case 1:
        return const Color(0xFFFFD700);
      case 2:
        return const Color(0xFFC0C0C0);
      case 3:
        return const Color(0xFFCD7F32);
      default:
        return AppColors.accent;
    }
  }

  String _rankLabel(int rank) {
    switch (rank) {
      case 1:
        return '1st';
      case 2:
        return '2nd';
      case 3:
        return '3rd';
      default:
        return '#$rank';
    }
  }

  @override
  Widget build(BuildContext context) {
    final pick = widget.pick;
    final rankColor = _rankColor(pick.rank);
    final isTop = pick.rank == 1;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        gradient: isTop
            ? LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  rankColor.withValues(alpha: 0.06),
                  AppColors.card,
                  AppColors.card,
                ],
              )
            : null,
        color: isTop ? null : AppColors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isTop ? rankColor.withValues(alpha: 0.35) : AppColors.border,
          width: isTop ? 1.0 : 0.5,
        ),
        boxShadow: isTop
            ? [
                BoxShadow(
                  color: rankColor.withValues(alpha: 0.08),
                  blurRadius: 20,
                  offset: const Offset(0, 4),
                ),
              ]
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── HEADER (always visible, tappable) ──
          GestureDetector(
            onTap: () => setState(() => _expanded = !_expanded),
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  // Rank badge
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          rankColor.withValues(alpha: 0.25),
                          rankColor.withValues(alpha: 0.08),
                        ],
                      ),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: rankColor.withValues(alpha: 0.5),
                        width: 0.5,
                      ),
                    ),
                    child: Center(
                      child: Text(
                        _rankLabel(pick.rank),
                        style: TextStyle(
                          color: rankColor,
                          fontSize: 13,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                pick.name,
                                style: const TextStyle(
                                  color: AppColors.textPrimary,
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.accent.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                '${pick.allocation}%',
                                style: const TextStyle(
                                  color: AppColors.accent,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
                                  fontFeatures: [FontFeature.tabularFigures()],
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            Text(
                              pick.symbol,
                              style: const TextStyle(
                                color: AppColors.textTertiary,
                                fontSize: 12,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              Formatters.formatKRW(pick.currentPrice.toInt()),
                              style: const TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                fontFeatures: [FontFeature.tabularFigures()],
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  _ConfidenceBadge(confidence: pick.confidence),
                  const SizedBox(width: 8),
                  AnimatedRotation(
                    turns: _expanded ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: const Icon(
                      Icons.keyboard_arrow_down_rounded,
                      size: 20,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
          ),

          // ── EXPANDED BODY ──
          AnimatedCrossFade(
            firstChild: const SizedBox.shrink(),
            secondChild: _buildExpandedBody(pick, rankColor),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 250),
            sizeCurve: Curves.easeOutCubic,
          ),
        ],
      ),
    );
  }

  Widget _buildExpandedBody(DailyPick pick, Color rankColor) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Position from High ──
          _PositionFromHighBar(positionFromHigh: pick.positionFromHigh),
          const SizedBox(height: 12),

          // ── Price Levels ──
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              children: [
                _PriceLevelRow(
                  label: '매수 구간',
                  value:
                      '${Formatters.formatKRW(pick.entryZone.low.toInt())} ~ ${Formatters.formatKRW(pick.entryZone.high.toInt())}',
                  color: AppColors.accent,
                  icon: Icons.login_rounded,
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  height: 0.5,
                  color: AppColors.border,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '1차 목표',
                  value: Formatters.formatKRW(pick.target1.toInt()),
                  color: AppColors.profit,
                  icon: Icons.flag_outlined,
                  suffix: pick.entryZone.high > 0
                      ? ' (+${(((pick.target1 - pick.entryZone.high) / pick.entryZone.high) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '2차 목표',
                  value: Formatters.formatKRW(pick.target2.toInt()),
                  color: const Color(0xFF00E676),
                  icon: Icons.flag_rounded,
                  suffix: pick.entryZone.high > 0
                      ? ' (+${(((pick.target2 - pick.entryZone.high) / pick.entryZone.high) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  height: 0.5,
                  color: AppColors.border,
                ),
                const SizedBox(height: 8),
                _PriceLevelRow(
                  label: '손절가',
                  value: Formatters.formatKRW(pick.stopLoss.toInt()),
                  color: AppColors.loss,
                  icon: Icons.block_rounded,
                  suffix: pick.entryZone.low > 0
                      ? ' (-${(((pick.entryZone.low - pick.stopLoss) / pick.entryZone.low) * 100).toStringAsFixed(1)}%)'
                      : null,
                ),
              ],
            ),
          ),

          // ── DIVIDER: prices -> reasons ──
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                Expanded(
                  child: Container(height: 0.5, color: AppColors.border),
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 10),
                  child: Text(
                    '분석 근거',
                    style: TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                    ),
                  ),
                ),
                Expanded(
                  child: Container(height: 0.5, color: AppColors.border),
                ),
              ],
            ),
          ),

          _ReasonSection(
            icon: Icons.newspaper_rounded,
            title: '뉴스 분석',
            body: pick.reason.news,
            accentColor: AppColors.accent,
            articles: widget.newsArticles,
          ),
          const SizedBox(height: 10),

          // ── REASON: Supply ──
          _ReasonSection(
            icon: Icons.people_alt_outlined,
            title: '수급 분석',
            body: pick.reason.supply,
            accentColor: AppColors.profit,
          ),
          const SizedBox(height: 10),

          // ── REASON: Chart ──
          _ReasonSection(
            icon: Icons.candlestick_chart_outlined,
            title: '차트 분석',
            body: pick.reason.chart,
            accentColor: AppColors.warning,
          ),

          // ── DIVIDER: reasons -> sell strategy ──
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                Expanded(
                  child: Container(height: 0.5, color: AppColors.border),
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 10),
                  child: Text(
                    '매도 전략',
                    style: TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                    ),
                  ),
                ),
                Expanded(
                  child: Container(height: 0.5, color: AppColors.border),
                ),
              ],
            ),
          ),

          // ── SELL STRATEGY ──
          _StrategyRow(
            icon: Icons.trending_up_rounded,
            color: AppColors.profit,
            condition: '고점 돌파 + 거래대금 유지',
            action: pick.sellStrategy.breakoutHold,
          ),
          const SizedBox(height: 8),
          _StrategyRow(
            icon: Icons.trending_down_rounded,
            color: AppColors.loss,
            condition: '돌파 실패 + 음봉 2개',
            action: pick.sellStrategy.breakoutFail,
          ),
          const SizedBox(height: 8),
          _StrategyRow(
            icon: Icons.volume_down_rounded,
            color: AppColors.warning,
            condition: '거래대금 급감',
            action: pick.sellStrategy.volumeDrop,
          ),
          const SizedBox(height: 8),
          _StrategyRow(
            icon: Icons.hourglass_bottom_rounded,
            color: AppColors.textTertiary,
            condition: '11시까지 횡보',
            action: pick.sellStrategy.sideways,
          ),

          // ── TAGS ──
          if (pick.tags.isNotEmpty) ...[
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              height: 0.5,
              color: AppColors.border,
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: pick.tags.map((tag) => _TagChip(label: tag)).toList(),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Inline Reason Section (colored left border)
// ─────────────────────────────────────────────

class _ReasonSection extends StatelessWidget {
  const _ReasonSection({
    required this.icon,
    required this.title,
    required this.body,
    required this.accentColor,
    this.articles = const [],
  });

  final IconData icon;
  final String title;
  final String body;
  final Color accentColor;
  final List<NewsArticle> articles;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: accentColor.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: accentColor.withValues(alpha: 0.1),
          width: 0.5,
        ),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: 3,
              decoration: BoxDecoration(
                color: accentColor,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(8),
                  bottomLeft: Radius.circular(8),
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(icon, size: 14, color: accentColor),
                        const SizedBox(width: 6),
                        Text(
                          title,
                          style: TextStyle(
                            color: accentColor,
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      body,
                      style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 13,
                        height: 1.7,
                      ),
                    ),
                    if (articles.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Container(
                        width: double.infinity,
                        height: 0.5,
                        color: accentColor.withValues(alpha: 0.15),
                      ),
                      const SizedBox(height: 8),
                      ...articles
                          .take(3)
                          .map(
                            (article) => _NewsLinkRow(
                              article: article,
                              accentColor: accentColor,
                            ),
                          ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NewsLinkRow extends StatelessWidget {
  const _NewsLinkRow({required this.article, required this.accentColor});

  final NewsArticle article;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    final hasUrl = article.url.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: GestureDetector(
        onTap: hasUrl
            ? () => launchUrl(
                Uri.parse(article.url),
                mode: LaunchMode.externalApplication,
              )
            : null,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              hasUrl ? Icons.open_in_new_rounded : Icons.article_outlined,
              size: 12,
              color: hasUrl ? accentColor : AppColors.textTertiary,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    article.title,
                    style: TextStyle(
                      color: hasUrl ? accentColor : AppColors.textTertiary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      height: 1.4,
                      decoration: hasUrl
                          ? TextDecoration.underline
                          : TextDecoration.none,
                      decorationColor: accentColor.withValues(alpha: 0.4),
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (article.source.isNotEmpty)
                    Text(
                      article.source,
                      style: TextStyle(
                        color: AppColors.textTertiary.withValues(alpha: 0.7),
                        fontSize: 10,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Position From High Bar
// ─────────────────────────────────────────────

class _PositionFromHighBar extends StatelessWidget {
  const _PositionFromHighBar({required this.positionFromHigh});

  final double positionFromHigh;

  @override
  Widget build(BuildContext context) {
    // positionFromHigh is a negative % (e.g. -5.2 means 5.2% below high)
    final pct = positionFromHigh.abs().clamp(0.0, 100.0);
    final fillRatio = (100 - pct) / 100;
    final color = pct <= 5
        ? AppColors.profit
        : pct <= 15
        ? AppColors.warning
        : AppColors.loss;

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.trending_down_rounded,
                size: 14,
                color: AppColors.textTertiary,
              ),
              const SizedBox(width: 4),
              const Text(
                '고점 대비 현재 위치',
                style: TextStyle(color: AppColors.textTertiary, fontSize: 11),
              ),
              const Spacer(),
              Text(
                '${positionFromHigh >= 0 ? '+' : ''}${positionFromHigh.toStringAsFixed(1)}%',
                style: TextStyle(
                  color: color,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: SizedBox(
              height: 6,
              child: Stack(
                children: [
                  Container(width: double.infinity, color: AppColors.border),
                  FractionallySizedBox(
                    widthFactor: fillRatio,
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [color.withValues(alpha: 0.5), color],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Reason Card (Tabbed: 뉴스/수급/차트)
// ─────────────────────────────────────────────

class _ReasonCard extends StatefulWidget {
  const _ReasonCard({required this.reason});

  final DailyPickReason reason;

  @override
  State<_ReasonCard> createState() => _ReasonCardState();
}

class _ReasonCardState extends State<_ReasonCard> {
  int _selectedTab = 0;

  static const _tabs = ['뉴스 관점', '수급 관점', '차트 관점'];
  static const _icons = [
    Icons.newspaper_rounded,
    Icons.people_alt_outlined,
    Icons.candlestick_chart_outlined,
  ];

  String get _content {
    switch (_selectedTab) {
      case 0:
        return widget.reason.news;
      case 1:
        return widget.reason.supply;
      case 2:
        return widget.reason.chart;
      default:
        return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Tab row
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
            child: Row(
              children: List.generate(_tabs.length, (i) {
                final selected = i == _selectedTab;
                return Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _selectedTab = i),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      margin: EdgeInsets.only(right: i < 2 ? 6 : 0),
                      decoration: BoxDecoration(
                        color: selected
                            ? AppColors.accent.withValues(alpha: 0.1)
                            : AppColors.surface,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: selected
                              ? AppColors.accent.withValues(alpha: 0.3)
                              : AppColors.border,
                          width: 0.5,
                        ),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            _icons[i],
                            size: 13,
                            color: selected
                                ? AppColors.accent
                                : AppColors.textTertiary,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            _tabs[i],
                            style: TextStyle(
                              color: selected
                                  ? AppColors.accent
                                  : AppColors.textTertiary,
                              fontSize: 11,
                              fontWeight: selected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
          // Content
          Padding(
            padding: const EdgeInsets.all(16),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: Text(
                _content,
                key: ValueKey(_selectedTab),
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 13,
                  height: 1.7,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Sell Strategy Card
// ─────────────────────────────────────────────

class _SellStrategyCard extends StatelessWidget {
  const _SellStrategyCard({required this.strategy});

  final SellStrategy strategy;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.exit_to_app_rounded,
                size: 16,
                color: AppColors.warning,
              ),
              SizedBox(width: 6),
              Text(
                '매도 전략',
                style: TextStyle(
                  color: AppColors.warning,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _StrategyRow(
            icon: Icons.trending_up_rounded,
            color: AppColors.profit,
            condition: '고점 돌파 + 거래대금 유지',
            action: strategy.breakoutHold,
          ),
          const SizedBox(height: 10),
          _StrategyRow(
            icon: Icons.trending_down_rounded,
            color: AppColors.loss,
            condition: '돌파 실패 + 음봉 2개',
            action: strategy.breakoutFail,
          ),
          const SizedBox(height: 10),
          _StrategyRow(
            icon: Icons.volume_down_rounded,
            color: AppColors.warning,
            condition: '거래대금 급감',
            action: strategy.volumeDrop,
          ),
          const SizedBox(height: 10),
          _StrategyRow(
            icon: Icons.hourglass_bottom_rounded,
            color: AppColors.textTertiary,
            condition: '11시까지 횡보',
            action: strategy.sideways,
          ),
        ],
      ),
    );
  }
}

class _StrategyRow extends StatelessWidget {
  const _StrategyRow({
    required this.icon,
    required this.color,
    required this.condition,
    required this.action,
  });

  final IconData icon;
  final Color color;
  final String condition;
  final String action;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(icon, size: 14, color: color),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  condition,
                  style: TextStyle(
                    color: color,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  action,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Risk Analysis Card
// ─────────────────────────────────────────────

class _RiskAnalysisCard extends StatelessWidget {
  const _RiskAnalysisCard({required this.riskAnalysis});

  final RiskAnalysis riskAnalysis;

  @override
  Widget build(BuildContext context) {
    final prob = riskAnalysis.successProbability;
    final probColor = prob >= 60
        ? AppColors.profit
        : prob >= 40
        ? AppColors.warning
        : AppColors.loss;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.security_rounded,
                size: 16,
                color: AppColors.loss,
              ),
              const SizedBox(width: 6),
              const Text(
                '리스크 분석',
                style: TextStyle(
                  color: AppColors.loss,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              // Success probability gauge
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: probColor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: probColor.withValues(alpha: 0.3),
                    width: 0.5,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      '성공 확률 ',
                      style: TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: 11,
                      ),
                    ),
                    Text(
                      '$prob%',
                      style: TextStyle(
                        color: probColor,
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Probability bar
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: SizedBox(
              height: 6,
              child: Stack(
                children: [
                  Container(width: double.infinity, color: AppColors.border),
                  FractionallySizedBox(
                    widthFactor: prob / 100,
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [probColor.withValues(alpha: 0.5), probColor],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            riskAnalysis.failureFactors,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.7,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Market Summary Card
// ─────────────────────────────────────────────

class _MarketSummaryCard extends StatelessWidget {
  const _MarketSummaryCard({required this.summary});

  final String summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.summarize_outlined, size: 16, color: AppColors.accent),
              SizedBox(width: 6),
              Text(
                '시장 요약',
                style: TextStyle(
                  color: AppColors.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            summary,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.7,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────
// Score Gauge
// ─────────────────────────────────────────────

class _ScoreGauge extends StatelessWidget {
  const _ScoreGauge({required this.score, required this.color});

  final int score;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 64,
      height: 64,
      child: CustomPaint(
        painter: _GaugePainter(
          score: score,
          color: color,
          trackColor: AppColors.border,
        ),
      ),
    );
  }
}

class _GaugePainter extends CustomPainter {
  _GaugePainter({
    required this.score,
    required this.color,
    required this.trackColor,
  });

  final int score;
  final Color color;
  final Color trackColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - 4;

    final trackPaint = Paint()
      ..color = trackColor
      ..strokeWidth = 5
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi * 0.75,
      math.pi * 1.5,
      false,
      trackPaint,
    );

    final valuePaint = Paint()
      ..color = color
      ..strokeWidth = 5
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final sweepAngle = (score / 100) * math.pi * 1.5;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi * 0.75,
      sweepAngle,
      false,
      valuePaint,
    );
  }

  @override
  bool shouldRepaint(covariant _GaugePainter oldDelegate) =>
      oldDelegate.score != score || oldDelegate.color != color;
}

// ─────────────────────────────────────────────
// Sub-widgets
// ─────────────────────────────────────────────

class _ConfidenceBadge extends StatelessWidget {
  const _ConfidenceBadge({required this.confidence});

  final double confidence;

  @override
  Widget build(BuildContext context) {
    final color = confidence >= 70
        ? AppColors.profit
        : confidence >= 50
        ? AppColors.warning
        : AppColors.loss;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 0.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.trending_up_rounded, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            '${confidence.toInt()}%',
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

class _PriceLevelRow extends StatelessWidget {
  const _PriceLevelRow({
    required this.label,
    required this.value,
    required this.color,
    required this.icon,
    this.suffix,
  });

  final String label;
  final String value;
  final Color color;
  final IconData icon;
  final String? suffix;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 8),
        Text(
          label,
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
        ),
        const Spacer(),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
        if (suffix != null)
          Text(
            suffix!,
            style: TextStyle(
              color: color.withValues(alpha: 0.7),
              fontSize: 10,
              fontWeight: FontWeight.w600,
            ),
          ),
      ],
    );
  }
}

class _TagChip extends StatelessWidget {
  const _TagChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.accentDim,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        '#$label',
        style: const TextStyle(
          color: AppColors.accent,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _ThemeChip extends StatelessWidget {
  const _ThemeChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.profit.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: AppColors.profit.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: AppColors.profit,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
