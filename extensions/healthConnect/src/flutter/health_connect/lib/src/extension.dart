import 'package:flet/flet.dart';

import 'health_connect_service.dart';

/// Tells Flet which Dart service handles the Python "HealthConnect" control.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "HealthConnect":
        return HealthConnectService(control: control);
      default:
        return null;
    }
  }
}
