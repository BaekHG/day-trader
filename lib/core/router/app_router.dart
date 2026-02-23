import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../screens/chart/chart_screen.dart';
import '../../screens/daily_pick/daily_pick_screen.dart';
import '../../screens/home/home_screen.dart';
import '../../screens/bot_report/bot_report_screen.dart';
import '../../screens/trade/add_trade_screen.dart';
import '../../screens/trade/close_trade_screen.dart';
import '../../screens/trade/trade_screen.dart';
import '../../screens/watchlist/add_watchlist_screen.dart';
import '../../screens/watchlist/watchlist_screen.dart';
import '../../widgets/common/app_bottom_nav.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/home',
    routes: [
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return AppBottomNav(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/watchlist',
                builder: (context, state) => const WatchlistScreen(),
                routes: [
                  GoRoute(
                    path: 'add',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) => const AddWatchlistScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/trade',
                builder: (context, state) => const TradeScreen(),
                routes: [
                  GoRoute(
                    path: 'add',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) => const AddTradeScreen(),
                  ),
                  GoRoute(
                    path: 'close/:tradeId',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) {
                      final tradeId = state.pathParameters['tradeId'] ?? '';
                      return CloseTradeScreen(tradeId: tradeId);
                    },
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/bot-report',
                builder: (context, state) => const BotReportScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/daily-pick',
                builder: (context, state) => const DailyPickScreen(),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        path: '/chart/:symbol',
        builder: (context, state) {
          final symbol = state.pathParameters['symbol'] ?? '';
          return ChartScreen(symbol: symbol);
        },
      ),
    ],
  );
});
