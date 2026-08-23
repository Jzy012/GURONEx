# QA Report — RFID / Attendance Module (Production Readiness)

**System:** LINANG / FEMS (PUP-GURONEx) — Django 5.2 + DRF + Daphne on Railway, PostgreSQL, ESP32 RFID reader
**Scope:** End-to-end RFID → device → API → backend → database → attendance record workflow
**Date:** 2026-08-14 · **Branch:** `production` @ `97c3dac`
**Status:** Analysis only — no code or firmware changes were made in producing this report.

### Confirmed constraints (from the requester)

- **Hardware is established. No device changes.** No new components, no board swap, no wiring changes.
- **Firmware: small config-level edits only.** Same architecture, no logic restructuring. Budget ≈ 15 lines, delivered as **one reflash** via the existing OTA path. Architectural firmware work (offline queue, non-blocking loop) is **out of scope**.
- **Lost-scan handling: backend compensating controls.** Since the device cannot buffer scans, losses must be made *visible and correctable* server-side rather than prevented at the device.
- Attendance rule *by design* = one `AttendanceLog` per faculty per day (1st tap IN, 2nd tap OUT, 3rd+ DONE).
- Railway prod env correctly sets `DEBUG=False`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True` (the local `.env` is insecure — local only).
- One device in production, classic ESP32 (UART bridge).

**The good news up front: 7 of the 11 Critical blockers are backend-only** and need the device untouched. Three more are 1–3 line firmware edits. Only one Critical (C-7) cannot be properly fixed within these constraints, and §3 sets out the compensating controls that make it survivable.

### Legend

**Severity:** Critical · High · Medium · Low
**Evidence class:** `[CONFIRMED]` proven directly by code · `[RISK]` depends on runtime/config · `[IMPROVEMENT]` quality/maintainability · `[NEEDS-INFO]` insufficient evidence in the codebase

**Fix location** (given the constraints above):
- 🖥️ **Backend-only** — device untouched
- 🔧 **Firmware, small edit** — fits the config-level budget, bundled into the single reflash
- 🚫 **Firmware restructure — out of scope** — documented, with a backend compensating control instead

---

## 1. Executive Summary

The RFID/attendance module is **functionally complete for the happy path and not safe to deploy to production as-is.** The core loop — tap card → HTTPS POST → look up tag → create or close an `AttendanceLog` → LCD feedback — works, and the decision to timestamp on the **server** (`timezone.now()`, never the device clock) is correct and removes a whole class of clock-drift bugs from the trust model.

Everything around that happy path is unprotected. Three themes:

**1. The attendance API is completely open — and this is entirely fixable in the backend.** `POST /api/log_attendance/` has no authentication, no permission class, no CSRF (anonymous DRF requests skip it), and no rate limit. The firmware sends an `X-Device-Token` header; **no line of backend code anywhere in the repo reads it.** Anyone with the public Railway URL and a card UID can write attendance records — and a second unauthenticated endpoint hands out live card UIDs on request. Four sibling endpoints are likewise unauthenticated, two of them writing to the database. The root cause is a single omission: DRF is installed with **no `REST_FRAMEWORK` configuration**, so the framework default of `AllowAny` governs every API view. One settings block plus a permission class closes the entire cluster without touching the device.

**2. Attendance records can be silently wrong, duplicated, or lost.** There is **no unique constraint** on `AttendanceLog(faculty, date)` despite four code paths assuming exactly one row per day — and one of them (`DTRCalculator.get_log_for_day`) raises an uncaught 500 the first time a duplicate exists, permanently breaking that faculty member's DTR page. Deactivated RFID cards still record attendance because `log_attendance` never checks `is_active`, so the documented revoke action silently does nothing. Both are backend-only fixes.

**3. The device has no recovery path, and this is where the constraints bite.** When the network drops, taps are **silently discarded** — no queue, no retry, and the firmware throws away its own success/failure return value. Properly fixing that means an NVS offline buffer, which is out of scope. Separately, `wifiManager.autoConnect()` has no portal timeout: if the AP is down at boot, the ESP32 blocks inside `setup()` forever, never reaching `loop()`, with RFID and OTA both dead until someone physically attends it. That one *is* a one-line fix and is in the reflash bundle.

Because the device cannot be made reliable within scope, **observability is promoted from a nice-to-have to a production blocker.** A heartbeat, a quiet-device alert, and a daily reconciliation report are the only things standing between a network outage and a silently missing day of attendance. Today there is no `LOGGING` config at all and nothing records that a scan was ever rejected.

**Counts:** 11 Critical · 14 High · 16 Medium · 6 Low.
**By fix location:** 🖥️ 30 backend-only · 🔧 7 small firmware edits · 🚫 3 out-of-scope (compensated) · 6 config/process.
Test coverage of the attendance module is **zero** — `rfid/tests.py` is the unmodified Django stub, and there is no CI.

---

## 2. Production Readiness Assessment

| Dimension | Rating | Basis | Fixable in scope? |
|---|---|---|---|
| Functional correctness (happy path) | 🟡 Adequate | IN/OUT/DONE works; server-side timestamps correct | — |
| API security | 🔴 Not ready | 5 unauthenticated endpoints, 3 of which write; token ignored | ✅ Fully (backend) |
| Attendance data integrity | 🔴 Not ready | No DB constraint; inactive cards accepted | ✅ Fully (backend) |
| Transport security | 🔴 Not ready | `setInsecure()`; OTA unauthenticated | ✅ Fully (2 firmware lines) |
| Device boot reliability | 🔴 Not ready | Permanent captive-portal hang | ✅ Fully (1 firmware line) |
| Scan-loss prevention | 🔴 Not ready | No queue, no retry, result discarded | ❌ **Compensating controls only** |
| Concurrency safety | 🔴 Not ready | Non-atomic `get_or_create`, no constraint | ✅ Fully (backend) |
| Error handling & recovery | 🟠 Weak | LCD message, scan dropped, no server-side trace | 🟡 Partially |
| Observability | 🔴 Absent | No `LOGGING`, no audit trail, no heartbeat | ✅ Fully (backend) |
| Performance & scale | 🟡 Adequate now | ~90 queries per DTR month; unindexed date filters | ✅ Fully (backend) |
| Test coverage | 🔴 Absent | 0 tests for the module; no CI | ✅ Fully |
| Deployment config | 🟡 Adequate | Prod env correct; double-migrate is a latent risk | ✅ Fully |

**Verdict: NOT PRODUCTION READY** — but the gap is closable. Ten blockers plus the mandatory compensating controls, at roughly **3–4 days** of backend work and **one 15-line firmware reflash**.

---

## 3. Critical Production Blockers

---

### C-1 · 🖥️ Security · `log_attendance` has no authentication whatsoever `[CONFIRMED]`

**Evidence** — `rfid/views.py:73-129`:
```python
@api_view(['POST'])
def log_attendance(request):
    uid = request.data.get('uid')
```
`FEMS/settings.py` contains **no `REST_FRAMEWORK` dict** (verified by repo-wide grep), so DRF defaults apply: `DEFAULT_PERMISSION_CLASSES = [AllowAny]`. `SessionAuthentication` enforces CSRF only for session-authenticated requests; an anonymous POST bypasses it entirely. The firmware sends `http.addHeader("X-Device-Token", DEVICE_TOKEN)` — a grep for `DEVICE_TOKEN|X-Device-Token|X_DEVICE_TOKEN` returns **the firmware and zero backend matches**.

**Production impact** — Anyone can `curl -X POST https://linang-production.up.railway.app/api/log_attendance/ -d '{"uid":"4773C366"}'` and create or close an attendance record. Attendance is unusable as an HR/payroll record: a faculty member can record from home, or a third party can close someone's day early. Combined with C-3 (UID disclosure) this needs no insider knowledge.

**Recommended fix — backend only, device untouched.** The firmware *already sends the header*, so this is purely a matter of the backend starting to check it:
1. Add a `REST_FRAMEWORK` block to settings with an authenticated default and throttle rates, so no API view is ever accidentally public again.
2. Write a `HasValidDeviceToken` permission class comparing `request.headers.get("X-Device-Token")` against a stored per-device secret with `hmac.compare_digest` — constant-time, since `==` leaks the token by timing.
3. Store tokens in a new `RFIDDevice` model (see H-13), hashed, not in settings.
4. Apply to `log_attendance`, `rfid_tap_api`, `check_wifi_reset`.

*Note:* the current token `ESP32_LINANG_ATTENDANCE_001` is hard-coded in firmware source. Within the constraints, **keep this value** and treat it as a shared secret — but restrict the deployment to a trusted network and rotate it via the reflash if the source is ever shared publicly. Moving it to NVS is desirable but is a firmware change beyond the config budget.

**Testing** — `curl` with no header → 401; wrong token → 401; correct token → 201. DRF `APITestCase` asserting 401 for anonymous. Confirm the physical device still records **before** removing the old open path.

**Blocker: yes.**

---

### C-2 · 🖥️ Security · `rfid_tap_api` is unauthenticated, CSRF-exempt, and writes to the DB `[CONFIRMED]`

**Evidence** — `rfid/views.py:46-59`:
```python
@csrf_exempt
@require_POST
def rfid_tap_api(request):
    uid = request.POST.get("uid")
    cache.set('last_rfid_uid', uid, timeout=10)
    tag, created = RFIDTag.objects.get_or_create(uid=uid)
```
The cached value is read at `adminhub/views.py:4046` and polled every second by `templates/admin/admin_pair_rfid.html:448-460`.

**Production impact** — (a) **Pairing hijack:** an attacker POSTing their own UID while an admin has the pairing page open gets it auto-filled into the admin's form (`this.rfidUid = data.uid`); if the admin confirms without noticing the substitution, the attacker's card is bound to a real faculty member and generates valid attendance indefinitely. (b) **Unbounded writes:** every POST does `get_or_create`, so arbitrary rows can be inserted without limit.

