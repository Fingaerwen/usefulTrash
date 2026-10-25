import 'package:flet/flet.dart';
import 'package:flutter/services.dart';

/// Receives method calls from Python and forwards them unchanged to the Kotlin plugin.
class BarcodeScanService extends FletService {
  BarcodeScanService({required super.control});

  // Channel name must match BarcodeScanPlugin.kt.
  static const _channel = MethodChannel('io.github.fingaerwen/barcodeScan');

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  /// Passes the call (name + arguments) to Android and returns Android's answer to Python.
  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    return await _channel.invokeMethod(name, args);
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
