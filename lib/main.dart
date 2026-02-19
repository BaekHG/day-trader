import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'core/constants/app_constants.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';

String? initError;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await dotenv.load(fileName: '.env');
  } catch (e) {
    initError = '.env 로딩 실패: $e';
  }

  try {
    await Hive.initFlutter();
  } catch (e) {
    initError = (initError ?? '') + '\nHive 초기화 실패: $e';
  }

  try {
    if (AppConstants.supabaseUrl.isNotEmpty) {
      await Supabase.initialize(
        url: AppConstants.supabaseUrl,
        anonKey: AppConstants.supabaseAnonKey,
      );
    }
  } catch (e) {
    initError = (initError ?? '') + '\nSupabase 초기화 실패: $e';
  }

  runApp(const ProviderScope(child: DayTraderApp()));
}

class DayTraderApp extends ConsumerWidget {
  const DayTraderApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'Day Trader',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      routerConfig: router,
    );
  }
}