**Recommended fix** — Same device-token permission as C-1. Validate the UID against `^[0-9A-F]{8,20}$` before touching the DB. Stop auto-creating tags here (see M-4).

**Testing** — Unauthenticated POST → 401, no row created. Verify admin pairing still auto-fills from the real device.

**Blocker: yes.**

---

### C-3 · 🖥️ Security · `rfid_pairing_tap_api` has no `@admin_required` — leaks card UIDs to anyone `[CONFIRMED]`

**Evidence** — `adminhub/views.py:4045-4047`:
```python
def rfid_pairing_tap_api(request):          # <-- no decorator
    uid = cache.get('last_rfid_uid')
    return JsonResponse({"uid": uid if uid else ""})
```
Routed publicly at `adminhub/urls.py:105`. Every other view in that file carries `@admin_required`; this one was missed.

**Production impact** — The credential-disclosure half of C-1. Because the firmware calls `sendPairing()` on **every** attendance tap (H-4), this cache is continuously repopulated with live faculty card UIDs throughout the working day. An unauthenticated attacker polling at 1 Hz harvests the UID of everyone who taps, then replays each to `log_attendance` (C-1).

**Recommended fix** — Add `@admin_required` (a one-line fix that closes the disclosure immediately — do this first). Then remove the underlying cause: gate the cache **write** behind an explicit admin-activated "pairing mode" flag, so UIDs are only buffered while someone is actively pairing. That also neutralises H-4 from the backend side without a firmware change, since the device's redundant pairing calls become harmless no-ops.

**Testing** — Logged-out GET redirects to login; faculty-role GET redirects away; admin GET returns the UID during a pairing session.

**Blocker: yes.**

---

### C-4 · 🖥️ Security · `check_wifi_reset` is unauthenticated **and mutates state on GET** `[CONFIRMED]`

**Evidence** — `rfid/views.py:155-168`:
```python
@require_GET
def check_wifi_reset(request):
    wifi_config = ESP32WiFi.objects.first()
    if wifi_config.reset_wifi:
        wifi_config.reset_wifi = False   # side effect on a GET
        wifi_config.save()
        return JsonResponse({'reset': True})
```

**Production impact** — (a) **Denial of reset:** the flag is consumed by whoever polls first — an attacker, a link scanner, a browser prefetcher, an uptime monitor. The device polls only every 60 s (`apiCheckMs`), so the admin clicks "reset Wi-Fi", the UI reports success, and nothing happens, with no diagnostic. (b) **Remote disruption:** anyone able to set the flag can force the field device to wipe its credentials and reboot into captive-portal mode — which, with C-8 unfixed, strands it until physically attended.

**Recommended fix** — Require the device token. Move the clearing side effect off GET: keep the flag set and clear it only when the device confirms. **Within the firmware constraints** the device cannot POST an acknowledgement, so use the next-best backend-only approach: clear the flag on the *subsequent* poll from an authenticated device (the device having polled once is itself the acknowledgement), and stamp `reset_sent_at` so the admin UI can show "sent, awaiting device" rather than a bare success.

**Testing** — Set `reset_wifi=True`; unauthenticated poll → 401 with the flag unchanged; authenticated poll → `{"reset": true}`; verify the admin UI reflects pending vs. confirmed state.

**Blocker: yes.**

---

### C-5 · 🔧 Security · Firmware disables TLS certificate validation `[CONFIRMED]` — *2-line fix, in the reflash bundle*

**Evidence** — `client.setInsecure()` in `sendAttendance()`, `sendPairing()`, and `checkForResetCommand()`. The code comments acknowledge it: *"For production-grade HTTPS: use setCACert() on WiFiClientSecure instead of setInsecure()."*

**Production impact** — HTTPS gives encryption but **zero authentication of the server**. Anyone controlling DNS or the local network (a rogue AP on the campus SSID, ARP spoofing) can transparently impersonate the Railway host: harvest every UID in cleartext, or return fabricated `{"faculty": "...", "status": "IN"}` responses so the LCD shows success and beeps green while nothing is recorded. With no offline buffer (C-7), the faculty member has no way to know.

**Recommended fix** — Two changes inside the existing structure, no restructuring:
1. Add the ISRG Root X1 root certificate as a PROGMEM constant and replace all three `client.setInsecure()` calls with `client.setCACert(root_ca)`.
2. Add `configTime(...)` in `setup()` after Wi-Fi connects — certificate validation **fails without a valid clock**, so this line is mandatory, not optional.

⚠️ **Operational caveat:** a hard-coded root certificate is a *scheduled outage* if its expiry isn't tracked. Record the CA expiry date in the runbook and diary a reflash well ahead of it. Verify which root Railway's edge currently presents before embedding — do not assume.

**Testing** — Point the device at a self-signed proxy: it must **refuse** and show an error, not succeed. Confirm normal operation against the real host after NTP sync. Test a cold boot with no NTP reachable.

**Blocker: yes.** No backend mitigation exists — the backend cannot make the device validate a certificate.

---

### C-6 · 🔧 Security · OTA update has no password `[CONFIRMED]` — *1-line fix, in the reflash bundle*

**Evidence** — `setupOTA()` calls `setHostname()` and `begin()`, with no `setPassword()` or `setPasswordHash()`. `ArduinoOTA.handle()` runs every `loop()` iteration, so the service is always live and mDNS-discoverable as `ESP32-Attendance`.

**Production impact** — Full remote code execution on the attendance device from any host on the same network segment. An attacker flashes firmware that fabricates attendance, exfiltrates every UID, or bricks the reader. Note the irony: **OTA is also the delivery mechanism for the C-5 and C-8 fixes**, so it must be secured in the same reflash that uses it.

**Recommended fix** — `ArduinoOTA.setPasswordHash("<md5-of-strong-password>")` — the hash form keeps the plaintext out of the binary. Store the password in your password manager; losing it means losing remote update capability. Additionally place the device on an isolated VLAN, which is a network-side control requiring no code change.

**Testing** — `espota.py` without a password → auth failure; with the password → success. Confirm RFID scanning is unaffected.

**Blocker: yes.**

---

### C-7 · 🚫 Data integrity · Attendance is silently lost on any network or server failure `[CONFIRMED]` — *proper fix out of scope; compensating controls mandatory*

**Evidence** — `sendAttendance()` returns `false` on Wi-Fi down, `http.begin()` failure, `httpResponseCode <= 0`, or JSON parse error. In `loop()`:
```cpp
bool attendanceSuccess = sendAttendance(uidString);
sendPairing(uidString);
```
`attendanceSuccess` is **assigned and never read**. No retry, no queue, no NVS/SPIFFS persistence, and no record of the attempt anywhere — device-side or server-side.

**Production impact** — The single largest threat to attendance accuracy. A 30-second Wi-Fi blip or one Railway cold start during the 07:00 class change loses every tap in that window permanently. The faculty member sees "Server unavailable. Contact admin." and has no recourse but a manual entry request. With no logging (H-11) and no heartbeat (H-13), **you cannot currently measure how much attendance you are losing, or even know that you lost any.**

**Why it can't be properly fixed here** — Prevention requires an NVS ring buffer, a drain loop with backoff, a device-side RTC for accurate queued timestamps, and an idempotency key so a retry after a lost *response* doesn't double-record. That is an architectural firmware change, explicitly out of scope.

**Recommended approach — make losses visible and correctable, server-side.** These are not optional niceties; they are the *entire* mitigation, and each is therefore a blocker in its own right:
1. **Device heartbeat** — reuse the existing 60-second reset poll (already in firmware, no change needed) to stamp `last_seen`. Any gap in `last_seen` is a precise, timestamped window during which scans were lost. This turns an invisible failure into a measurable one at zero firmware cost.
2. **Quiet-device alerting** — a Celery beat task (Celery is already configured, `FEMS/settings.py:289-314`) that alerts when the device is silent for >10 minutes during defined working hours.
3. **Daily reconciliation report** — an admin view listing faculty with a scheduled `TeachingAssignment` but no `AttendanceLog`, cross-referenced against device downtime windows, so an admin can distinguish "was absent" from "the reader was down" and correct the latter via the existing manual-entry flow.
4. **Log every rejected/failed request** (H-11) so partial failures while the device *is* online are also captured.
5. **Document the residual risk** — a tap during an outage is lost and requires manual entry. This is a known, signed-off limitation of the current hardware, not a defect to be discovered later during a payroll dispute.

**Testing** — Kill the network for 5 minutes during the morning window; assert the heartbeat gap is recorded, the alert fires, and the reconciliation report flags exactly the affected faculty.

**Blocker: yes** — not the firmware defect, but items 1–3 above. Without them the loss is undetectable.

---

### C-8 · 🔧 Reliability · `wifiManager.autoConnect()` can block the device in `setup()` forever `[CONFIRMED]` — *1-line fix, in the reflash bundle*

**Evidence** — `setup()` calls `wifiManager.autoConnect("FEMS-Attendance-Setup")` with no `setConfigPortalTimeout()` and no `setConnectTimeout()`. WiFiManager's default behavior on connection failure is a **blocking** configuration portal that does not return.

**Production impact** — If the AP is down, renamed, or slow at the moment the device boots — a power cut, scheduled maintenance, a router reboot — the ESP32 sits in captive-portal mode indefinitely. It **never reaches `loop()`**: RFID dead, OTA dead, reset polling dead. It will not recover even after Wi-Fi returns. The LCD shows "Connecting to Wi-Fi..." forever. Recovery requires walking to the device. Given that a power interruption is the single most likely real-world event on a campus, this is the most probable cause of a full lost day.

**Recommended fix** — One line inside the existing structure:
```cpp
wifiManager.setConfigPortalTimeout(180);   // portal gives up after 3 min
wifiManager.autoConnect("FEMS-Attendance-Setup");
```
On timeout `autoConnect` returns instead of blocking, `setup()` completes, and `loop()` runs. Combined with the C-8b line below, the device then retries the saved credentials on its own. If you can accept one more line, add `WiFi.setAutoReconnect(true);` after connecting (see H-12).

