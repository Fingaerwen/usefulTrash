import 'package:flet/flet.dart';

import 'barcode_scan_service.dart';

/// Tells Flet which Dart service handles the Python "BarcodeScan" control.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "BarcodeScan":
        return BarcodeScanService(control: control);
      default:
        return null;
    }
  }
}
