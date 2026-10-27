"""Phase 0 spike: tests risky parts of the plan on a real phone.
Currently: startup time (check 8), version (check 12), Google sign-in via our own nativeGoogleSignIn
extension (check 2), Supabase read/write (check 3), offline queue + staying signed in with our own
secureStore extension (check 4), Google Drive upload with Google Play services' permission (check 7),
picking a plan file (check 9), scheduled notifications via our own weighInNotify extension (check 5).
Built for the web, the same file is the PC view (check 6)."""

import time

# Measured as early as possible: the moment Python starts running this file.
pythonStartTime = time.monotonic()

import asyncio  # noqa: E402  (imported after the timer on purpose)
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import flet as ft  # noqa: E402
from driveAccess import DriveAccessError, DriveKeeper, tokenFingerprint  # noqa: E402
from googleDriveApi import DriveError, GoogleDriveApi, quoteDriveText  # noqa: E402
from nativeGoogleSignIn import NativeGoogleSignIn  # noqa: E402
from offlineQueue import OfflineQueue  # noqa: E402
from secureStore import SecureStore  # noqa: E402
from sessionKeeper import MemoryStore, SessionKeeper  # noqa: E402
from supabaseApi import SupabaseApi, SupabaseError, makeNoncePair  # noqa: E402
from weighInNotify import WeighInNotify  # noqa: E402

appVersion = "0.1-alpha"


def describePlan(planData: dict) -> str:
    """Returns a one-line summary of a plan: name, cycle days and exercise count."""
    cycle = planData.get("cycle", [])
    exerciseCount = sum(len(day.get("exercises", [])) for day in cycle)
    return f"{planData.get('name', '(no name)')}: {len(cycle)} cycle days, {exerciseCount} exercises"