**Testing** — Power on with the AP off. Confirm the device exits the portal after 3 minutes, reaches `loop()` (LCD shows the Ready screen), and connects automatically when the AP returns — **with no human intervention.** This is the single most important firmware test in this report.

**Blocker: yes.** No backend mitigation is possible — a device stuck in `setup()` never contacts the server. The heartbeat (C-7) will at least alert you that it happened.

---

### C-9 · 🖥️ Data integrity · No unique constraint on `AttendanceLog(faculty, date)` — duplicates crash the DTR `[CONFIRMED]`

**Evidence** — `rfid/models.py:19-34` has **no `Meta`, no `unique_together`, no `constraints`, no indexes** — confirmed across all 8 migrations in `rfid/migrations/`. Yet four code paths assume one row per faculty per day:
- `rfid/views.py:97` — `AttendanceLog.objects.get_or_create(faculty=..., date=today, ...)`
- `services/dtr_service.py:24-28` — `AttendanceLog.objects.get(faculty=..., date=day)`, catching **only `DoesNotExist`**
- `base/forms.py:1587-1591` and `:1637-1641` — form-level "already exists" checks (TOCTOU: validate, then save, no lock)

`get_or_create` is only atomic when the database can reject the duplicate. Without a constraint, two concurrent requests both `SELECT` (miss) and both `INSERT`.

**Production impact** — A double-tap beating the 2 s firmware cooldown, a manual entry racing a live tap, or any attacker POST creates a second row. The moment it happens, `get_log_for_day` raises **`MultipleObjectsReturned` — an uncaught 500** on both `faculty_teaching_assignment_dtr_view` and the admin `dtr_tab_view`. That faculty member's DTR page is permanently inaccessible until an admin locates and deletes the extra row in the Django admin. DTR export breaks the same way.

**Recommended fix** —
1. **Audit production for existing duplicates and merge them first** — the constraint migration will *fail* on live data if any exist. Merge as earliest `time_in` + latest `time_out`, preserving `is_manual`.
2. Add `Meta: constraints = [UniqueConstraint(fields=["faculty", "date"], name="uniq_attendance_per_faculty_per_day")]` plus indexes on `["faculty", "date"]` and `["date"]`.
3. Wrap `log_attendance` in `transaction.atomic()`; use `select_for_update()` when setting `time_out`, or catch `IntegrityError` and re-read.
4. Make `get_log_for_day` defensive — `filter(...).order_by("time_in").first()` — so a stray duplicate degrades gracefully instead of 500-ing.

**Testing** — 20 concurrent POSTs for one UID → exactly one row, no 500s. Force-insert a duplicate and assert the DTR page still renders. Run the merge migration against a **copy of production data** before applying it for real.

**Blocker: yes.**

---

### C-10 · 🖥️ Data integrity / Security · Deactivated RFID cards still record attendance `[CONFIRMED]`

**Evidence** — `rfid/views.py:80`:
```python
rfid_tag = RFIDTag.objects.get(uid__iexact=uid)   # is_active never checked
```
The admin re-pairing flow (`adminhub/views.py:4012-4014`) deactivates the old card **but leaves `tag.faculty` populated**:
```python
RFIDTag.objects.filter(faculty=faculty_obj, is_active=True)\
    .exclude(uid=rfid_uid).update(is_active=False)
```
`RFIDTagAdmin` exposes `is_active` in both `list_display` and `list_filter`, so an administrator has every reason to believe unticking it revokes the card.

**Production impact** — A lost, stolen, or replaced card keeps generating valid attendance for its original owner **forever**. This is a silent revocation failure: the admin performs the documented revoke, the UI confirms it, and the card still works. Nothing in the logs distinguishes it (H-11).

**Recommended fix** — Filter `is_active=True` in the lookup and return a distinguishable response for a known-but-inactive tag (e.g. `{"error": "Card deactivated. Contact admin.", "code": "CARD_INACTIVE"}`). *The existing firmware already renders this correctly* — it falls into the `containsKey("error")` branch and displays the message — so no firmware change is needed. Add an admin action that deactivates **and** clears `faculty`, plus a `deactivated_at` timestamp for audit.

**Testing** — Pair card A → re-pair the faculty to card B → tap card A: expect rejection, a useful LCD message, and **no** `AttendanceLog` row. Assert in a unit test.

**Blocker: yes.**

---

### C-11 · 🖥️ Security · `pair_rfid_api` — an unauthenticated endpoint that binds cards to faculty `[CONFIRMED]`

**Evidence** — `rfid/views.py:25-44`, routed at `rfid/urls.py:8`:
```python
@csrf_exempt
@require_POST
def pair_rfid_api(request):
    ...
    tag.faculty = faculty
    tag.save()
```
A repo-wide grep confirms **no template and no firmware code calls this endpoint** — unused, but fully routed and reachable.

**Production impact** — Completes a fully remote forgery chain with no physical access: `POST /api/rfid_tap/` creates a tag row (C-2) → `POST /api/pair_rfid/` binds it to a faculty → `POST /api/log_attendance/` records attendance (C-1). The only unknown is the faculty `uuid`, and this endpoint's distinguishable errors (`"RFID not found"` vs `"Faculty not found"` vs `"RFID already paired to {name}"`) form a working enumeration oracle whose success case **returns the faculty member's real name**.

**Recommended fix** — Delete the view and its URL. The `@admin_required` admin flow at `adminhub/views.py:3925` is the real pairing path and already supersedes it. Verify nothing calls it (already confirmed) before removal.

**Testing** — URL 404s after removal; `/admin/pair-rfid/` unaffected.

**Blocker: yes.**

---

## 4. High-Priority Issues

---

### H-1 · 🖥️ Data integrity · Firmware duplicate protection is single-slot — alternating taps defeat it `[CONFIRMED]`

**Evidence** — the firmware tracks exactly one previous card, with `duplicateMs` = 5 minutes:
```cpp
String lastUID = ""; unsigned long lastUIDTime = 0;
if (uidString == lastUID && (millis() - lastUIDTime) < duplicateMs) { ...reject... }
lastUID = uidString; lastUIDTime = millis();
```

**Production impact** — The guard only holds for *consecutive* taps of the same card. In a queue — A taps, B taps, A taps again 40 s later — A's second tap passes because `lastUID` is now B. It hits `log_attendance`, finds `time_out is None`, and **records a time-out at 07:01 for a day ending at 17:00**. All later taps return `DONE`, so the faculty member cannot self-correct at the device. Under the confirmed one-IN/one-OUT rule this is unrecoverable without an admin edit. The backend has **no duplicate guard of its own** — it trusts the device completely.

**Recommended fix — backend, and this fully covers the gap.** Enforce a **minimum dwell time** between IN and OUT: reject an OUT recorded less than N minutes after IN, returning a distinguishable code. Make N an admin-configurable setting (the `AttendanceFeatureSetting` singleton at `adminhub/models.py:173` is the natural home) rather than a constant. Because the backend is authoritative, this is strictly better than patching the device cache — the device is not a trustworthy enforcement point regardless. The existing firmware renders the rejection correctly via its `error` branch, so **no firmware change is required.**

**Testing** — Tap A, tap B, tap A within the dwell window: assert A's log still has `time_out is None` and the LCD shows the rejection. Unit-test the boundary at exactly N.

---

### H-2 · 🖥️ Data integrity · No minimum dwell time — a premature time-out marks the whole day absent `[CONFIRMED]`

**Evidence** — `rfid/views.py:112-114` closes the log on any second tap with no time check. Downstream, `services/dtr_service.py:97-98` returns `'absent'` whenever `actual_out < scheduled_out`.

**Production impact** — A faculty member who steps out to their car and taps on re-entry at 07:06 gets a 6-minute recorded day, and **every assignment that day is marked `absent`** — worse than no record at all, since a missing log at least reads as "no data". Feeds directly into DTR exports used for payroll.

**Recommended fix** — The same backend dwell rule as H-1 (one change resolves both). Consider flagging very short IN/OUT pairs for admin review rather than silently accepting them.

**Testing** — Unit-test `calculate_assignment_status` with a same-morning time-out; assert the dwell rule rejects it before it reaches the DB.

---

### H-3 · 🔧 Reliability · A failed scan locks the card out for 5 minutes with a misleading message `[CONFIRMED]` — *3-line move, in the reflash bundle*

**Evidence** — the firmware commits duplicate state **before** the network call:
```cpp
lastUID = uidString;
lastUIDTime = millis();
lcdShowProcessing();
bool attendanceSuccess = sendAttendance(uidString);   // may fail
```

**Production impact** — When a tap fails (Wi-Fi blip, 502, TLS error), the faculty member's natural immediate retry is rejected by the device's own guard, showing **"Already scanned. Try again later."** — which is false and sends them away believing attendance was recorded. Compounds C-7: the tap is lost *and* the user is told the opposite.

**Recommended fix** — Move the two assignments below the call and guard them, using the return value that is currently discarded:
```cpp
bool attendanceSuccess = sendAttendance(uidString);
if (attendanceSuccess) { lastUID = uidString; lastUIDTime = millis(); }
```
No restructuring — it reorders existing lines and reads a variable that already exists. The 2 s global `cooldownMs` still prevents hammering. **This is the highest value-per-line change in the bundle:** it makes every transient failure user-recoverable by simply tapping again, which is the closest thing to a retry mechanism available within scope, and it meaningfully reduces C-7's real-world impact.

**Testing** — Disconnect Wi-Fi, tap, reconnect, tap the same card immediately: the retry must be accepted.

---

### H-4 · 🖥️🔧 Reliability / Performance · `sendPairing()` fires on every attendance tap `[CONFIRMED]` — *backend-mitigable; 1-line firmware removal preferred*

**Evidence** — `loop()`:
```cpp
bool attendanceSuccess = sendAttendance(uidString);
sendPairing(uidString);      // unconditional, every tap
```

