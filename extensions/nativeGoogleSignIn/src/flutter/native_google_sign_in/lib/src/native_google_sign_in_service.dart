import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

// Browser half (Google Identity Services); on Android the stub is compiled instead.
import 'google_web_sign_in_stub.dart' if (dart.library.js_interop) 'google_web_sign_in.dart';

/// Receives method calls from Python. On Android they go unchanged to the Kotlin plugin;
/// in the browser (PC view) they're answered by Google's website sign-in.
/// Nothing is logged here: the answer to "getIdToken" carries the Google ID token.
class NativeGoogleSignInService extends FletService {
  NativeGoogleSignInService({required super.control});

  // Channel name must match NativeGoogleSignInPlugin.kt.
  static const _channel = MethodChannel('io.github.fingaerwen/nativeGoogleSignIn');

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  /// Passes the call (name + arguments) to Android, or to Google's website sign-in in the browser,
  /// and returns the answer to Python.
  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    if (kIsWeb) {
      final arguments = args is Map ? args : const {};
      switch (name) {
        case 'getIdToken':
          return await webGetIdToken(
              '${arguments['serverClientId'] ?? ''}', '${arguments['hashedNonce'] ?? ''}');
        case 'clearSignInState':
          return await webClearSignInState();
        default:
          return {'status': 'error', 'errorType': 'unknownMethod', 'message': 'No method called $name'};
      }
    }
    return await _channel.invokeMethod(name, args);
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
