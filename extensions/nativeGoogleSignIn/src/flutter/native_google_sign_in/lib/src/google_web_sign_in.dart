// Web half of the sign-in extension (PC view, plan 6.1): Google Identity Services, Google's official
// website sign-in. Shows Google's own "Sign in with Google" button in a small box on top of the page and
// returns the ID token, with the same nonce rule as the phone (Google puts the hashed nonce in the token).
// No client secret: Google checks that the page's address is listed under the Web client's
// "Authorized JavaScript origins" in Google Cloud. The token is only handed back to Python, never logged.
import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

// Google Identity Services functions (loaded from accounts.google.com, see _loadGoogleScript).
@JS('google.accounts.id.initialize')
external void _gisInitialize(_IdConfiguration config);

@JS('google.accounts.id.renderButton')
external void _gisRenderButton(web.HTMLElement parent, _ButtonConfiguration options);

@JS('google.accounts.id.cancel')
external void _gisCancel();

@JS('google.accounts.id.disableAutoSelect')
external void _gisDisableAutoSelect();

/// Settings for google.accounts.id.initialize (field names are Google's).
extension type _IdConfiguration._(JSObject _) implements JSObject {
  external factory _IdConfiguration({
    String client_id,
    JSFunction callback,
    String nonce,
    bool auto_select,
    bool cancel_on_tap_outside,
    String ux_mode,
    bool itp_support,
  });
}

/// Settings for Google's button (field names are Google's).
extension type _ButtonConfiguration._(JSObject _) implements JSObject {
  external factory _ButtonConfiguration({String type, String theme, String size, String text, String shape, int width});
}

/// What Google hands to the callback: `credential` is the ID token.
extension type _CredentialResponse._(JSObject _) implements JSObject {
  external String? get credential;
}

Future<void>? _googleScriptLoading;  // loaded once per page

/// Loads Google's sign-in library once. Fails after 20 seconds (e.g. offline or blocked).
Future<void> _loadGoogleScript() {
  final alreadyLoading = _googleScriptLoading;
  if (alreadyLoading != null) return alreadyLoading;

  final loaded = Completer<void>();
  final script = web.HTMLScriptElement()
    ..src = 'https://accounts.google.com/gsi/client'
    ..async = true;
  script.onload = ((web.Event _) {
    if (!loaded.isCompleted) loaded.complete();
  }).toJS;
  script.onerror = ((web.Event _) {
    if (!loaded.isCompleted) loaded.completeError("Google's sign-in script didn't load");
  }).toJS;
  web.document.head!.appendChild(script);

  final loading = loaded.future.timeout(const Duration(seconds: 20));
  _googleScriptLoading = loading;
  loading.catchError((Object _) {
    _googleScriptLoading = null;  // failed: a later sign-in may try loading it again
  });
  return loading;
}

Map<String, dynamic> _failure(String errorType, String message) =>
    {'status': 'error', 'errorType': errorType, 'message': message};

/// Shows Google's button and answers exactly once: {"status": "ok", "idToken": ...}, {"status": "cancelled"}
/// (Cancel button) or {"status": "error", ...}. Same answer shapes as the Android half.
Future<Map<String, dynamic>> webGetIdToken(String serverClientId, String hashedNonce) async {
  if (serverClientId.isEmpty) return _failure('missingClientId', 'No Google Web client ID was given');
  if (hashedNonce.isEmpty) return _failure('missingNonce', "No nonce was given (it's required: replay protection)");
  try {
    await _loadGoogleScript();
  } catch (e) {
    return _failure('scriptLoad', '$e');
  }

  final answer = Completer<Map<String, dynamic>>();
  final overlay = web.HTMLDivElement();

  void finish(Map<String, dynamic> result) {
    if (answer.isCompleted) return;  // only the first answer counts
    overlay.remove();
    answer.complete(result);
  }

  // A dimmed layer over the whole page with a small card: title, Google's button, Cancel.
  overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,0.55);'
      'display:flex;align-items:center;justify-content:center;';
  final card = web.HTMLDivElement()
    ..style.cssText = 'background:#fff;color:#202124;border-radius:12px;padding:24px 28px;display:flex;'
        'flex-direction:column;align-items:center;gap:16px;font:16px sans-serif;min-width:280px;';
  final title = web.HTMLDivElement()..textContent = 'Sign in to usefulTrash';
  final buttonHolder = web.HTMLDivElement();
  final cancel = web.HTMLButtonElement()
    ..textContent = 'Cancel'
    ..style.cssText = 'border:none;background:none;color:#1a73e8;font:15px sans-serif;cursor:pointer;padding:6px 12px;';
  cancel.onclick = ((web.Event _) {
    try {
      _gisCancel();
    } catch (_) {}
    finish({'status': 'cancelled'});
  }).toJS;
  card.appendChild(title);
  card.appendChild(buttonHolder);
  card.appendChild(cancel);
  overlay.appendChild(card);
  web.document.body!.appendChild(overlay);

  try {
    _gisInitialize(_IdConfiguration(
      client_id: serverClientId,
      nonce: hashedNonce,  // goes into the ID token. Supabase gets the raw value and compares
      auto_select: false,
      cancel_on_tap_outside: true,
      ux_mode: 'popup',
      itp_support: true,
      callback: ((_CredentialResponse response) {
        final idToken = response.credential;
        finish(idToken == null || idToken.isEmpty
            ? _failure('noCredential', 'Google returned no ID token')
            : {'status': 'ok', 'idToken': idToken});
      }).toJS,
    ));
    _gisRenderButton(buttonHolder, _ButtonConfiguration(
        type: 'standard', theme: 'outline', size: 'large', text: 'signin_with', shape: 'pill', width: 260));
  } catch (e) {
    finish(_failure('googleLibrary', '$e'));
  }
  return answer.future;
}

/// Sign-out on the web: stop Google from picking the account automatically next time.
Future<Map<String, dynamic>> webClearSignInState() async {
  try {
    if (_googleScriptLoading != null) _gisDisableAutoSelect();
    return {'status': 'ok'};
  } catch (e) {
    return _failure('googleLibrary', '$e');
  }
}