**Production impact** — Three costs. (a) **Latency:** a second full TLS handshake per tap (~1–2 s on an ESP32), doubling the time a person stands at the reader and widening H-5's missed-scan window. (b) **Load:** doubles backend requests and performs a needless `get_or_create` write per tap. (c) **Correctness:** it continuously repopulates `last_rfid_uid`, which is what makes C-3's harvesting attack productive and causes an admin with the pairing page open to see live faculty cards auto-filling their form.

**Recommended fix** — Both, in order:
- **Backend (mandatory, no device impact):** gate the cache write behind admin-activated pairing mode (C-3). The device's calls become harmless no-ops and the security impact disappears immediately, before any reflash.
- **Firmware (in the bundle):** delete the `sendPairing(uidString);` line from `loop()`. One line, no restructuring, and it halves per-tap latency and backend load. Pairing then needs the admin to use the USB reader path already supported by `normalize_uid_from_admin` (`adminhub/views.py:3877`), which handles decimal USB input with byte-order correction.

⚠️ **Confirm before removing:** if your operational pairing procedure relies on tapping the card at the ESP32 reader rather than a USB reader, removing this line changes that workflow. The backend gating alone closes the security hole, so **if in doubt, do the backend change and leave the line in.**

**Testing** — Measure tap-to-LCD latency before/after. Verify the admin pairing workflow you actually use still functions end-to-end.

---

### H-5 · 🚫 Reliability · The main loop blocks for seconds per tap — cards are silently missed `[CONFIRMED]` — *partial mitigation only*

**Evidence** — one tap can block `loop()` for `sendAttendance` (5 s timeout) + 1.5 s `safeDelay` + `sendPairing` (5 s) + 0.5 s ≈ **up to 12 s worst case**. `mfrc522.PICC_IsNewCardPresent()` is not polled at all during that window.

**Production impact** — During a class change, cards presented while a previous tap is in flight are **not detected** — no beep, no LCD, no record. The person sees "Processing..." on screen, assumes it's theirs, and walks away with no attendance. Nothing counts or logs the miss. Worst during exactly the peak the system exists to cover.

**Proper fix is out of scope** — eliminating this needs a non-blocking state machine or a second FreeRTOS task with a scan queue.

**Available mitigation within scope** — reduce the window from ~12 s to ~4 s:
1. Remove `sendPairing` from the tap path (H-4) — removes up to 5 s and one TLS handshake.
2. Reduce `http.setTimeout(5000)` to `3000` in `configureHttpClient()` — one constant. Railway responses are well under this; a request that slow has effectively failed anyway.
3. Optionally trim the post-response `safeDelay(1500)` to ~800 ms — the LCD auto-return already handles readability.

That is roughly a 3× improvement from three edited constants, with no restructuring. **Residual risk remains:** a tap during the remaining ~4 s window is still missed silently. Document it, and cover it operationally — the reconciliation report (C-7) will surface the affected faculty member as "scheduled but no log", which is the only detection available.

**Testing** — Present two cards ~1 s apart against a deliberately slowed backend; quantify the miss rate before and after. Feed the measured window into the operational runbook.

---

### H-6 · 🖥️ Data integrity · Case-inconsistent UID storage can 500 the attendance endpoint `[CONFIRMED]`

**Evidence** — three writers normalize inconsistently:
- `rfid_tap_api` upper-cases — `rfid/views.py:53`
- admin pairing upper-cases — `adminhub/views.py:3918`
- **`log_attendance` does not** — `rfid/views.py:82`: `RFIDTag.objects.create(uid=uid)` stores the raw value

and the reader uses `uid__iexact` (`:80`). `RFIDTag.uid`'s `unique=True` is **case-sensitive** in PostgreSQL, so `'ab12'` and `'AB12'` can coexist.

**Production impact** — Once both cases exist for one physical card, `.get(uid__iexact=...)` raises `MultipleObjectsReturned` — an uncaught **500 on every tap of that card**, unrecoverable from the device. Latent today (the firmware always sends uppercase), but C-1's open endpoint lets any client create the condition deliberately.

**Recommended fix** — Normalize in one place: override `RFIDTag.save()` to force `uid = uid.strip().upper()`; add a data migration normalizing existing rows; switch the lookup from `uid__iexact` to `uid=` for an exact, index-backed match. Wrap in a `MultipleObjectsReturned` guard as a backstop.

**Testing** — Insert `'ab12'` and `'AB12'` directly; assert a clean error, not a 500. Assert the normalizing `save()` prevents the pair from being created via the API.

---

### H-7 · 🖥️ Data integrity · Unbounded `RFIDTag` creation from unauthenticated endpoints `[CONFIRMED]`

**Evidence** — `rfid/views.py:82` (creates a tag as a side effect of returning 404) and `:56` (`get_or_create`). No format validation, no length cap, no rate limit, no cleanup.

**Production impact** — Unlimited row insertion (`uid` is `max_length=255`). Bloats the DB, degrades the admin RFID Tags list, and pollutes the pairing screen with junk an admin must manually distinguish from genuine unpaired cards. On a small Railway Postgres plan, sustained abuse is a real availability risk.

**Recommended fix** — Validate `^[0-9A-F]{8,20}$` before any DB access; stop creating tags in the 404 path; add DRF throttling (M-1); add a management command purging unpaired tags older than N days.

**Testing** — POST a 200-character UID and one with punctuation → 400, no row created.

---

### H-8 · 🖥️ Data integrity · Shifts crossing midnight are split across two records `[CONFIRMED]`

**Evidence** — `rfid/views.py:95`: `today = timezone.localdate()`, keyed directly into `get_or_create`.

**Production impact** — A tap-in at 23:50 and tap-out at 00:10 produce day *N* with `time_in` only (which DTR credits as still-present via `dtr_service.py:100-109`) and day *N+1* with a `time_in` that is really a time-out. Two wrong records from one correct shift.

**Severity depends on your schedule** `[NEEDS-INFO]` — if no `TeachingAssignment` ends after ~22:00 this is theoretical. **Please confirm the latest scheduled `end_time` in production.**

**Recommended fix** (if evening shifts exist) — Define an attendance "business day" boundary (e.g. 04:00) and derive `date` from `(time_now - 4h).date()`, or attach an out-tap to the most recent open log within a bounded window rather than to the calendar date. Make the boundary an admin setting.

**Testing** — Freeze time at 23:50 and 00:10 across the boundary; assert one coherent record.

---

### H-9 · 🖥️ Data integrity · Manual entry and device tap can race into a duplicate `[CONFIRMED]`

**Evidence** — `base/forms.py:1587-1591` checks for an existing log in `clean()`, then the view saves separately (`adminhub/views.py:4114`, `faculty/views.py:622`) — classic TOCTOU, with no `transaction.atomic()`, no `select_for_update()`, and (per C-9) no constraint to catch it.

**Production impact** — An admin creating a manual entry as the faculty member taps produces two rows → the C-9 500 cascade. The paths also disagree semantically: the manual form requires **both** `time_in` and `time_out`, while the device path creates `time_out=None` — so a manual entry cannot represent an in-progress day, which matters because manual entry is your **only** recovery mechanism for C-7 losses.

**Recommended fix** — The C-9 constraint fixes the race structurally; add `IntegrityError` handling in both manual views surfacing "A log already exists for this date" rather than a 500. **Make `time_out` optional on the manual form** — with C-7 unfixable, admins will use this flow to repair same-day losses while the faculty member is still present.

**Testing** — Concurrent manual save + device POST for one faculty/date → one row and a clean user-facing error. Assert a manual entry with `time_out` blank saves and the device can later close it.

---

### H-10 · 🖥️ Data integrity · `AttendanceLog.uid` records only the IN card, never the OUT card `[CONFIRMED]`

**Evidence** — `rfid/views.py:100`: `defaults={'uid': uid, 'time_in': time_now}` — set only on create. The time-out branch (`:112-114`) updates `time_out` alone.

**Production impact** — No audit trail for the tap that closed the day. If a faculty member disputes an early time-out, or two cards are paired to one person, there is no way to determine which card produced which event. With C-10 (inactive cards work), you cannot prove after the fact whether a revoked card was used.

**Recommended fix** — Introduce an append-only `AttendanceScan` table (uid, device, received_at, result, resulting_log) that `AttendanceLog` is derived from. This one change also delivers the audit trail H-11 needs and the loss-detection evidence C-7 depends on — **the highest-leverage single addition in the backend work.**

**Testing** — Tap in with card A and out with card B (both paired to one faculty); assert both UIDs are recoverable.

---

### H-11 · 🖥️ Monitoring · No logging of any kind for the attendance pipeline `[CONFIRMED]`

**Evidence** — `FEMS/settings.py` contains **no `LOGGING` dict** (verified). None of the four RFID views call a logger, emit a metric, or write to `notifications.ActivityLog` — a model that exists and is used elsewhere (`adminhub/views.py:4080` logs an admin toggling a *setting*, but nothing logs an actual attendance event).

**Production impact** — When a faculty member says "I tapped and it didn't record," you have **nothing to check**. No record of rejected UIDs, unpaired cards, inactive cards, duplicates, backend errors, or connectivity. You cannot distinguish "the device was offline" from "the card is broken" from "they didn't tap." **Given C-7 is unfixable, this is the difference between a known correctable gap and an unresolvable dispute** — which is why it is promoted to a production gate item here rather than treated as ordinary observability work.

**Recommended fix** — Add a `LOGGING` config emitting JSON to stdout (Railway captures it). Log every `log_attendance` call at INFO with uid, resolved faculty, outcome, and source IP; rejections at WARNING. Persist events to the `AttendanceScan` table (H-10). Add an admin view for recent rejected scans.

**Testing** — Trigger every rejection branch; confirm a distinguishable log line for each.

---

### H-12 · 🔧 Reliability · No Wi-Fi reconnection strategy after boot `[CONFIRMED]` — *1-line fix, in the reflash bundle*

