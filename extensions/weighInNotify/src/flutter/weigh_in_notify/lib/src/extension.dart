import 'package:flet/flet.dart';

import 'weigh_in_notify_service.dart';

/// Tells Flet which Dart service handles the Python "WeighInNotify" control.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "WeighInNotify":
        return WeighInNotifyService(control: control);
      default:
        return null;
    }
  }
}
