import 'dart:math' as math;

abstract final class TechnicalIndicators {
  static List<double?> calculateSMA(List<double> prices, int period) {
    if (prices.length < period) {
      return List.filled(prices.length, null);
    }

    final result = List<double?>.filled(prices.length, null);
    double sum = 0;

    for (int i = 0; i < period; i++) {
      sum += prices[i];
    }
    result[period - 1] = sum / period;

    for (int i = period; i < prices.length; i++) {
      sum = sum - prices[i - period] + prices[i];
      result[i] = sum / period;
    }

    return result;
  }

  static List<double?> calculateEMA(List<double> prices, int period) {
    if (prices.length < period) {
      return List.filled(prices.length, null);
    }

    final result = List<double?>.filled(prices.length, null);
    final multiplier = 2.0 / (period + 1);

    double sum = 0;
    for (int i = 0; i < period; i++) {
      sum += prices[i];
    }
    result[period - 1] = sum / period;

    for (int i = period; i < prices.length; i++) {
      result[i] = (prices[i] - result[i - 1]!) * multiplier + result[i - 1]!;
    }

    return result;
  }

  static List<double?> calculateRSI(List<double> prices, {int period = 14}) {
    if (prices.length < period + 1) {
      return List.filled(prices.length, null);
    }

    final result = List<double?>.filled(prices.length, null);
    double avgGain = 0;
    double avgLoss = 0;

    for (int i = 1; i <= period; i++) {
      final change = prices[i] - prices[i - 1];
      if (change > 0) {
        avgGain += change;
      } else {
        avgLoss += change.abs();
      }
    }

    avgGain /= period;
    avgLoss /= period;

    if (avgLoss == 0) {
      result[period] = 100;
    } else {
      final rs = avgGain / avgLoss;
      result[period] = 100 - (100 / (1 + rs));
    }

    for (int i = period + 1; i < prices.length; i++) {
      final change = prices[i] - prices[i - 1];
      final gain = change > 0 ? change : 0.0;
      final loss = change < 0 ? change.abs() : 0.0;

      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;

      if (avgLoss == 0) {
        result[i] = 100;
      } else {
        final rs = avgGain / avgLoss;
        result[i] = 100 - (100 / (1 + rs));
      }
    }

    return result;
  }

  static ({List<double?> macd, List<double?> signal, List<double?> histogram})
      calculateMACD(
    List<double> prices, {
    int fast = 12,
    int slow = 26,
    int signal = 9,
  }) {
    final emaFast = calculateEMA(prices, fast);
    final emaSlow = calculateEMA(prices, slow);

    final macdLine = List<double?>.filled(prices.length, null);
    final macdValues = <double>[];
    final macdIndices = <int>[];

    for (int i = 0; i < prices.length; i++) {
      if (emaFast[i] != null && emaSlow[i] != null) {
        macdLine[i] = emaFast[i]! - emaSlow[i]!;
        macdValues.add(macdLine[i]!);
        macdIndices.add(i);
      }
    }

    final signalLine = List<double?>.filled(prices.length, null);
    final histogramLine = List<double?>.filled(prices.length, null);

    if (macdValues.length >= signal) {
      final emaSignal = calculateEMA(macdValues, signal);
      for (int i = 0; i < emaSignal.length; i++) {
        if (emaSignal[i] != null) {
          final idx = macdIndices[i];
          signalLine[idx] = emaSignal[i];
          histogramLine[idx] = macdLine[idx]! - emaSignal[i]!;
        }
      }
    }

    return (macd: macdLine, signal: signalLine, histogram: histogramLine);
  }

  static ({List<double?> upper, List<double?> middle, List<double?> lower})
      calculateBollingerBands(
    List<double> prices, {
    int period = 20,
    double stdDev = 2,
  }) {
    final middle = calculateSMA(prices, period);
    final upper = List<double?>.filled(prices.length, null);
    final lower = List<double?>.filled(prices.length, null);

    for (int i = period - 1; i < prices.length; i++) {
      if (middle[i] == null) continue;

      double sumSquaredDiff = 0;
      for (int j = i - period + 1; j <= i; j++) {
        final diff = prices[j] - middle[i]!;
        sumSquaredDiff += diff * diff;
      }

      final sd = math.sqrt(sumSquaredDiff / period);
      upper[i] = middle[i]! + (stdDev * sd);
      lower[i] = middle[i]! - (stdDev * sd);
    }

    return (upper: upper, middle: middle, lower: lower);
  }
}