**Evidence** — each API function checks `WiFi.status() != WL_CONNECTED` and returns. `loop()` contains **no reconnection attempt, no `WiFi.setAutoReconnect(true)`, no watchdog.**

**Production impact** — The ESP32 core's default auto-reconnect usually recovers, but that is an undocumented dependency rather than designed behavior, and it does not cover AP-side changes (channel switch, DHCP exhaustion, credential rotation). When it doesn't recover, the device stays powered and *looks* healthy — LCD showing "Ready to scan" — while every tap fails.

**Recommended fix** — Add `WiFi.setAutoReconnect(true); WiFi.persistent(true);` after the `autoConnect` call — one line, making the reliance explicit rather than incidental. Pairs naturally with C-8's timeout: portal times out → `loop()` runs → auto-reconnect restores the link unattended. A retry/restart state machine and watchdog would be better but exceed the budget; the heartbeat (C-7) covers detection instead.

**Testing** — Power-cycle the AP while the device is idle and mid-scan; confirm automatic recovery within a bounded time.

---

### H-13 · 🖥️ Monitoring · No device liveness signal exists `[CONFIRMED]`

**Evidence** — `ESP32WiFi` (`rfid/models.py:37-42`) has exactly two fields: `device_name` and `reset_wifi`. No `last_seen`, no IP, no firmware version, no scan counter. Nothing writes a heartbeat.

**Production impact** — If the reader loses power, hangs (C-8), or loses Wi-Fi (H-12) at 07:00, **nobody finds out until faculty complain** — potentially a full day of lost attendance across everyone who tapped. No dashboard signal, no alert, and no way to answer "was the device up on the 12th?" during a later dispute.

**Recommended fix — backend-only, and the firmware already does its half.** The device polls `/api/check_reset/` every 60 seconds today. Extend `ESP32WiFi` into a proper `RFIDDevice` (device_id, token hash, last_seen, last_ip, firmware_version, scan_count) — the same model C-1 and C-4 need — and stamp `last_seen` on every authenticated poll. **Zero firmware change: the heartbeat already exists, the backend simply isn't recording it.** Then:
- Surface "last seen" on the admin dashboard beside the existing "Attendance Today" KPI (`FEMS/admin_dashboard.py:76-83`).
- Add a Celery beat task (Celery is already configured) alerting when the device is silent >10 min during working hours.

This is the cheapest high-value item in the entire report and the backbone of C-7's mitigation.

**Testing** — Unplug the device; assert `last_seen` goes stale, the dashboard reflects it, and the alert fires.

---

### H-14 · 🖥️ Backend · Response contract is implicit and brittle `[CONFIRMED]`

**Evidence** — the firmware dispatches on key *presence* in order: `containsKey("faculty")` → `containsKey("error")` → `containsKey("message")`, then on `status == "IN"/"OUT"/"DONE"` plus a second presence check. But every backend success response includes **both** `faculty` and `message` (`rfid/views.py:106-129`) — so the *ordering*, not the semantics, is what makes it work.

**Production impact** — Undocumented, unversioned coupling. Adding `faculty` to an error payload (natural: "already paired to X") makes the device report a success with a green beep. Renaming `time_in` drops the tap into the generic `else` branch showing "Contact admin" despite a correctly written record. A backend change can silently corrupt what the person at the reader is told — and **the firmware is not redeployed alongside the backend**, which under a no-firmware-change policy makes this a permanent constraint rather than a temporary one.

**Recommended fix — treat the current contract as frozen and document it.** Since the device cannot be updated freely, the backend must hold the existing shape as a compatibility contract:
1. **Write the contract down** in `docs/` from the firmware's actual parsing order — the single most valuable artifact for preventing a future regression here.
2. Add contract tests asserting the exact response shape of every branch, so a refactor cannot silently change it.
3. For new states (inactive card C-10, dwell rejection H-1), reuse the **existing** `error` key — already rendered correctly by the current firmware — rather than inventing keys the device cannot parse.
4. Keep `faculty` strictly absent from error payloads. This is now a hard rule, not a style preference.

**Testing** — Contract tests per branch, plus a manual device check of each new response type against the real LCD before release.

---

## 5. Medium / Low-Priority Improvements

### Medium

**M-1 · 🖥️ Security · No rate limiting anywhere** `[CONFIRMED]` — no DRF throttle classes, no limiting middleware. *Fix:* `DEFAULT_THROTTLE_CLASSES` with a scoped device rate (e.g. `60/min`), which also caps H-7.

**M-2 · 🖥️ Backend · The firmware ignores HTTP status codes** `[CONFIRMED]` — `sendAttendance` only tests `httpResponseCode <= 0`; a 500 falls through to `deserializeJson` and surfaces as "Response error. Contact admin." Real rejections (404, 400) work only because their bodies happen to contain `error`. *Fix (backend, since the firmware is frozen):* always return a parseable JSON body with an `error` key on **every** error path, including 500s — add a DRF exception handler so an unhandled exception still produces device-parseable JSON rather than an HTML page.

**M-3 · 🖥️ Reliability · No response-size guard on the device** `[CONFIRMED]` — `http.getString()` reads the whole body into a `String` and `DynamicJsonDocument doc(1024)` is fixed. A Railway 502 HTML page overflows the document and pressures heap on a device that never reboots. *Fix (backend):* keep responses small and always JSON (see M-2). Prod `DEBUG=False` already prevents the worst case — a full Django traceback — so **do not let `DEBUG=True` reach production**, as it would turn every error into a device-side memory event.

**M-4 · 🖥️ Design · Tag auto-creation conflates "seen" with "registered"** `[CONFIRMED]` — `rfid/views.py:82` creates a tag while returning 404. Pairing should be an explicit admin act. *Fix:* return the error without the write; buffer unknown UIDs in a short-lived "recently seen" list for the pairing screen.

**M-5 · 🖥️ Backend · Single global reset row with no device identity** `[CONFIRMED]` — `ESP32WiFi.objects.first()` returns the lowest-pk row. Adequate for one device, but no device identity exists in the schema. Rolled into the `RFIDDevice` model (H-13).

**M-6 · 🖥️ Performance · Cache backend makes pairing single-process-only** `[CONFIRMED]` — `CACHES` uses `LocMemCache` (`FEMS/settings.py:145-150`), which is per-process. `rfid_tap_api` writes `last_rfid_uid` in one process; the admin poll reads from whichever process serves that GET. On one Daphne process this works; add a replica and **pairing silently breaks ~50% of the time with no error.** *Fix:* store the pairing handoff in a short-lived DB row instead. Until then, **document the single-replica requirement in the deploy runbook** — this will bite silently during a future scale-up.

**M-7 · 🖥️ Performance · `attendance_logs_view` runs two COUNT queries and cannot use an index** `[CONFIRMED]` — `adminhub/views.py:3848` and `:3869`. Worse, `filter(date__month=..., date__year=...)` wraps the column in `EXTRACT`, so **no index on `date` can ever be used**. *Fix:* filter by date range (`date__gte`/`date__lt`), use `paginator.count`, add the C-9 indexes.

**M-8 · 🖥️ Performance · DTR views issue ~90 queries per month rendered** `[CONFIRMED]` — `services/dtr_service.py:120-123` (2/day) plus `adminhub/views.py:4795-4799` (1/day). *Fix:* fetch the month's assignments and logs in two queries and group in Python.

**M-9 · 🖥️ Performance · `manual_attendance_log_view` loads every RFID tag into memory** `[CONFIRMED]` — `adminhub/views.py:4064` filters `if tag.faculty_id` in Python over an unfiltered queryset. *Fix:* `.exclude(faculty=None)` — the pattern already used correctly at `:3928`.

**M-10 · 🖥️ Code quality · Dead and duplicated code in `rfid/views.py`** `[CONFIRMED]` — two near-identical import blocks (lines 10-22, 137-149); unused imports (`datetime`, `time`, `calendar`, `render`, `redirect`, `HttpResponse`, `parse_datetime`, `json`, `now`); and `from rfid.models import FacultyProfile` (`:145`), which resolves only because `rfid/models.py` happens to re-export it — a rename in `faculty.models` breaks it non-obviously. *Fix:* consolidate imports; import `FacultyProfile` from `faculty.models`.

**M-11 · 🖥️ Code quality · `AttendanceStatusService` is dead code that disagrees with `DTRCalculator`** `[CONFIRMED]` — repo-wide grep finds **no importer**. It also contains two real bugs: `attendance_log.time_in.time()` (`:19`, `:45`) reads a UTC-stored datetime **without `timezone.localtime()`** — an 8-hour error versus the correct handling at `dtr_service.py:66` — and `:45` will `AttributeError` on any log with `time_in=None`. *Fix:* delete `services/attendance_status_service.py`. Two divergent status calculators is a correctness trap. **Confirm it's abandoned before I remove it.**

**M-12 · ⚙️ Deployment · Migrations run twice per deploy** `[CONFIRMED]` — `nixpacks.toml` runs `migrate` in `[phases.build]` **and** `[start]`; `Procfile` runs it again. Harmless today (single replica, idempotent), but concurrent `migrate` across replicas can deadlock — and the C-9 constraint migration is exactly the kind that fails loudly here. *Fix:* run migrations in a single release step, not in the web process start command. **Do this before the C-9 migration.**

**M-13 · ⚙️ Security · Missing hardening headers** `[CONFIRMED]` — `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`, `SECURE_REFERRER_POLICY`, `SECURE_CONTENT_TYPE_NOSNIFF` unset. `SECURE_PROXY_SSL_HEADER` and cookie flags are correct. *Fix:* add HSTS (low `max-age` first, then raise) and run `manage.py check --deploy` in CI.

**M-14 · 🖥️ Operations · No health-check endpoint** `[CONFIRMED]` — nothing for Railway or an uptime monitor to probe. *Fix:* `/healthz/` returning app + DB status. Pairs with H-13's device heartbeat to give a complete liveness picture.

