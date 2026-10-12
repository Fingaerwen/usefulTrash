// Stand-in for google_web_sign_in.dart on Android, where browser code can't be compiled.
// Never called there: the service only uses these functions when running in a browser.

Map<String, dynamic> _notWeb() =>
    {'status': 'error', 'errorType': 'notWeb', 'message': 'Website sign-in only exists in the browser build'};

Future<Map<String, dynamic>> webGetIdToken(String serverClientId, String hashedNonce) async => _notWeb();

Future<Map<String, dynamic>> webClearSignInState() async => _notWeb();