def loadPublicConfig() -> dict:
    """Reads the public identifiers (Supabase URL + publishable key, Google Web client ID) that
    makePublicConfig.py copied from .env into the app before the build. Empty if the file is missing."""
    try:
        return json.loads(Path(__file__).with_name("publicConfig.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def maskEmail(email: str) -> str:
    """Shows an email as "j•••@gmail.com", so the full address never appears on screen (or in screenshots)."""
    name, _, domain = (email or "").partition("@")
    return f"{name[:1]}•••@{domain}" if domain else "(no email)"


def describeSession(session: dict) -> str:
    """One line about a Supabase session: masked email, start of the user ID, minutes left. Never shows tokens."""
    user = session.get("user") or {}
    minutesLeft = round((session.get("expires_at", 0) - time.time()) / 60)
    return f"{maskEmail(user.get('email', ''))}, user {str(user.get('id', '?'))[:8]}…, access token valid {minutesLeft} more min"


async def googleSignInToSupabase(googleSignIn, supabase, clientId: str, progress) -> dict:
    """Google ID token → Supabase session, used by the phone (check 2) and the PC view (check 6).
    Also proves the replay protection works: the same ID token with a wrong nonce must be refused
    before the right nonce is accepted. Returns {"outcome": "ok", "session": ..., "nonceCheck": ...},
    {"outcome": "cancelled"} or {"outcome": "failed", "detail": ...}. Supabase errors are raised (SupabaseError)."""
    rawNonce, hashedNonce = makeNoncePair()
    answer = await googleSignIn.getIdToken(clientId, hashedNonce)
    status = answer.get("status")
    if status == "cancelled":
        return {"outcome": "cancelled"}
    if status != "ok":
        return {"outcome": "failed", "detail": f"Google: {answer.get('errorType', status)}: {answer.get('message', '')}"}

    # Replay protection check: Supabase must refuse this token with a nonce it wasn't made for.
    progress("⏳ Google OK. Checking that Supabase refuses a wrong nonce…")
    wrongNonce, _ = makeNoncePair()
    try:
        accidentalSession = await supabase.signInWithGoogleIdToken(answer["idToken"], wrongNonce)
    except SupabaseError as err:
        if err.statusCode == 0:
            raise  # a network problem proves nothing about the nonce check
        # Proven below: if the right nonce then works, the nonce was the only difference.
        nonceCheck = f"wrong nonce refused ({err})"
    else:
        try:  # end the session this check should never have produced
            await supabase.signOut(accidentalSession["access_token"])
        except SupabaseError:
            pass  # the warning matters more than this clean-up
        return {"outcome": "failed",
                "detail": "Supabase ACCEPTED a wrong nonce: replay protection is off (check 'Skip nonce checks')"}

    progress("⏳ Signing in to Supabase…")
    session = await supabase.signInWithGoogleIdToken(answer["idToken"], rawNonce)
    return {"outcome": "ok", "session": session, "nonceCheck": nonceCheck}


def buildPcView(page: ft.Page):
    """Check 6: the PC view as a website on GitHub Pages. Signs in with Google's website sign-in (plan 6.1)
    and reads the notes the phone wrote. Online only, and the session lives in this browser tab's memory:
    nothing is stored in the browser, and closing the tab signs you out."""
    page.title = "usefulTrash PC view (Phase 0)"
    page.theme_mode = ft.ThemeMode.SYSTEM
    publicConfig = loadPublicConfig()
    googleSignIn = NativeGoogleSignIn()  # its web half shows Google's button (extension's google_web_sign_in.dart)
    supabase = (
        SupabaseApi(publicConfig["supabaseUrl"], publicConfig["supabasePublishableKey"])
        if publicConfig.get("supabaseUrl") and publicConfig.get("supabasePublishableKey") else None
    )
    keeper = SessionKeeper(supabase, MemoryStore())
    signInText = ft.Text("Not signed in")
    notesText = ft.Text("")

    def show(message: str):
        """Shows the outcome of a sign-in step."""
        signInText.value = message
        page.update()

    async def signIn(e):
        """Google's button → ID token → Supabase session (same steps and replay test as the phone)."""
        if supabase is None or not publicConfig.get("googleWebClientId"):
            show("❌ No public config in this build: run makePublicConfig.py, then rebuild")
            return
        if signInButton.disabled:
            return  # already running (double click)
        signInButton.disabled = True
        show("⏳ Waiting for Google…")
        try:
            result = await googleSignInToSupabase(googleSignIn, supabase, publicConfig["googleWebClientId"], show)
            if result["outcome"] == "cancelled":
                show("Sign-in cancelled")
            elif result["outcome"] != "ok":
                show(f"❌ {result['detail']}")
            else:
                await keeper.save(result["session"])  # MemoryStore: this tab only
                show(f"✅ Signed in: {describeSession(keeper.session)}\n✅ Replay protection: {result['nonceCheck']}\n"
                     "Session kept in this tab's memory only")
        except SupabaseError as err:
            show(f"❌ Supabase: {err}")  # e.g. 422 signup_disabled for an account that isn't yours
        except Exception as err:  # shown instead of crashing. Messages never contain tokens
            show(f"❌ {type(err).__name__}: {err}")
        finally:
            signInButton.disabled = False
            page.update()

    async def readNotes(e):
        """Check 6: reads the same rows the phone wrote (row-level security shows only yours)."""
        if not keeper.isSignedIn():
            notesText.value = "Sign in first"
            page.update()
            return
        try:
            rows = await supabase.selectRows(
                "phase0Notes", {"select": "noteText", "order": "updatedAt.desc", "limit": "10"},
                await keeper.freshAccessToken())
            notesText.value = f"Your notes in Supabase ({len(rows)}):\n" + "\n".join(f"· {row.get('noteText', '')}" for row in rows)
        except SupabaseError as err:
            notesText.value = f"❌ {err}"
        page.update()

    async def signOut(e):
        """Ends the Supabase session, forgets it and stops Google's automatic account choice."""
        messages = []
        if keeper.isSignedIn():
            try:
                await supabase.signOut(await keeper.freshAccessToken())
                messages.append("Supabase session ended")
            except SupabaseError as err:
                messages.append(f"Supabase sign-out failed: {err}")
        await keeper.forget()
        try:
            await googleSignIn.clearSignInState()
        except Exception:
            pass  # nothing to undo if Google's library never loaded
        notesText.value = ""
        show("Signed out. " + "; ".join(messages))

    signInButton = ft.FilledButton("Sign in with Google", icon=ft.Icons.LOGIN, on_click=signIn)
    page.add(
        ft.SafeArea(
            ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("usefulTrash PC view", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Phase 0, check 6 · version {appVersion}"),
                    ft.Divider(),
                    signInButton,
                    ft.OutlinedButton("Show my notes", on_click=readNotes),
                    ft.OutlinedButton("Sign out", on_click=signOut),
                    signInText,
                    notesText,
                ],
            ),
            expand=True,  # gives the column a fixed height, so it can scroll
        )
    )


def main(page: ft.Page):
    """Builds the single test screen (the phone), or the PC view when running as a website."""
    if page.web:
        buildPcView(page)
        return
    page.title = "usefulTrash Phase 0"
    page.theme_mode = ft.ThemeMode.SYSTEM  # dark mode follows the phone (plan G1)

    # Time from Python starting to the first screen being built.
    pythonToScreenSec = time.monotonic() - pythonStartTime

    # Check 2: native Google sign-in → Supabase session (plan AU1c, F8, F9).
    # Check 4 (T1.1): the session is saved encrypted with a phone-locked key and restored when the app starts.
    publicConfig = loadPublicConfig()
    googleSignIn = NativeGoogleSignIn()
    secureStore = SecureStore()
    supabase = (
        SupabaseApi(publicConfig["supabaseUrl"], publicConfig["supabasePublishableKey"])
        if publicConfig.get("supabaseUrl") and publicConfig.get("supabasePublishableKey") else None
    )
    keeper = SessionKeeper(supabase, secureStore)  # the session: in memory, plus an encrypted copy on the phone
    signInResultText = ft.Text("Not signed in")

    def showSignIn(message: str):
        """Shows the outcome of a sign-in test under the buttons."""
        signInResultText.value = message
        page.update()

    async def signInWithGoogle(e):
        """Google account picker → ID token → Supabase session. Also proves the replay protection works:
        the same ID token with a wrong nonce must be refused before the right nonce is accepted."""
        if supabase is None or not publicConfig.get("googleWebClientId"):
            showSignIn("❌ No public config in this build: run makePublicConfig.py, then rebuild")
            return
        if page.platform != ft.PagePlatform.ANDROID:
            showSignIn("Native Google sign-in only works on the phone")
            return
        if signInButton.disabled:
            return  # a sign-in is already running (double tap)
        signInButton.disabled = True  # set before the first await, so a second tap sees it
        showSignIn("⏳ Waiting for Google…")
        try:
            result = await googleSignInToSupabase(googleSignIn, supabase, publicConfig["googleWebClientId"], showSignIn)
            if result["outcome"] == "cancelled":
                showSignIn("Sign-in cancelled")
                return
            if result["outcome"] != "ok":
                showSignIn(f"❌ {result['detail']}")
                return
            nonceCheck = result["nonceCheck"]
            saved = await keeper.save(result["session"])
            savedLine = "✅ Saved encrypted on the phone (T1.1)" if saved else f"⚠️ Not saved: {keeper.lastProblem}"
            showSignIn(f"✅ Signed in: {describeSession(keeper.session)}\n✅ Replay protection: {nonceCheck}\n{savedLine}")
            await refreshCheck4Status()
        except SupabaseError as err:
            showSignIn(f"❌ Supabase: {err}")  # e.g. 422 signup_disabled for an account that isn't yours
        except Exception as err:  # anything else is shown instead of crashing. Messages never contain tokens
            showSignIn(f"❌ {type(err).__name__}: {err}")
        finally:
            signInButton.disabled = False
            page.update()

    async def checkSession(e):
        """Asks Supabase who the current access token belongs to."""
        if not keeper.isSignedIn():
            showSignIn("Not signed in")
            return
        try:
            user = await supabase.getUser(await keeper.freshAccessToken())
            showSignIn(f"✅ Supabase accepts the session: user {str(user.get('id', '?'))[:8]}…\n{describeSession(keeper.session)}")
        except SupabaseError as err:
            showSignIn(f"❌ Session refused: {err}")

    async def signOut(e):
        """Ends the Supabase session, deletes the saved copy and clears Google's account choice."""
        messages = []
        if keeper.isSignedIn() and supabase is not None:
            try:
                await supabase.signOut(await keeper.freshAccessToken())
                messages.append("Supabase session ended")
            except SupabaseError as err:
                messages.append(f"Supabase sign-out failed: {err}")
        await keeper.forget()  # also deletes the encrypted copy on the phone
        messages.append("saved session deleted")
        await refreshCheck4Status()
        if page.platform == ft.PagePlatform.ANDROID:
            try:
                cleared = await googleSignIn.clearSignInState()
                messages.append("Google account choice cleared" if cleared.get("status") == "ok"
                                else f"Google: {cleared.get('message', '')}")
            except Exception as err:  # shown instead of crashing
                messages.append(f"Google: {type(err).__name__}: {err}")
        showSignIn("Signed out. " + "; ".join(messages))

    signInButton = ft.FilledButton("Sign in with Google", icon=ft.Icons.LOGIN, on_click=signInWithGoogle)

    # Check 3: signed-in read/write of a camelCase-column row, with row-level security (plan 11.4c, F6).
    # Table phase0Notes ("id", "userId", "noteText", "updatedAt") comes from spikes/phase0/sql/001_phase0Notes.sql.
    testTable = "phase0Notes"
    dataResultText = ft.Text("Sign in first (check 2), then run this")

    async def runCheck3(e):
        """Saves, reads, edits and deletes one own row, and proves row-level security refuses rows
        for someone else. Every step shows ✅ or ❌. The test row is always deleted again."""
        if not keeper.isSignedIn():
            dataResultText.value = "Sign in first (check 2)"
            page.update()
            return
        if check3Button.disabled:
            return  # already running (double tap)
        check3Button.disabled = True
        accessToken = ""  # fetched inside the try: renewing may fail
        myUserId = keeper.userId()
        strangerId = str(uuid.uuid4())  # a user ID that isn't yours
        lines, outcomes = [], []
        rowId = None

        def report(passed: bool, text: str):
            """Adds one ✅/❌ line and shows the list so far."""
            outcomes.append(passed)
            lines.append(("✅ " if passed else "❌ ") + text)
            dataResultText.value = "\n".join(lines)
            page.update()

        async def expectRefusal(action, label: str):
            """Runs a write that row-level security must refuse. Only code 42501 counts: a different refusal
            (e.g. 23503, the userId foreign key) would mean row-level security let it through."""
            try:
                await action
                report(False, f"{label}: was ACCEPTED")
            except SupabaseError as err:
                report(err.errorCode == "42501", f"{label}: refused ({err.statusCode} {err.errorCode})")

        try:
            dataResultText.value = "⏳ Running…"
            page.update()
            accessToken = await keeper.freshAccessToken()

            # 1. Save one own row. The database fills in id, userId (= whoever is signed in) and updatedAt.
            row = await supabase.insertRow(testTable, {"noteText": f"check 3 test {time.strftime('%H:%M:%S')}"}, accessToken)
            rowId = row.get("id")
            columns = sorted(row)
            report(columns == ["id", "noteText", "updatedAt", "userId"] and row.get("userId") == myUserId,
                   f"save: own row stored, columns {', '.join(columns)} (camelCase kept), owner = you")

            # 2. Read it back.
            rows = await supabase.selectRows(testTable, {"id": f"eq.{rowId}"}, accessToken)
            report(len(rows) == 1 and rows[0].get("noteText") == row.get("noteText"), "read: the row comes back unchanged")

            # 3. Edit it.
            updated = await supabase.updateRows(testTable, {"id": f"eq.{rowId}"}, {"noteText": "edited"}, accessToken)
            report(len(updated) == 1 and updated[0].get("noteText") == "edited", "edit: own row changed")

            # 4. + 5. Row-level security: no rows for someone else, and no giving your row away.
            await expectRefusal(
                supabase.insertRow(testTable, {"noteText": "must be refused", "userId": strangerId}, accessToken),
                "row-level security, save a row for someone else")
            await expectRefusal(
                supabase.updateRows(testTable, {"id": f"eq.{rowId}"}, {"userId": strangerId}, accessToken),
                "row-level security, give your row to someone else")

            # 6. Delete it and check it's gone.
            deleted = await supabase.deleteRows(testTable, {"id": f"eq.{rowId}"}, accessToken)
            remaining = await supabase.selectRows(testTable, {"id": f"eq.{rowId}"}, accessToken)
            report(len(deleted) == 1 and not remaining, "delete: own row removed")
            if not remaining:
                rowId = None  # nothing left to clean up

            # 7. Without a sign-in, the table can't be read at all (table permission, review F6).
            try:
                await supabase.selectRows(testTable, {"limit": "1"}, None)
                report(False, "anonymous read: was ALLOWED")
            except SupabaseError as err:
                report(err.statusCode == 401 and err.errorCode == "42501", f"anonymous read: refused ({err.statusCode} {err.errorCode})")

            lines.append("\n✅ Check 3 passed" if all(outcomes) and len(outcomes) == 7 else "\n❌ Check 3 not passed")
            dataResultText.value = "\n".join(lines)
        except Exception as err:  # shown instead of crashing. Messages never contain tokens
            lines.append(f"❌ stopped: {type(err).__name__}: {err}")
            dataResultText.value = "\n".join(lines)
        finally:
            if rowId is not None:  # a step failed half-way: don't leave the test row behind
                try:
                    await supabase.deleteRows(testTable, {"id": f"eq.{rowId}"}, accessToken)
                    lines.append("(test row deleted)")
                except Exception:
                    lines.append("⚠️ the test row may still exist")
                dataResultText.value = "\n".join(lines)
            check3Button.disabled = False
            page.update()

    check3Button = ft.FilledButton("Run check 3", icon=ft.Icons.STORAGE, on_click=runCheck3)

    # Check 4: offline queue + staying signed in (plan 1 and 2, T1.1). Notes go into a local SQLite queue first
    # and are sent while the app is open and online. Each note's ID is made on the phone, so sending it again
    # can't create a duplicate. The session survives closing the app: it's restored from the encrypted copy.
    queue = OfflineQueue(os.getenv("FLET_APP_STORAGE_DATA") or os.getcwd())
    sessionStatusText = ft.Text("Session: checking…")
    queueStatusText = ft.Text("Queue: checking…")
    check4ResultText = ft.Text("")
    syncLock = asyncio.Lock()
    syncState = {"tries": 0, "lastResult": "not tried yet", "sentTotal": 0}
    testNotePattern = "like.check 4*"  # Data API filter: every note this check created

    def showCheck4(message: str):
        """Shows the outcome of a check 4 button under the buttons."""
        check4ResultText.value = message
        page.update()

    async def refreshCheck4Status():
        """Updates check 4's session and queue lines."""
        if keeper.isSignedIn():
            sessionStatusText.value = f"Session: {describeSession(keeper.session)}; renewed {keeper.renewCount}× this run"
        else:
            sessionStatusText.value = "Session: not signed in" + (f" ({keeper.lastProblem})" if keeper.lastProblem else "")
        queueStatusText.value = (f"Queue: {queue.count()} waiting on the phone · sent {syncState['sentTotal']} this run · "
                                 f"sync try #{syncState['tries']}: {syncState['lastResult']}")
        page.update()

    async def syncNow() -> str:
        """Sends every waiting note in one request, then forgets them on the phone. Safe to repeat."""
        async with syncLock:  # the loop and the button never send at the same time
            notes = queue.pending()
            if not notes:
                return "nothing to send"
            if supabase is None or not keeper.isSignedIn():
                return f"{len(notes)} waiting for sign-in"
            rows = [{"id": note["id"], "noteText": note["noteText"]} for note in notes]
            try:
                await supabase.insertRowsSkippingExisting(testTable, rows, await keeper.freshAccessToken())
            except SupabaseError as err:
                if err.statusCode == 0:
                    return f"offline, {len(notes)} waiting"
                if err.statusCode != 401:
                    raise
                # Access token refused early (e.g. the phone's clock is off): renew once and resend.
                await keeper.renewNow()
                await supabase.insertRowsSkippingExisting(testTable, rows, await keeper.freshAccessToken())
            queue.remove([note["id"] for note in notes])  # only after Supabase confirmed them
            syncState["sentTotal"] += len(notes)
            return f"✅ sent {len(notes)}"

    async def trySync():
        """One sync attempt. The result goes on the queue line."""
        syncState["tries"] += 1
        try:
            syncState["lastResult"] = await syncNow()
        except SupabaseError as err:
            syncState["lastResult"] = f"❌ {err}"
        except Exception as err:  # shown instead of crashing. Messages never contain tokens
            syncState["lastResult"] = f"❌ {type(err).__name__}: {err}"
        await refreshCheck4Status()

    async def syncLoop():
        """While the app is open: every 10 seconds, send whatever is waiting (plan: sync runs while the app is open)."""
        while True:
            try:
                if queue.count():
                    await trySync()
            except Exception as err:  # never let one bad round stop syncing for good
                syncState["lastResult"] = f"❌ {type(err).__name__}: {err}"
            await asyncio.sleep(10)

    async def addTestNote(e):
        """Writes a note on the phone first, then tries to send it straight away."""
        noteId = queue.add(f"check 4 note {time.strftime('%H:%M:%S')}")
        showCheck4(f"Saved on the phone (id {noteId[:8]}…)")
        await trySync()

    async def syncButton(e):
        await trySync()

    async def renewSession(e):
        """Renews the session now: new tokens from Supabase, saved encrypted before they're used."""
        try:
            await keeper.renewNow()
            showCheck4(f"✅ Renewed: new tokens saved encrypted ({keeper.renewCount}× this run)"
                       + (f"\n⚠️ {keeper.lastProblem}" if keeper.lastProblem else ""))
        except SupabaseError as err:
            showCheck4(f"❌ Renewal: {err}" + ("\nSign in again (the saved session was deleted)" if not keeper.isSignedIn() else ""))
        await refreshCheck4Status()

    async def showMyNotes(e):
        """Reads this check's notes back from Supabase."""
        try:
            rows = await supabase.selectRows(
                testTable, {"select": "noteText", "noteText": testNotePattern, "order": "updatedAt.desc"},
                await keeper.freshAccessToken())
            texts = "\n".join(f"· {row.get('noteText', '')}" for row in rows[:6])
            showCheck4(f"In Supabase: {len(rows)} check 4 notes\n{texts}")
        except SupabaseError as err:
            showCheck4(f"❌ {err}")

    async def deleteMyNotes(e):
        """Deletes this check's notes from Supabase (clean-up)."""
        try:
            deleted = await supabase.deleteRows(testTable, {"noteText": testNotePattern}, await keeper.freshAccessToken())
            showCheck4(f"✅ Deleted {len(deleted)} check 4 notes from Supabase")
        except SupabaseError as err:
            showCheck4(f"❌ {err}")

    async def scanAppLog(e):
        """Searches the app's own log file (Flet writes Python's output there) for tokens. Shows counts only."""
        logPath = os.path.join(os.getenv("FLET_APP_STORAGE_CACHE", ""), "console.log")
        try:
            with open(logPath, encoding="utf-8", errors="replace") as logFile:
                logText = logFile.read()
        except OSError:
            showCheck4("App log file: none written (nothing was printed)")
            return
        tokenShaped = len(re.findall(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", logText))
        googleTokens = len(re.findall(r"ya29\.[A-Za-z0-9_-]{20,}", logText))  # Google access tokens (check 7)
        currentTokens = [value for value in (keeper.session.get("access_token"), keeper.session.get("refresh_token"),
                                             driveKeeper.accessToken, firstDriveToken["value"])
                         if value and value in logText]
        clean = not tokenShaped and not googleTokens and not currentTokens
        showCheck4(f"App log file: {len(logText.splitlines())} lines, {tokenShaped} token-shaped strings, "
                   f"{googleTokens} Google access tokens, current tokens found: {len(currentTokens)}" + (" ✅" if clean else " ❌"))

    async def startUp():
        """Restores the saved session (if any), shows where its key lives, then starts the sync loop."""
        if supabase is None:
            sessionStatusText.value = "Session: no public config in this build"
            page.update()
            return
        try:
            restoreResult = await keeper.restore()
            keyInfo = await secureStore.info()
        except Exception as err:  # e.g. the secure store isn't available: show it instead of failing silently
            showCheck4(f"❌ Start-up: {type(err).__name__}: {err}")
            return
        keyLine = f"key in {keyInfo.get('keyLocation')}" if keyInfo.get("keyExists") else "no key yet"
        restoreLines = {
            "restored": "✅ Session restored from the encrypted copy",
            "none": "No saved session: sign in (check 2)",
            "unreadable": "⚠️ Saved session couldn't be decrypted, so it was deleted: sign in again",
            "error": "⚠️ Couldn't read the saved session",
        }
        showCheck4(f"{restoreLines.get(restoreResult, restoreResult)} ({keyLine})")
        if restoreResult == "restored":
            try:
                await keeper.freshAccessToken()  # renews now if the access token is (nearly) expired. Offline is fine
            except SupabaseError:
                pass  # offline or refused: the status line shows it
            if keeper.isSignedIn():  # written after the renewal, so it shows the renewed session's time
                signInResultText.value = f"Restored: {describeSession(keeper.session)}"
        await refreshCheck4Status()
        page.run_task(syncLoop)

    # Check 7: backups to Google Drive (plan F14.1, R2). The permission comes from Google Play services and covers
    # only files this app creates. No secret in the app. Access tokens last about an hour, so the expiry test
    # (step 3) proves a fresh one arrives without any screen once step 1's token has expired.
    drive = GoogleDriveApi()
    driveKeeper = DriveKeeper(googleSignIn)
    driveStatusText = ft.Text("Drive: no access token yet")
    check7ResultText = ft.Text("")
    driveTestFolder = "usefulTrash Phase 0 test"
    check7StatePath = Path(os.getenv("FLET_APP_STORAGE_DATA") or os.getcwd()) / "check7State.json"
    firstDriveToken = {"value": ""}  # step 1's token, memory only: the expiry test checks Drive refuses it later
    expiryWaitSec = 61 * 60  # access tokens last 60 minutes. One more for clock differences

    def loadCheck7State() -> dict:
        """Step 1's token fingerprint and time, kept on the phone so the expiry test survives an app restart.
        Not secret: a fingerprint can't be turned back into the token."""
        try:
            state = json.loads(check7StatePath.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) and "firstFetchedAt" in state else {}
        except (OSError, ValueError):
            return {}

    def driveAccount() -> str:
        """The signed-in account's email, so the Drive permission is for the same Google account (empty = Google asks)."""
        return str((keeper.session.get("user") or {}).get("email", "")) if keeper.isSignedIn() else ""

    def refreshDriveStatus():
        """Updates check 7's status line: current token (fingerprint only) and when the expiry test can run."""
        lines = []
        if driveKeeper.accessToken:
            ageMin = round((time.time() - driveKeeper.fetchedAt) / 60)
            lines.append(f"Drive: token {tokenFingerprint(driveKeeper.accessToken)}, first seen {ageMin} min ago; "
                         f"{driveKeeper.tokenChanges} different tokens this run")
        else:
            lines.append("Drive: no access token yet")
        state = loadCheck7State()
        if state:
            readyAt = time.strftime("%H:%M", time.localtime(state["firstFetchedAt"] + expiryWaitSec))
            lines.append(f"Step 1 token {state.get('firstFingerprint', '?')} from "
                         f"{time.strftime('%H:%M', time.localtime(state['firstFetchedAt']))}: expiry test from {readyAt}")
        driveStatusText.value = "\n".join(lines)
        page.update()

    async def runDriveStep(button, job):
        """Runs one check 7 button's job: one at a time, the outcome shown under the buttons, errors shown
        instead of crashing (Google's and Drive's messages never contain tokens)."""
        if page.platform != ft.PagePlatform.ANDROID:
            check7ResultText.value = "Drive access only works on the phone"
            page.update()
            return
        if button.disabled:
            return  # already running (double tap)
        button.disabled = True  # set before the first await, so a second tap sees it
        check7ResultText.value = "⏳ Working…"
        page.update()
        try:
            check7ResultText.value = await job()
        except DriveAccessError as err:
            check7ResultText.value = "Cancelled" if err.kind == "cancelled" else f"❌ Google Play services: {err}"
        except DriveError as err:
            check7ResultText.value = f"❌ Drive: {err}"  # e.g. 403 accessNotConfigured: the Drive API isn't enabled
        except Exception as err:
            check7ResultText.value = f"❌ {type(err).__name__}: {err}"
        finally:
            button.disabled = False
            refreshDriveStatus()

    async def testFolderId(token: str) -> str:
        """The test folder in Drive, created on first use."""
        folder = await drive.findFolder(driveTestFolder, token)
        if folder is None:
            folder = await drive.createFolder(driveTestFolder, token)
        return folder["id"]

    async def uploadTestFile(token: str) -> dict:
        """Uploads one small text file into the test folder."""
        content = f"usefulTrash check 7 test file\nUploaded {time.strftime('%Y-%m-%d %H:%M:%S')} (phone time)\n"
        return await drive.uploadFile(f"check7 test {time.strftime('%H-%M-%S')}.txt", content.encode("utf-8"),
                                      "text/plain", await testFolderId(token), token)

    def describeUpload(uploaded: dict) -> str:
        retried = f"\n↻ {driveKeeper.lastRetry}" if driveKeeper.lastRetry else ""
        return (f"✅ Uploaded {uploaded.get('name', '?')} ({uploaded.get('size', '?')} bytes) to '{driveTestFolder}' "
                f"with token {tokenFingerprint(driveKeeper.accessToken)}{retried}")

    async def allowDriveJob() -> str:
        """Step 1: Google's permission screen (only files this app creates), unless already allowed."""
        account = driveAccount()
        token = await driveKeeper.getToken(account, interactive=True)
        firstDriveToken["value"] = token
        firstFetchedAt = time.time()
        check7StatePath.write_text(json.dumps({"firstFingerprint": tokenFingerprint(token), "firstFetchedAt": firstFetchedAt}),
                                   encoding="utf-8")
        readyAt = time.strftime("%H:%M", time.localtime(firstFetchedAt + expiryWaitSec))
        return (f"✅ Drive access allowed for {maskEmail(account) if account else 'the account you picked'}: "
                f"token {tokenFingerprint(token)}, kept in memory only\nStep 3 (expiry test) from {readyAt}")

    async def uploadJob() -> str:
        """Step 2: one upload with a token from Google Play services (no screen)."""
        driveKeeper.lastRetry = ""
        return describeUpload(await driveKeeper.run(uploadTestFile, driveAccount()))

    async def expiryTestJob() -> str:
        """Step 3, 61+ minutes after step 1: Drive must refuse step 1's token, Google Play services must hand
        out a new one without any screen, and an upload with it must work (plan R2)."""
        state = loadCheck7State()
        if not state:
            return "Do step 1 first"
        minutesSince = (time.time() - state["firstFetchedAt"]) / 60
        if minutesSince * 60 < expiryWaitSec:
            readyAt = time.strftime("%H:%M", time.localtime(state["firstFetchedAt"] + expiryWaitSec))
            return f"⏳ Only {minutesSince:.0f} min since step 1: try again from {readyAt}"
        lines, outcomes = [], []

        def report(passed: bool, text: str):
            outcomes.append(passed)
            lines.append(("✅ " if passed else "❌ ") + text)

        # A. Drive refuses step 1's token (if it's still in memory: closing the app forgets it).
        oldToken = firstDriveToken["value"]
        if oldToken:
            try:
                await drive.listFiles("trashed = false", oldToken, pageSize=1)
                report(False, f"step 1's token was still ACCEPTED after {minutesSince:.0f} min")
            except DriveError as err:
                report(err.statusCode == 401, f"step 1's token refused after {minutesSince:.0f} min ({err.statusCode} {err.reason})")
        else:
            lines.append("· step 1's token isn't in memory (the app was closed since), so its refusal isn't shown")

        # B. A new token without any screen (interactive=False can't show one).
        token = await driveKeeper.getToken(driveAccount())
        report(tokenFingerprint(token) != state.get("firstFingerprint"),
               f"new token {tokenFingerprint(token)} from Google Play services, no screen shown "
               f"(step 1's was {state.get('firstFingerprint', '?')})")

        # C. The new token works.
        driveKeeper.lastRetry = ""
        lines.append(describeUpload(await driveKeeper.run(uploadTestFile, driveAccount())))
        outcomes.append(True)
        lines.append("\n✅ Check 7 passed: upload works after the 1-hour expiry, with no secret and no screen"
                     if all(outcomes) else "\n❌ Check 7 not passed")
        return "\n".join(lines)

    async def freshTokenJob() -> str:
        """Removes the current token from Google Play services' cache and asks again without a screen: the same
        path the app takes when Drive refuses a token. (The removed token stays valid at Google until it expires.)"""
        oldToken = await driveKeeper.getToken(driveAccount())
        cleared = await googleSignIn.clearDriveToken(oldToken)
        if cleared.get("status") != "ok":
            return f"❌ Clearing the cache: {cleared.get('errorType', '')} {cleared.get('message', '')}"
        newToken = await driveKeeper.getToken(driveAccount())
        return (f"{'✅' if newToken != oldToken else '❌'} Token {tokenFingerprint(oldToken)} → {tokenFingerprint(newToken)} "
                "after clearing the cache, no screen shown")

    async def testFiles(token: str) -> tuple[dict | None, list[dict]]:
        """The test folder and the files in it (Drive only shows ones this app created)."""
        folder = await drive.findFolder(driveTestFolder, token)
        if folder is None:
            return None, []
        return folder, await drive.listFiles(f"{quoteDriveText(folder['id'])} in parents and trashed = false", token)

    async def listJob() -> str:
        folder, files = await driveKeeper.run(testFiles, driveAccount())
        if folder is None:
            return f"No '{driveTestFolder}' folder in Drive yet"
        names = "\n".join(f"· {file.get('name', '?')} ({file.get('size', '?')} bytes)" for file in files[:6])
        return f"In Drive folder '{driveTestFolder}': {len(files)} files\n{names}"

    async def deleteJob() -> str:
        """Clean-up: deletes the test files for good and moves the test folder to Drive's bin."""
        async def deleteAll(token: str) -> int:
            folder, files = await testFiles(token)
            for file in files:
                await drive.deleteFile(file["id"], token)
            if folder is not None:
                await drive.moveToBin(folder["id"], token)  # restorable for 30 days, in case you put something in it
            return len(files)

        deleted = await driveKeeper.run(deleteAll, driveAccount())
        return f"✅ Deleted {deleted} test files; the test folder is in Drive's bin"

    async def allowDrive(e):
        await runDriveStep(allowDriveButton, allowDriveJob)

    async def uploadTest(e):
        await runDriveStep(uploadButton, uploadJob)

    async def expiryTest(e):
        await runDriveStep(expiryTestButton, expiryTestJob)

    async def freshToken(e):
        await runDriveStep(freshTokenButton, freshTokenJob)

    async def listTestFiles(e):
        await runDriveStep(listFilesButton, listJob)

    async def deleteTestFiles(e):
        await runDriveStep(deleteFilesButton, deleteJob)

    allowDriveButton = ft.FilledButton("1. Allow Drive access", icon=ft.Icons.ADD_TO_DRIVE, on_click=allowDrive)
    uploadButton = ft.FilledButton("2. Upload a test file", icon=ft.Icons.UPLOAD_FILE, on_click=uploadTest)
    expiryTestButton = ft.FilledButton("3. Expiry test (61+ min after step 1)", icon=ft.Icons.TIMER, on_click=expiryTest)
    freshTokenButton = ft.OutlinedButton("Get a fresh token now", on_click=freshToken)
    listFilesButton = ft.OutlinedButton("List my test files", on_click=listTestFiles)
    deleteFilesButton = ft.OutlinedButton("Delete my test files", on_click=deleteTestFiles)

    # Check 9: the phone's file picker. Services register themselves with the page in Flet 1.0.
    filePicker = ft.FilePicker()
    pickResultText = ft.Text("No file picked yet")

    async def pickPlanFile(e):
        """Opens the phone's file picker, reads the chosen JSON file and shows a summary."""
        # with_data=True returns the file's bytes. On Android a plain file path isn't always available.
        files = await filePicker.pick_files(
            dialog_title="Pick a plan JSON file",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
            with_data=True,
        )
        if not files:
            pickResultText.value = "Picking cancelled"
        else:
            picked = files[0]
            try:
                planData = json.loads(picked.bytes.decode("utf-8"))
                pickResultText.value = f"✅ Read {picked.name} ({picked.size} bytes)\n{describePlan(planData)}"
            except Exception as err:  # broken file: show the error instead of crashing
                pickResultText.value = f"❌ Could not read {picked.name}: {err}"
        page.update()

    # Check 5: scheduled notifications through our own Android plugin.
    notifier = WeighInNotify()
    notifyResultText = ft.Text("Notifications not tested yet")

    def showResult(message: str):
        """Shows the outcome of a notification test under the buttons."""
        notifyResultText.value = message
        page.update()

    async def allowNotifications(e):
        """Asks Android for notification permission."""
        allowed = await notifier.requestPermission()
        showResult("✅ Notifications allowed" if allowed else "❌ Notifications NOT allowed")

    async def showNow(e):
        """Shows a test notification right away."""
        shown = await notifier.showNow("usefulTrash test", "Notifications work 🎉")
        showResult("✅ Shown now: check the notification shade" if shown else "❌ Not shown: allow notifications first")

    async def scheduleIn60(e):
        """Schedules a test notification 60 seconds from now (close the app to test it fires anyway)."""
        plannedAt = await notifier.scheduleInSeconds(60, "usefulTrash test", "Scheduled 60 s ago: alarms work ⏰")
        showResult(f"⏰ Planned for {plannedAt}: close the app and lock the phone")

    async def scheduleFriday(e):
        """Sets the real weekly weigh-in reminder: Friday 07:00 (plan G9.1 + 16.1a)."""
        nextAt = await notifier.scheduleWeekly(
            5, 7, 0, "Weekly weigh-in", "Same day, morning, after toilet, before food."
        )
        showResult(f"📅 Weekly reminder set. Next: {nextAt}")

    async def showStatus(e):
        """Shows permission, exact-alarm and next-reminder status."""
        showResult(f"Status: {await notifier.getStatus()}")

    page.add(
        ft.SafeArea(
            ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("usefulTrash Phase 0", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Version: {appVersion}"),
                    ft.Text(f"Python start → screen: {pythonToScreenSec:.2f} s"),
                    ft.Divider(),
                    ft.Text("Check 2: Google sign-in", weight=ft.FontWeight.BOLD),
                    signInButton,
                    ft.OutlinedButton("Check session", on_click=checkSession),
                    ft.OutlinedButton("Sign out", on_click=signOut),
                    signInResultText,
                    ft.Divider(),
                    ft.Text("Check 3: Supabase read/write", weight=ft.FontWeight.BOLD),
                    check3Button,
                    dataResultText,
                    ft.Divider(),
                    ft.Text("Check 4: offline queue + staying signed in", weight=ft.FontWeight.BOLD),
                    sessionStatusText,
                    queueStatusText,
                    ft.FilledButton("Add test note", icon=ft.Icons.NOTE_ADD, on_click=addTestNote),
                    ft.OutlinedButton("Sync now", on_click=syncButton),
                    ft.OutlinedButton("Renew session now", on_click=renewSession),
                    ft.OutlinedButton("Show my notes in Supabase", on_click=showMyNotes),
                    ft.OutlinedButton("Delete my test notes", on_click=deleteMyNotes),
                    ft.OutlinedButton("Scan the app's log for tokens", on_click=scanAppLog),
                    check4ResultText,
                    ft.Divider(),
                    ft.Text("Check 7: Google Drive backup", weight=ft.FontWeight.BOLD),
                    driveStatusText,
                    allowDriveButton,
                    uploadButton,
                    expiryTestButton,
                    freshTokenButton,
                    listFilesButton,
                    deleteFilesButton,
                    check7ResultText,
                    ft.Divider(),
                    ft.Text("Check 9: pick a plan file", weight=ft.FontWeight.BOLD),
                    ft.FilledButton("Pick plan file", icon=ft.Icons.FOLDER_OPEN, on_click=pickPlanFile),
                    pickResultText,
                    ft.Divider(),
                    ft.Text("Check 5: notifications", weight=ft.FontWeight.BOLD),
                    ft.FilledButton("1. Allow notifications", on_click=allowNotifications),
                    ft.FilledButton("2. Show one now", on_click=showNow),
                    ft.FilledButton("3. Schedule one in 60 s", on_click=scheduleIn60),
                    ft.FilledButton("4. Set Friday 07:00 reminder", on_click=scheduleFriday),
                    ft.OutlinedButton("Status", on_click=showStatus),
                    notifyResultText,
                ]
            ),
            # expand: the safe area fills the screen, which gives the column a fixed height to scroll in.
            # Without it the column is as tall as its content, gets cut off at the bottom and can't scroll.
            expand=True,
        )
    )
    refreshDriveStatus()  # shows when the check 7 expiry test can run, even after a restart
    page.run_task(startUp)  # restore the saved session and start syncing (check 4)


if __name__ == "__main__":
    ft.run(main)