**M-15 · 🔧 Firmware · `safeDelay()` breaks on `millis()` overflow** `[CONFIRMED]` — `unsigned long endTime = millis() + ms; while (millis() < endTime)` fails when the sum wraps past 2³² (~49.7 days uptime), returning immediately once. Every other timer in the firmware correctly uses the wrap-safe `now - start < interval` form. *Fix (2 lines, optional in the bundle):* `unsigned long start = millis(); while (millis() - start < ms)`. Low impact — one shortened delay — but **a device that is never rebooted will reach 49.7 days**, and it's nearly free to include while the firmware is already open.

**M-16 · 🖥️ Firmware/UX · LCD messages truncate silently** `[CONFIRMED]` — `errorMsg.substring(0, 20)` on `"UID not registered. Please pair this UID in the admin."` displays `"UID not registered. "`, cutting the actionable half. *Fix (backend, since the firmware is frozen):* keep every device-facing `error` string **≤20 characters** — e.g. `"Card not registered"`, `"Card deactivated"`, `"Too soon - wait"`. This is a backend copy change that costs nothing and is the only way to improve device UX without a reflash. Add it to the frozen contract doc (H-14).

### Low

**L-1 · 🖥️ `format_log` double-converts timezones** `[CONFIRMED]` — `rfid/views.py:63-64`: `timezone.localtime(x).astimezone(pytz.timezone('Asia/Manila'))`. Harmless (TIME_ZONE is already Asia/Manila) but mixes `pytz` with Django 5's `zoneinfo`. *Fix:* drop the `astimezone` and the `pytz` import.

**L-2 · 🖥️ Manual-entry timezone construction is fragile** `[CONFIRMED, currently correct]` — `datetime.combine(date, time, tzinfo=timezone.get_current_timezone())` (`adminhub/views.py:4110-4111`, `faculty/views.py:618-619`) is correct under Django 5's `zoneinfo`, but would yield an LMT offset (+08:04) if a `pytz` zone were ever injected. *Fix:* use `timezone.make_aware(...)`.

**L-3 · 🔧 `while (!Serial) {;}` in `setup()`** `[CONFIRMED — not a blocker for your board]` — a no-op on the classic ESP32's UART bridge. It becomes a permanent boot hang on an ESP32-S3/C3 with native USB. Given hardware is fixed, **no action needed** — noted only so a future board swap doesn't brick the unit.

**L-4 · ⚙️ `DynamicJsonDocument` is deprecated** `[CONFIRMED]` — removed in ArduinoJson 7. No `platformio.ini` or library manifest was provided, so **the firmware build is not currently reproducible**. *Fix:* before making the reflash edits, capture the exact library versions and board settings into a committed `platformio.ini`. Under a no-firmware-change policy, being unable to rebuild the current binary is itself an operational risk — if the device fails you cannot reproduce its firmware.

**L-5 · 🖥️ Admin pairing page polls at 1 Hz with no backoff** `[CONFIRMED]` — `templates/admin/admin_pair_rfid.html:448`; on error it sets a message but keeps polling forever. *Fix:* exponential backoff, stop after N consecutive errors.

**L-6 · 🖥️ `check_wifi_reset` returns 404 when unconfigured** `[CONFIRMED]` — the firmware parses the body, finds no `reset` key, and `doc["reset"]` yields `false`, so a misconfigured backend is indistinguishable from a healthy one on the device. Benign, but it hides a real misconfiguration.

---

## 6. RFID Device / Firmware Findings

| Area | Assessment | Disposition under constraints |
|---|---|---|
| Card detection & UID handling | ✅ Correct — zero-padded hex, uppercased | No change |
| Scan cooldown | 🟠 2 s global works; per-UID guard single-slot (H-1) | 🖥️ Backend dwell rule covers it |
| Duplicate protection | 🔴 Defeated by alternating taps; commits before send | 🖥️ H-1 backend · 🔧 H-3 3-line move |
| Attendance API request | 🟠 Well-formed; no retry, result discarded (C-7) | 🚫 Compensating controls |
| Pairing API | 🔴 Fires every tap (H-4) | 🖥️ Backend gating · 🔧 optional 1-line removal |
| Device authentication | 🔴 Token sent, never validated | 🖥️ **Backend-only — firmware already sends it** |
| HTTPS / TLS | 🔴 `setInsecure()` (C-5) | 🔧 2 lines — **in bundle** |
| Wi-Fi failure handling | 🔴 Boot hang (C-8); no reconnect (H-12) | 🔧 2 lines — **in bundle** |
| API timeout / error handling | 🟠 5 s timeout; status codes ignored | 🔧 constant · 🖥️ always-JSON errors |
| Server response handling | 🟠 Works via implicit key-ordering (H-14) | 🖥️ Freeze + document the contract |
| Device recovery | 🔴 No watchdog, no restart, no buffer | 🚫 Heartbeat + alerting instead |
| OTA | 🔴 No password (C-6) | 🔧 1 line — **in bundle** |
| LCD / user feedback | 🟠 Good screens; silent truncation; false "Already scanned" | 🖥️ ≤20-char strings · 🔧 H-3 |
| Startup behavior | 🟠 Correct order; `while(!Serial)` latent | No action (board is fixed) |
| Reset / configuration | 🟠 Works; GET side effect, no ack (C-4) | 🖥️ Backend-only |
| Race conditions / missed scans | 🔴 Loop blocks up to ~12 s (H-5) | 🔧 Reduce to ~4 s; residual risk accepted |

### The complete reflash bundle (~15 lines, one OTA deployment)

| # | Change | Lines | Finding |
|---|---|---|---|
| 1 | `setCACert(root_ca)` ×3 + PROGMEM cert + `configTime()` | ~6 | C-5 |
| 2 | `ArduinoOTA.setPasswordHash(...)` | 1 | C-6 |
| 3 | `wifiManager.setConfigPortalTimeout(180)` | 1 | C-8 |
| 4 | `WiFi.setAutoReconnect(true); WiFi.persistent(true);` | 2 | H-12 |
| 5 | Move `lastUID` commit after a successful send | 3 | H-3 |
| 6 | Delete `sendPairing(uidString);` from `loop()` *(confirm workflow first)* | 1 | H-4 |
| 7 | `setTimeout(5000)` → `3000` | 1 | H-5 |
| 8 | *(optional)* wrap-safe `safeDelay` | 2 | M-15 |

**Sequencing note:** flash **items 2 and 3 first, verified on the bench**, before relying on OTA for anything else — C-6 secures the update channel and C-8 guarantees the device can still boot if the reflash leaves it unable to reach Wi-Fi. Keep a USB cable and the current binary available as rollback. Capture `platformio.ini` (L-4) before starting, since you currently cannot reproduce the running firmware.

### Firmware ↔ backend assumptions that could fail in production

1. The device assumes `X-Device-Token` does something. It does not (C-1) — **backend-fixable, firmware already compliant.**
2. The device branches on JSON key *presence* in a fixed order; the backend guarantees no such contract (H-14). Under a frozen-firmware policy this becomes a permanent compatibility constraint.
3. The device assumes a failed send means "not recorded." A lost *response* to a *successful* write is indistinguishable — which is precisely why H-3's retry-on-failure is safe only while there is no automatic retry.
4. The device assumes uppercase-hex UIDs are canonical. `log_attendance` stores whatever it is given (H-6).
5. The device assumes deactivating a card revokes it. It does not (C-10).
6. The device's 5-minute duplicate window is the **only** duplicate protection in the entire system today (H-1).

---

## 7. Backend / API Findings

| Endpoint | Auth | CSRF | Writes | Findings |
|---|---|---|---|---|
| `POST /api/log_attendance/` | ❌ none | ❌ bypassed | ✅ AttendanceLog, RFIDTag | C-1, C-9, C-10, H-6, H-7, H-8, H-10 |
| `POST /api/rfid_tap/` | ❌ none | ❌ exempt | ✅ RFIDTag, cache | C-2, H-7 |
| `POST /api/pair_rfid/` | ❌ none | ❌ exempt | ✅ RFIDTag.faculty | C-11 |
| `GET /api/check_reset/` | ❌ none | n/a | ✅ ESP32WiFi (on GET) | C-4, M-5, L-6 |
| `GET /api/rfid_pairing_tap/` | ❌ none | n/a | ❌ | C-3 |
| `/admin/pair-rfid/` | ✅ admin | ✅ | ✅ | C-10 (leaves `faculty` set on deactivate) |
| `/admin/attendance-logs/manual-log/` | ✅ admin | ✅ | ✅ | H-9, M-9 |
| `POST /admin/faculty/<uuid>/dtr/` | ✅ admin | ✅ | ✅ edit/delete | C-9 (500 on duplicate), M-8 |

`@admin_required` (`base/decorators.py`) correctly checks authentication and role and is applied consistently across `adminhub/views.py` — **with the single exception of C-3**. `TwoFAMiddleware` correctly passes device requests through (no session → no `pre_2fa_user_id`). Confirmed prod settings are correct.

**Root cause of the security cluster:** DRF is installed with **no `REST_FRAMEWORK` configuration**, so `AllowAny` governs. One settings block closes the default-open posture for every current and future API view — the highest-leverage fix in this report, and it requires nothing from the device.

---

## 8. Database & Attendance Data Integrity Findings

**Schema gaps** — `AttendanceLog` has no `Meta` at all (`rfid/models.py:19-34`), confirmed across all 8 migrations:

| Missing | Consequence |
|---|---|
| `UniqueConstraint(faculty, date)` | **C-9** — non-atomic `get_or_create`, duplicates, 500 on DTR |
| Index on `(faculty, date)` | **M-8** — sequential scans on per-day DTR lookups |
| Index on `date` | **M-7** — admin list degrades (and `date__month` defeats it anyway) |
| `CheckConstraint(time_out > time_in)` | Nothing at DB level prevents an inverted record |
| Audit fields (`created_at`, `device`, `source`) | **H-10**, **H-11** — no forensic trail |

