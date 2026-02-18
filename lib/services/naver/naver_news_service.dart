import 'package:dio/dio.dart';

class NewsArticle {
  final String title;
  final String url;
  final String source;

  const NewsArticle({required this.title, required this.url, this.source = ''});
}

class NaverNewsService {
  NaverNewsService()
    : _dio = Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5),
        ),
      );

  final Dio _dio;

  Future<List<NewsArticle>> getStockNews(String stockCode) async {
    try {
      final resp = await _dio.get(
        'https://m.stock.naver.com/api/news/stock/$stockCode',
        queryParameters: {'pageSize': 5},
      );

      final data = resp.data;
      if (data is Map<String, dynamic>) {
        final items = data['items'] as List<dynamic>?;
        if (items != null) return _parseItems(items);
      }

      if (data is List<dynamic>) {
        final articles = <NewsArticle>[];
        for (final group in data) {
          if (group is Map<String, dynamic>) {
            final items = group['items'] as List<dynamic>?;
            if (items != null) articles.addAll(_parseItems(items));
          }
        }
        return articles.take(10).toList();
      }

      return [];
    } catch (_) {
      return _getStockNewsAlternative(stockCode);
    }
  }

  List<NewsArticle> _parseItems(List<dynamic> items) {
    final articles = <NewsArticle>[];
    for (final e in items) {
      if (e is! Map<String, dynamic>) continue;
      final title =
          ((e['title'] as String?) ?? (e['titleFull'] as String?) ?? '')
              .replaceAll(RegExp(r'<[^>]*>'), '');
      if (title.isEmpty) continue;

      final officeId = e['officeId'] as String? ?? '';
      final articleId = e['articleId'] as String? ?? '';
      final source = e['officeName'] as String? ?? '';

      final url = officeId.isNotEmpty && articleId.isNotEmpty
          ? 'https://n.news.naver.com/article/$officeId/$articleId'
          : '';

      articles.add(NewsArticle(title: title, url: url, source: source));
    }
    return articles;
  }

  Future<List<NewsArticle>> _getStockNewsAlternative(String stockCode) async {
    try {
      final resp = await _dio.get(
        'https://m.stock.naver.com/api/json/news/stockNews.nhn',
        queryParameters: {'code': stockCode},
      );

      final data = resp.data;
      if (data is Map<String, dynamic>) {
        final result = data['result'] as Map<String, dynamic>?;
        if (result != null) {
          final newsList = result['newsList'] as List<dynamic>?;
          if (newsList != null) {
            return newsList
                .take(5)
                .map((e) {
                  if (e is Map<String, dynamic>) {
                    final title = (e['articleTitle'] as String?) ?? '';
                    if (title.isEmpty) return null;
                    return NewsArticle(title: title, url: '');
                  }
                  return null;
                })
                .whereType<NewsArticle>()
                .toList();
          }
        }
      }

      return [];
    } catch (_) {
      return [];
    }
  }

  void dispose() {
    _dio.close();
  }
}
