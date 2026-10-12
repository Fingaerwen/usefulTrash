import 'package:flet/flet.dart';

import 'secure_store_service.dart';

/// Tells Flet which Dart service handles the Python "SecureStore" control.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "SecureStore":
        return SecureStoreService(control: control);
      default:
        return null;
    }
  }
}