`RFIDTag.uid` is `unique=True` but **case-sensitive**, which is what enables H-6.

**Ways the system can currently produce a wrong record:**

| # | Mechanism | Result | Finding | Fixable in scope? |
|---|---|---|---|---|
| 1 | Concurrent taps / manual+device race | **Duplicate** → 500 on DTR | C-9, H-9 | ✅ Backend |
| 2 | Alternating-card double tap | **Premature OUT** → day marked absent | H-1, H-2 | ✅ Backend dwell rule |
| 3 | Network failure | **Missing**, user told it succeeded | C-7 | ❌ **Detect only** |
| 4 | Deactivated card | **Unauthorized** record | C-10 | ✅ Backend |
| 5 | Unauthenticated POST | **Forged** record | C-1, C-11 | ✅ Backend |
| 6 | Shift crossing midnight | **Split** into two wrong records | H-8 | ✅ Backend |
| 7 | Mixed-case UID rows | **500** on every tap of that card | H-6 | ✅ Backend |
| 8 | Blocked loop during a request | **Missed** scan, no trace | H-5 | 🟡 Reduced ~3×, residual |

**Seven of the eight are fully fixable in the backend.** Only #3 and (partly) #8 remain, and both are covered by detection rather than prevention.

---

## 9. Security Findings

**Confirmed vulnerabilities:** C-1, C-2, C-3, C-4, C-11 (all backend-only) · C-5, C-6 (2 firmware lines each) · H-7, M-1, M-13.

**The complete unauthenticated attack chain — no physical access, no insider:**
```
1. GET  /api/rfid_pairing_tap/   → harvest a live faculty card UID        (C-3)
   ↑ continuously repopulated because the device pairs on every tap       (H-4)
2. POST /api/log_attendance/     → write attendance as that faculty       (C-1)
```
Two requests. Or without any real card:
```
1. POST /api/rfid_tap/     {uid: ATTACKER}        → creates the tag row   (C-2)
2. POST /api/pair_rfid/    {faculty_id, rfid_uid} → binds it to a faculty (C-11)
3. POST /api/log_attendance/ {uid: ATTACKER}      → attendance recorded   (C-1)
```
Step 2 needs a faculty `uuid`, and C-11's distinguishable errors form an enumeration oracle whose success case **returns the person's real name**.

**Every step of both chains is closed by backend changes alone.**

**Compensating network controls** (worth doing regardless, and the main residual defense for C-5/C-6 until the reflash): place the reader on an isolated VLAN with egress limited to the Railway host, and disable inter-client traffic on that SSID. This does not replace the TLS and OTA fixes — it reduces who can reach the device while they're pending.

**Positives:** prod env vars correctly set; `@admin_required` consistent outside C-3; 2FA middleware in place; Fernet key and Google credentials env-sourced; `.env` correctly gitignored and untracked (verified via `git ls-files`); `SECURE_PROXY_SSL_HEADER` correct for Railway's proxy.

---

## 10. Reliability & Failure-Recovery Findings

| Failure scenario | Current behavior | After in-scope fixes |
|---|---|---|
| Wi-Fi down at boot | Blocks in captive portal **forever** | ✅ Times out, retries, self-recovers (C-8, H-12) |
| Wi-Fi drops after boot | Undocumented core auto-reconnect | ✅ Explicit; heartbeat alerts if not (H-12, H-13) |
| Wi-Fi drops mid-tap | Tap lost; card locked out 5 min, false message | 🟡 Still lost, but **retry works immediately** (H-3) and the gap is visible (C-7) |
| Backend 500 / cold start | Tap lost; generic parse error on LCD | 🟡 Lost but logged, alerted, reconcilable (C-7, H-11) |
| Backend slow (>timeout) | Tap lost; loop blocked; concurrent cards missed | 🟡 Window ~12 s → ~4 s (H-5) |
| DB unavailable | 500 → tap lost (`connect_timeout=5` bounds the hang) | 🟡 Logged + alerted |
| Two cards presented together | Second **not detected at all** | 🟡 Narrower window; reconciliation surfaces it |
| Duplicate record created | Uncaught 500 on the DTR page | ✅ Prevented by constraint (C-9) |
| Device powered off / hung | **Nobody notified** | ✅ Alert within 10 min (H-13) |
| Reset command lost | Flag consumed, device never resets | ✅ Pending/confirmed state (C-4) |
| Card deactivated | Still works | ✅ Rejected with a clear message (C-10) |

**The strategic shift:** the system moves from *silent, undetectable failure* to *visible, correctable failure*. Within a fixed-hardware constraint that is the correct target — you cannot prevent every lost scan, but you can guarantee you always know one happened and can repair it the same day.

---

## 11. Performance / Scalability Findings

Current scale (one device, one campus) is comfortably within capacity — these are forward-looking, and all backend-side.

- **M-6 (architectural ceiling):** `LocMemCache` couples RFID pairing to a single process. Scaling Daphne past one replica breaks pairing **silently, with no error message**. This is the first thing that will break when you scale.
- **M-7 / M-8:** DTR and attendance-log views issue ~90 queries per month view and two full COUNTs per log page, on an unindexed table where `date__month` cannot use an index even if one existed. Fine at hundreds of rows; noticeable at tens of thousands.
- **H-5:** device throughput is bounded at roughly one tap per 3–12 s (→ ~4 s after the bundle), which is the real constraint at class changes. **This is a hardware-architecture limit** and the reason the reconciliation report matters at peak.
- **H-4:** every tap costs two TLS handshakes; removing `sendPairing` halves device latency and backend request volume.
- **H-7 / M-1:** with no rate limiting on unauthenticated write endpoints, request volume is attacker-controlled.

---

## 12. Testing Gaps

**Current state: `rfid/tests.py` is the unmodified 3-line Django stub. Zero tests for the attendance module, and no CI** (no `.github/`, confirmed). The only real tests are `faculty/tests.py` (deliverable auto-assignment); `adminhub`, `applicant`, `base`, `notifications` test files are empty stubs.

**Required before production — backend:**
- IN → OUT → DONE state machine, all three branches
- Unknown UID (404), unpaired UID (400), **inactive tag** (C-10 regression)
- Unauthenticated request rejected on all five device endpoints (C-1–C-4, C-11 regression)
- **Concurrency:** N parallel POSTs for one UID → exactly one row (C-9 regression)
- Minimum-dwell rejection at the boundary (H-1, H-2)
- Midnight-boundary handling (H-8)
- Mixed-case UID → clean error, not 500 (H-6)
- Manual + device race, and manual entry with `time_out` blank (H-9)
- `DTRCalculator.calculate_assignment_status` across late/early/on-time/overtime/absent, including `time_out=None` and duplicate-log inputs
- **Frozen response-contract tests for every branch** (H-14) — elevated in priority, since the firmware cannot adapt to a contract change
- All device-facing `error` strings ≤20 characters (M-16) — assert in a test so it cannot regress

**Required — device (manual, given fixed hardware):**
- **Bench-verify the reflash bundle before field deployment**, item 2 and 3 first (see §6 sequencing)
- Boot with the AP off → confirm the device reaches `loop()` and self-recovers (**the single most important firmware test**)
- Cert validation against a self-signed proxy → must refuse (C-5)
- Cold boot with NTP unreachable → confirm graceful behavior (C-5)
- OTA without the password → must fail (C-6)
- Failed tap → immediate retry accepted (H-3)
- Rapid multi-card presentation to **quantify the residual missed-scan window** (H-5) and record it in the runbook
- Each new backend response type checked against the real LCD (H-14, M-16)

**Required — operational:**
- Load test on `log_attendance` at expected peak `[NEEDS-INFO: how many faculty tap in the busiest 5 minutes?]`
- **A full day of parallel manual logging vs. system records before go-live** — the empirical baseline for how much attendance C-7 actually costs you
- `manage.py check --deploy` in CI

**Recommendation:** add a minimal GitHub Actions workflow running `manage.py test` + `check --deploy`. Without CI these regression tests will not stay green — and with a frozen firmware, a backend regression that breaks the response contract cannot be fixed by updating the device.

---

## 13. End-to-End RFID / Attendance Workflow Assessment

```
[Card] → [MFRC522] → [ESP32 loop()] → [HTTPS POST] → [Django/DRF] → [PostgreSQL] → [DTR/Export]
```

| Stage | Now | Blocking issues | After in-scope work |
|---|---|---|---|
| 1. Card → reader | ✅ Solid | — | ✅ |
| 2. Device duplicate guard | 🔴 | H-1, H-3 | ✅ Backend dwell rule + retry fix |
| 3. Device → network | 🔴 | C-5, C-8, H-12 | ✅ Reflash bundle |
| 4. Transport | 🔴 | C-7, H-5 | 🟡 Window cut ~3×; loss detected not prevented |
| 5. API auth | 🔴 | C-1 | ✅ Backend |
| 6. Tag resolution | 🔴 | C-10, H-6 | ✅ Backend |
| 7. Record write | 🔴 | C-9, H-1, H-2, H-8 | ✅ Backend |
| 8. Response → LCD | 🟠 | H-14, M-16, H-3 | ✅ Frozen contract + ≤20-char strings |
| 9. Failure feedback | 🔴 | C-7, H-11 | 🟡 Logged, alerted, reconcilable |
| 10. DTR / export | 🟠 | C-9, M-8 | ✅ Backend |

**Can the system produce incorrect, duplicated, missing, or inconsistent attendance records?**

**Today: yes — all four, by eight confirmed mechanisms** (§8). Most likely in daily operation, in order: **missing** (C-7, every network blip), **incorrect** (H-1/H-2, a premature OUT marks the entire day absent), **duplicated** (C-9, any concurrent write), **forged** (C-1, needs only the public URL).

