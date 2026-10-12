import 'package:flet/flet.dart';

import 'native_google_sign_in_service.dart';

/// Tells Flet which Dart service handles the Python "NativeGoogleSignIn" control.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "NativeGoogleSignIn":
        return NativeGoogleSignInService(control: control);
      default:
        return null;
    }
  }
}
