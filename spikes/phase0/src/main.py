"""Phase 0 spike: tests risky parts of the plan on a real phone.
Currently: startup time (check 8), version (check 12), Google sign-in via our own nativeGoogleSignIn
extension (check 2), picking a plan file (check 9), scheduled notifications via our own weighInNotify
extension (check 5). More checks (Supabase data, offline queue) get added step by step."""

import time

# Measured as early as possible: the moment Python starts running this file.
pythonStartTime = time.monotonic()

import json  # noqa: E402  (imported after the timer on purpose)
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import flet as ft  # noqa: E402
from nativeGoogleSignIn import NativeGoogleSignIn  # noqa: E402
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


def main(page: ft.Page):
    """Builds the single test screen."""
    page.title = "usefulTrash Phase 0"
    page.theme_mode = ft.ThemeMode.SYSTEM  # dark mode follows the phone (plan G1)

    # Time from Python starting to the first screen being built.
    pythonToScreenSec = time.monotonic() - pythonStartTime

    # Check 2: native Google sign-in → Supabase session (plan AU1c, F8, F9).
    # The session lives in memory only: nothing is saved on the phone yet, and closing the app signs you out.
    # How tokens get stored is decided before check 4.
    publicConfig = loadPublicConfig()
    googleSignIn = NativeGoogleSignIn()
    supabase = (
        SupabaseApi(publicConfig["supabaseUrl"], publicConfig["supabasePublishableKey"])
        if publicConfig.get("supabaseUrl") and publicConfig.get("supabasePublishableKey") else None
    )
    session = {}  # current Supabase session (access_token, refresh_token, expires_at, user); memory only
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
            rawNonce, hashedNonce = makeNoncePair()
            answer = await googleSignIn.getIdToken(publicConfig["googleWebClientId"], hashedNonce)
            status = answer.get("status")
            if status == "cancelled":
                showSignIn("Sign-in cancelled")
                return
            if status != "ok":
                showSignIn(f"❌ Google: {answer.get('errorType', status)}: {answer.get('message', '')}")
                return

            # Replay protection check: Supabase must refuse this token with a nonce it wasn't made for.
            showSignIn("⏳ Google OK. Checking that Supabase refuses a wrong nonce…")
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
                    pass  # the warning below matters more than this clean-up
                showSignIn("❌ Supabase ACCEPTED a wrong nonce: replay protection is off (check 'Skip nonce checks')")
                return

            showSignIn("⏳ Signing in to Supabase…")
            newSession = await supabase.signInWithGoogleIdToken(answer["idToken"], rawNonce)
            session.clear()
            session.update(newSession)
            showSignIn(f"✅ Signed in: {describeSession(session)}\n✅ Replay protection: {nonceCheck}")
        except SupabaseError as err:
            showSignIn(f"❌ Supabase: {err}")  # e.g. 422 signup_disabled for an account that isn't yours
        except Exception as err:  # anything else is shown instead of crashing; messages never contain tokens
            showSignIn(f"❌ {type(err).__name__}: {err}")
        finally:
            signInButton.disabled = False
            page.update()

    async def checkSession(e):
        """Asks Supabase who the current access token belongs to."""
        if not session:
            showSignIn("Not signed in")
            return
        try:
            user = await supabase.getUser(session["access_token"])
            showSignIn(f"✅ Supabase accepts the session: user {str(user.get('id', '?'))[:8]}…\n{describeSession(session)}")
        except SupabaseError as err:
            showSignIn(f"❌ Session refused: {err}")

    async def signOut(e):
        """Ends the Supabase session, forgets it in memory and clears Google's account choice."""
        messages = []
        if session and supabase is not None:
            try:
                await supabase.signOut(session["access_token"])
                messages.append("Supabase session ended")
            except SupabaseError as err:
                messages.append(f"Supabase sign-out failed: {err}")
        session.clear()
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
        for someone else. Every step shows ✅ or ❌; the test row is always deleted again."""
        if not session:
            dataResultText.value = "Sign in first (check 2)"
            page.update()
            return
        if check3Button.disabled:
            return  # already running (double tap)
        check3Button.disabled = True
        accessToken = session["access_token"]
        myUserId = str((session.get("user") or {}).get("id", ""))
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

            # 1. Save one own row; the database fills in id, userId (= whoever is signed in) and updatedAt.
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
        except Exception as err:  # shown instead of crashing; messages never contain tokens
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

    # Check 9: the phone's file picker. Services register themselves with the page in Flet 1.0.
    filePicker = ft.FilePicker()
    pickResultText = ft.Text("No file picked yet")

    async def pickPlanFile(e):
        """Opens the phone's file picker, reads the chosen JSON file and shows a summary."""
        # with_data=True returns the file's bytes; on Android a plain file path isn't always available.
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
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