**After the in-scope work: duplication, forgery, unauthorized use, and incorrect status are eliminated.** Missing records remain possible during network outages and at the ~4 s per-tap blind spot — but become **detectable within 10 minutes and correctable the same day** via the heartbeat, alert, and reconciliation report. That is the realistic ceiling without firmware restructuring, and it is a defensible production posture provided the residual limitation is documented and the reconciliation report is actually reviewed daily.

**What is genuinely well-built and should be preserved:** server-side timestamping (removes device clock drift from the trust model entirely); `DTRCalculator`'s status logic, handling early-in, late, overtime, and consecutive-assignment grouping, correctly using `timezone.localtime` throughout; the `is_manual` flag distinguishing manual from device records; the admin UID normalizer handling both decimal USB-reader and hex ESP32 formats with byte-order correction; the pairing confirmation modal with its already-paired warning; and the LCD state machine with auto-return-to-ready. The foundations are sound — the gaps are at the trust boundary and in the failure paths.

---

## 14. Recommended Fix Roadmap

> Sequenced so the device is touched **once**, and so nothing depends on hardware work that isn't happening.

**Phase 0 — Immediate, minutes, zero risk**
1. Add `@admin_required` to `rfid_pairing_tap_api` — one line, closes live UID disclosure *(C-3)*
2. Delete `pair_rfid_api` and its URL — unused, removes a forgery step *(C-11)*
3. Capture `platformio.ini` with exact library/board versions **before** any firmware work *(L-4)*

**Phase 1 — Backend security · ~1 day · device untouched**
4. Add `REST_FRAMEWORK` settings: authenticated default + throttle rates *(C-1, M-1 — highest leverage)*
5. Add the `RFIDDevice` model (device_id, token hash, last_seen, firmware_version, last_ip) *(C-1, C-4, H-13, M-5)*
6. Add `HasValidDeviceToken` using `hmac.compare_digest`; apply to `log_attendance`, `rfid_tap_api`, `check_wifi_reset` *(C-1, C-2, C-4)* — **verify the live device still records before removing the open path**
7. Gate the pairing cache write behind admin-activated pairing mode *(C-3, neutralises H-4 server-side)*
8. Reset flag: pending/confirmed state, cleared on the next authenticated poll *(C-4)*

**Phase 2 — Backend data integrity · ~1 day**
9. Move migrations to a single release step *(M-12 — do this before step 10)*
10. **Audit production for duplicate `(faculty, date)` rows; write and rehearse the merge migration on a copy** *(C-9 — this will fail on live data otherwise)*
11. Apply the unique constraint + indexes; wrap `log_attendance` in `transaction.atomic()`; handle `IntegrityError` *(C-9, H-9)*
12. Filter `is_active=True`; add the inactive-card response *(C-10)*
13. Normalize UID on `save()`; migrate existing rows; exact-match lookup *(H-6)*
14. Add the admin-configurable minimum-dwell rule *(H-1, H-2)*
15. Stop auto-creating tags in the 404 path; add UID format validation *(H-7, M-4)*
16. Keep all device-facing `error` strings ≤20 chars; always return JSON on every error path *(M-16, M-2, M-3)*
17. Make `time_out` optional on the manual form *(H-9 — the C-7 recovery path)*

**Phase 3 — Observability & compensating controls · ~1 day · MANDATORY, not optional**
18. `LOGGING` config; log every attendance decision *(H-11)*
19. `AttendanceScan` append-only audit table *(H-10, H-11)*
20. Heartbeat via the existing 60 s poll — **no firmware change** *(H-13, C-7)*
21. Celery beat quiet-device alert (>10 min during working hours) *(C-7, H-13)*
22. Daily reconciliation report: scheduled-but-no-log, cross-referenced with downtime *(C-7)*
23. `/healthz/` *(M-14)*

**Phase 4 — The single firmware reflash · ~0.5 day**
24. Bench-flash items 2 & 3 (OTA password, portal timeout) first, verified *(C-6, C-8)*
25. Then the remaining bundle: TLS + NTP, auto-reconnect, `lastUID` move, timeout constant, optional `sendPairing` removal and `safeDelay` fix *(C-5, H-12, H-3, H-5, H-4, M-15)*
26. Full bench test sweep (§12) **before** returning the device to service; keep the rollback binary

**Phase 5 — Contract, tests, polish · ~1.5 days**
27. Document the frozen response contract in `docs/` *(H-14)*
28. Full test suite (§12) + GitHub Actions CI
29. Query and index optimization *(M-7, M-8, M-9)*
30. Document the single-replica requirement, or fix `LocMemCache` *(M-6)*
31. Cleanup: dead imports, delete `AttendanceStatusService`, HSTS *(M-10, M-11, M-13, L-1, L-2, L-5, L-6)*

**Minimum viable production gate: Phases 0–4.** Phase 3 is non-negotiable — it is the entire mitigation for the one Critical that cannot be fixed.

---

## 15. Final Production Readiness Checklist

**Security — backend**
- [ ] `REST_FRAMEWORK` configured with an authenticated default *(C-1)*
- [ ] Device token validated with `hmac.compare_digest` on all device endpoints *(C-1, C-2, C-4)*
- [ ] Live device confirmed still recording after auth is enforced
- [ ] `rfid_pairing_tap_api` requires admin *(C-3)*
- [ ] Pairing cache write gated behind admin pairing mode *(C-3, H-4)*
- [ ] `pair_rfid_api` removed *(C-11)*
- [ ] Rate limiting active *(M-1)*
- [ ] HSTS enabled; `manage.py check --deploy` clean *(M-13)*
- [ ] Reader on an isolated VLAN with egress restricted to the Railway host

**Security — firmware (single reflash)**
- [ ] OTA password set and stored in the password manager *(C-6)*
- [ ] TLS certificate pinned; NTP synced; **CA expiry diarised** *(C-5)*

**Data integrity**
- [ ] Production audited for duplicates; merge migration rehearsed on a copy *(C-9)*
- [ ] `UniqueConstraint(faculty, date)` + indexes applied *(C-9)*
- [ ] `log_attendance` atomic and `IntegrityError`-safe *(C-9)*
- [ ] `is_active` enforced on tag lookup *(C-10)*
- [ ] UID normalized on write; exact-match lookup *(H-6)*
- [ ] Minimum dwell time enforced and admin-configurable *(H-1, H-2)*
- [ ] Midnight-boundary decision made *(H-8)* — **pending your answer on evening schedules**
- [ ] Tag auto-creation removed from the 404 path *(H-7, M-4)*
- [ ] Manual form accepts a blank `time_out` *(H-9)*

**Reliability**
- [ ] Config-portal timeout verified by booting with the AP off *(C-8)*
- [ ] Auto-reconnect explicit *(H-12)*
- [ ] `lastUID` committed only on success; failed tap retryable *(H-3)*
- [ ] Per-tap window measured and recorded in the runbook *(H-5)*
- [ ] **Residual scan-loss limitation documented and signed off** *(C-7)*

**Observability — the C-7 mitigation, all mandatory**
- [ ] `LOGGING` configured; every attendance decision logged *(H-11)*
- [ ] `AttendanceScan` audit table live *(H-10)*
- [ ] Device heartbeat recording `last_seen` *(H-13)*
- [ ] Quiet-device alert firing within 10 minutes *(H-13, C-7)*
- [ ] Daily reconciliation report live **and assigned to a named owner who reviews it** *(C-7)*
- [ ] `/healthz/` *(M-14)*

**Testing**
- [ ] Backend suite (§12) passing, including frozen-contract tests
- [ ] Concurrency test proves single-row-per-day
- [ ] Device bench sweep passed; rollback binary retained
- [ ] Load test at peak tap volume
- [ ] One-day parallel manual-vs-system reconciliation completed before go-live
- [ ] CI running tests + `check --deploy`

**Operations**
- [ ] `platformio.ini` committed; firmware build reproducible *(L-4)*
- [ ] Single-replica requirement documented, or M-6 fixed
- [ ] Migrations in a release step, not per web-process start *(M-12)*
- [ ] Runbook: device offline · card not reading · disputed record · **CA certificate rotation**

---

## Open Questions & Information Still Needed

1. **Evening schedules** — latest `end_time` across production `TeachingAssignment` rows? Determines whether H-8 (midnight split) is theoretical or live.
2. **Peak tap volume** — how many faculty tap within the busiest 5-minute window? Sizes the H-5 residual risk and the load test.
3. **Pairing workflow** — do you pair by tapping at the ESP32 reader, or with a USB reader at the admin PC? Determines whether the `sendPairing` removal (H-4 item 6) is safe. **If unsure, leave the line in** — the backend gating closes the security hole either way.
4. **Dwell-time policy** — minimum plausible gap between a faculty member's IN and OUT? Needed to set the H-1/H-2 threshold. A business decision, not a technical one.
5. **`AttendanceStatusService`** — confirm it's abandoned so I can delete it (M-11), or tell me it's in progress.
6. **Firmware build environment** — no `platformio.ini`/`.ino` project files were provided. Library versions, board target, and partition scheme are needed before any reflash (L-4), and you currently cannot rebuild the running firmware.
7. **Physical/network placement** — is the reader in a locked enclosure on a restricted VLAN? Determines residual risk while C-5/C-6 are pending, and is the main compensating control in the meantime.

---

## Appendix — How to use this report

**Finding IDs are stable.** `C-1…C-11` (Critical), `H-1…H-14` (High), `M-1…M-16` (Medium), `L-1…L-6` (Low). Cite them in tickets and commit messages so the roadmap in §14 and the checklist in §15 stay traceable as work lands.

**Every code reference is a `file:line` anchor** against branch `production` @ `97c3dac`. Line numbers will drift as fixes are applied; the surrounding function and symbol names are given alongside so findings remain locatable.

**Read §14 and §15 first if you are planning the work.** §14 sequences the fixes so the device is touched exactly once and nothing depends on hardware work that isn't happening. §15 is the go/no-go gate.

**Suggested first step:** Phase 0 in §14 — four lines of change, no device access, and it immediately closes the live UID-disclosure (C-3) and the remote forgery chain (C-11).
