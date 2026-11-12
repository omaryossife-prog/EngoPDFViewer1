"""Engo Admin Panel — standalone desktop tool for Engo's owner only.

يتحكم هذا البرنامج في حسابات المستخدمين والاشتراكات والأجهزة والمدفوعات
وحدود الميزات ونسخ البرنامج الموثوقة، عن طريق الاتصال المباشر بقاعدة Supabase
باستخدام مفتاح "service_role" (مفتاح سري كامل الصلاحيات).

تحذير أمني مهم جدًا:
  - مفتاح service_role يتجاوز كل قواعد الـ RLS، فهو يعطي تحكمًا كاملًا في
    قاعدة البيانات. لا تضعه أبدًا داخل برنامج Engo نفسه ولا أي ملف يوزّع
    للمستخدمين، ولا ترفعه على GitHub. هذه الأداة لجهازك الشخصي فقط.
  - يمكنك الحصول عليه من: Supabase Dashboard → Settings → API →
    "service_role secret" (مختلف عن publishable/anon key المستخدم داخل Engo).
  - الإعدادات (الرابط والمفتاح) تُحفظ محليًا فقط عبر QSettings (لا تُكتب داخل
    مجلد المشروع، فلا خطر من رفعها بالخطأ على Git).

تشغيل الأداة:
    pip install PyQt6
    python engo_admin.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import calendar

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QComboBox, QCheckBox, QMessageBox, QDialog, QDialogButtonBox, QHeaderView,
    QAbstractItemView, QDateEdit, QGroupBox, QStatusBar, QSplitter, QFrame, QTextEdit,
)


# --------------------------------------------------------------------------
# Supabase REST client (uses only the Python standard library, no extra deps)
# --------------------------------------------------------------------------

class SupabaseAdminError(RuntimeError):
    pass


class SupabaseAdminClient:
    """Minimal PostgREST + GoTrue admin client using the service_role key."""

    def __init__(self, base_url: str, service_role_key: str, timeout: int = 20):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.service_role_key = (service_role_key or "").strip()
        self.timeout = timeout

    def _headers(self, prefer=None):
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method, url, body=None, prefer=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._headers(prefer))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            raise SupabaseAdminError(f"HTTP {exc.code}: {detail[:600]}") from exc
        except urllib.error.URLError as exc:
            raise SupabaseAdminError(f"تعذّر الاتصال بالسيرفر: {exc.reason}") from exc

    # --- generic REST (table) helpers -----------------------------------

    def select(self, table, select="*", filters=None, order=None, limit=None, offset=None):
        params = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(max(1, int(limit)))
        if offset is not None:
            params["offset"] = str(max(0, int(offset)))
        url = f"{self.base_url}/rest/v1/{table}?{urllib.parse.urlencode(params, safe=',.()')}"
        return self._request("GET", url) or []

    def update(self, table, filters, patch_body):
        params = dict(filters or {})
        url = f"{self.base_url}/rest/v1/{table}?{urllib.parse.urlencode(params, safe=',.()')}"
        return self._request("PATCH", url, body=patch_body, prefer="return=representation") or []

    def insert(self, table, body):
        url = f"{self.base_url}/rest/v1/{table}"
        return self._request("POST", url, body=body, prefer="return=representation") or []

    def delete(self, table, filters):
        params = dict(filters or {})
        url = f"{self.base_url}/rest/v1/{table}?{urllib.parse.urlencode(params, safe=',.()')}"
        return self._request("DELETE", url, prefer="return=representation") or []

    def rpc(self, function_name, arguments=None):
        """Call an owner-only Postgres RPC through the service_role connection."""
        safe_name = urllib.parse.quote(str(function_name or "").strip(), safe="")
        if not safe_name:
            raise SupabaseAdminError("اسم إجراء قاعدة البيانات غير صالح.")
        url = f"{self.base_url}/rest/v1/rpc/{safe_name}"
        return self._request("POST", url, body=arguments or {})

    # --- GoTrue admin (needed only to read e-mail addresses) ------------

    def list_auth_users(self, max_users=3000, per_page=200):
        users, page = [], 1
        while True:
            url = f"{self.base_url}/auth/v1/admin/users?page={page}&per_page={per_page}"
            data = self._request("GET", url) or {}
            batch = data.get("users") if isinstance(data, dict) else None
            if not batch:
                break
            users.extend(batch)
            if len(batch) < per_page or len(users) >= max_users:
                break
            page += 1
        return users

    def test_connection(self):
        self.select("plans", limit=1)
        return True


def _parse_dt(value):
    if not value or not isinstance(value, str):
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _fmt_dt(value):
    dt = _parse_dt(value)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _checkbox_in(cell_widget: QWidget) -> QCheckBox:
    """Find the QCheckBox inside a cell widget, whether or not it's wrapped by _centered()."""
    if isinstance(cell_widget, QCheckBox):
        return cell_widget
    return cell_widget.findChild(QCheckBox)


def _centered(widget: QWidget) -> QWidget:
    """Wrap a widget (e.g. a checkbox) so it renders centered inside a table cell."""
    holder = QWidget()
    box = QHBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.addStretch(1)
    box.addWidget(widget)
    box.addStretch(1)
    return holder


# --------------------------------------------------------------------------
# Background worker — keeps the UI responsive during network calls
# --------------------------------------------------------------------------

class ApiWorker(QThread):
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
            self.finished_err.emit(str(exc))
            return
        self.finished_ok.emit(result)


# --------------------------------------------------------------------------
# Data-fetching helpers run inside ApiWorker (take the client explicitly)
# --------------------------------------------------------------------------

def fetch_users_overview(client: SupabaseAdminClient):
    auth_users = client.list_auth_users()
    profiles = client.select("profiles", select="user_id,display_name,account_status")
    subs = client.select("subscriptions", select="user_id,plan_id,status,starts_at,ends_at", order="starts_at.desc")
    devices = client.select("devices", select="user_id,status")

    profiles_by_id = {p["user_id"]: p for p in profiles}
    active_devices = {}
    for d in devices:
        if d.get("status") == "active":
            active_devices[d["user_id"]] = active_devices.get(d["user_id"], 0) + 1

    now = datetime.now(timezone.utc)
    effective_sub = {}
    for s in subs:
        uid = s.get("user_id")
        if uid in effective_sub or s.get("status") not in ("active", "trialing"):
            continue
        starts, ends = _parse_dt(s.get("starts_at")), _parse_dt(s.get("ends_at"))
        if starts and starts > now:
            continue
        if ends and ends <= now:
            continue
        effective_sub[uid] = s

    rows = []
    for u in auth_users:
        uid = u.get("id")
        profile = profiles_by_id.get(uid, {})
        sub = effective_sub.get(uid)
        rows.append({
            "id": uid,
            "email": u.get("email") or "—",
            "created_at": u.get("created_at"),
            "last_sign_in_at": u.get("last_sign_in_at"),
            "display_name": profile.get("display_name") or "",
            "account_status": profile.get("account_status") or "active",
            "plan_id": (sub or {}).get("plan_id") or "free",
            "sub_status": (sub or {}).get("status") or "—",
            "sub_ends_at": (sub or {}).get("ends_at") or "",
            "devices_active": active_devices.get(uid, 0),
        })
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def grant_premium(client: SupabaseAdminClient, user_id: str, ends_at_iso):
    client.update("subscriptions", {"user_id": f"eq.{user_id}", "status": "in.(active,trialing)"},
                   {"status": "cancelled"})
    client.insert("subscriptions", {
        "user_id": user_id, "plan_id": "premium", "status": "active",
        "starts_at": _now_iso(), "ends_at": ends_at_iso,
    })
    _log_event(client, user_id, "admin_grant_premium", {"ends_at": ends_at_iso})
    return True


def _add_months_utc(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def approve_subscription_request(client: SupabaseAdminClient, payment: dict):
    """Atomically approve a pending QR payment and activate its Premium term."""
    payment_id = str(payment.get("id") or "")
    if not payment_id or payment.get("status") != "pending":
        raise SupabaseAdminError("عملية الدفع لم تعد معلّقة أو بياناتها غير مكتملة.")
    return client.rpc("admin_approve_qr_payment_v1", {"p_payment_id": payment_id})


def reject_subscription_request(client: SupabaseAdminClient, payment: dict):
    payment_id = str(payment.get("id") or "")
    if not payment_id or payment.get("status") != "pending":
        raise SupabaseAdminError("عملية الدفع لم تعد معلّقة أو بياناتها غير مكتملة.")
    return client.rpc("admin_reject_qr_payment_v1", {"p_payment_id": payment_id})


def revoke_premium(client: SupabaseAdminClient, user_id: str):
    client.update("subscriptions", {"user_id": f"eq.{user_id}", "status": "in.(active,trialing)"},
                   {"status": "cancelled"})
    _log_event(client, user_id, "admin_revoke_premium", {})
    return True


def set_account_status(client: SupabaseAdminClient, user_id: str, status: str):
    client.update("profiles", {"user_id": f"eq.{user_id}"}, {"account_status": status})
    _log_event(client, user_id, f"admin_account_{status}", {})
    return True


def _log_event(client: SupabaseAdminClient, user_id: str, event_type: str, details: dict):
    try:
        client.insert("license_events", {
            "user_id": user_id, "event_type": event_type,
            "details": {**details, "actor": "admin_panel"},
        })
    except Exception:
        pass  # audit logging is best-effort only; never blocks the real action


# --------------------------------------------------------------------------
# Settings / connection dialog
# --------------------------------------------------------------------------

class ConnectionDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("الاتصال بـ Supabase")
        self.setModal(True)
        self.resize(480, 220)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.url_edit = QLineEdit(str(settings.value("supabase_url", "") or ""))
        self.url_edit.setPlaceholderText("https://xxxxxxxx.supabase.co")
        form.addRow("رابط مشروع Supabase:", self.url_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(str(settings.value("service_role_key", "") or ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("service_role secret key")
        toggle = QPushButton("إظهار")
        toggle.setCheckable(True)
        toggle.toggled.connect(lambda show: (
            self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password),
            toggle.setText("إخفاء" if show else "إظهار"),
        ))
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(toggle)
        form.addRow("service_role key:", key_row)
        layout.addLayout(form)

        warning = QLabel(
            "⚠ هذا المفتاح له صلاحية كاملة على قاعدة البيانات. لا تشاركه مع أحد ولا تضعه\n"
            "داخل برنامج Engo نفسه. يُحفظ محليًا على هذا الجهاز فقط."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#b5894a;")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        self.settings.setValue("supabase_url", self.url_edit.text().strip())
        self.settings.setValue("service_role_key", self.key_edit.text().strip())
        self.settings.sync()


# --------------------------------------------------------------------------
# "Grant Premium" small dialog (optional expiry date)
# --------------------------------------------------------------------------

class GrantPremiumDialog(QDialog):
    def __init__(self, email, parent=None):
        super().__init__(parent)
        self.setWindowTitle("منح اشتراك Premium")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"المستخدم: {email}"))

        self.lifetime_check = QCheckBox("بدون تاريخ انتهاء (مدى الحياة)")
        self.lifetime_check.setChecked(True)
        layout.addWidget(self.lifetime_check)

        self.date_edit = QDateEdit(QDate.currentDate().addMonths(1))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        self.lifetime_check.toggled.connect(lambda checked: self.date_edit.setEnabled(not checked))
        layout.addWidget(self.date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def ends_at_iso(self):
        if self.lifetime_check.isChecked():
            return None
        qd = self.date_edit.date()
        return datetime(qd.year(), qd.month(), qd.day(), tzinfo=timezone.utc).isoformat()


# --------------------------------------------------------------------------
# "Record manual payment" dialog — payments happen outside the app (bank
# transfer, Instapay, Vodafone Cash…), so there's no automatic gateway
# writing to payment_transactions. This logs one manually for bookkeeping,
# and can optionally grant Premium in the same step.
# --------------------------------------------------------------------------

class RecordPaymentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تسجيل دفعة يدويًا")
        self.setModal(True)
        self.resize(420, 320)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("نفس الإيميل الظاهر في تبويب المستخدمين")
        form.addRow("إيميل المستخدم:", self.email_edit)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("مثال: 150")
        form.addRow("المبلغ:", self.amount_edit)

        self.currency_edit = QLineEdit("EGP")
        form.addRow("العملة:", self.currency_edit)

        self.provider_edit = QLineEdit()
        self.provider_edit.setPlaceholderText("مثال: Instapay / Vodafone Cash / تحويل بنكي")
        form.addRow("طريقة الدفع:", self.provider_edit)

        self.status_combo = QComboBox()
        self.status_combo.addItem("ناجحة", "succeeded")
        self.status_combo.addItem("معلّقة", "pending")
        self.status_combo.addItem("مسترجعة", "refunded")
        self.status_combo.addItem("فاشلة", "failed")
        form.addRow("حالة الدفعة:", self.status_combo)
        layout.addLayout(form)

        self.grant_check = QCheckBox("امنح Premium لهذا المستخدم تلقائيًا بعد التسجيل")
        self.grant_check.setChecked(True)
        layout.addWidget(self.grant_check)

        self.lifetime_check = QCheckBox("بدون تاريخ انتهاء (مدى الحياة)")
        self.lifetime_check.setChecked(True)
        layout.addWidget(self.lifetime_check)
        self.date_edit = QDateEdit(QDate.currentDate().addMonths(1))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        self.lifetime_check.toggled.connect(lambda checked: self.date_edit.setEnabled(not checked))
        self.grant_check.toggled.connect(lambda checked: (
            self.lifetime_check.setEnabled(checked),
            self.date_edit.setEnabled(checked and not self.lifetime_check.isChecked()),
        ))
        layout.addWidget(self.date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def ends_at_iso(self):
        if self.lifetime_check.isChecked():
            return None
        qd = self.date_edit.date()
        return datetime(qd.year(), qd.month(), qd.day(), tzinfo=timezone.utc).isoformat()

    def values(self):
        amount_text = self.amount_edit.text().strip()
        try:
            amount = float(amount_text) if amount_text else None
        except ValueError:
            amount = None
        return {
            "email": self.email_edit.text().strip(),
            "amount": amount,
            "currency": self.currency_edit.text().strip() or "EGP",
            "provider": self.provider_edit.text().strip() or "يدوي",
            "status": self.status_combo.currentData(),
            "grant_premium": self.grant_check.isChecked(),
            "ends_at": self.ends_at_iso() if self.grant_check.isChecked() else None,
        }


def record_manual_payment(client: SupabaseAdminClient, user_id: str, values: dict):
    client.insert("payment_transactions", {
        "user_id": user_id, "plan_id": "premium" if values["grant_premium"] else None,
        "amount": values["amount"], "currency": values["currency"], "provider": values["provider"],
        "status": values["status"],
        "metadata": {"source": "manual", "recorded_by": "admin_panel"},
    })
    if values["grant_premium"] and values["status"] == "succeeded":
        grant_premium(client, user_id, values["ends_at"])
    return True


# --------------------------------------------------------------------------
# Users tab
# --------------------------------------------------------------------------

class UsersTab(QWidget):
    COLUMNS = ["البريد الإلكتروني", "الاسم", "حالة الحساب", "الخطة", "حالة الاشتراك",
               "ينتهي في", "أجهزة نشطة", "تاريخ التسجيل"]

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.rows = []
        self.filtered = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث بالإيميل أو الاسم…")
        self.search.textChanged.connect(self._apply_filter)
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.load)
        top.addWidget(self.search, 1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.suspend_btn = QPushButton("تعليق الحساب")
        self.suspend_btn.clicked.connect(self._suspend)
        self.activate_btn = QPushButton("تفعيل الحساب")
        self.activate_btn.clicked.connect(self._activate)
        self.grant_btn = QPushButton("منح Premium")
        self.grant_btn.clicked.connect(self._grant)
        self.revoke_btn = QPushButton("سحب Premium")
        self.revoke_btn.clicked.connect(self._revoke)
        self.devices_btn = QPushButton("عرض الأجهزة")
        self.devices_btn.clicked.connect(self._view_devices)
        self.payments_btn = QPushButton("عرض المدفوعات")
        self.payments_btn.clicked.connect(self._view_payments)
        for b in (self.suspend_btn, self.activate_btn, self.grant_btn, self.revoke_btn,
                  self.devices_btn, self.payments_btn):
            actions.addWidget(b)
        layout.addLayout(actions)

    # --- loading ----------------------------------------------------
    def load(self):
        self.main.run_async(fetch_users_overview, self._on_loaded, args=(self.main.client,),
                             busy_label="جاري تحميل المستخدمين…")

    def _on_loaded(self, rows):
        self.rows = rows
        self.main.users_index = {r["id"]: r["email"] for r in rows}
        self._apply_filter()
        if hasattr(self.main, "usage_tab"):
            self.main.usage_tab.load()
        self.main.status(f"تم تحميل {len(rows)} مستخدم")

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        self.filtered = [r for r in self.rows if not text
                          or text in (r["email"] or "").lower()
                          or text in (r["display_name"] or "").lower()] if self.rows else []
        self.table.setRowCount(len(self.filtered))
        for i, r in enumerate(self.filtered):
            values = [
                r["email"], r["display_name"] or "—",
                "موقوف" if r["account_status"] == "suspended" else "نشط",
                "Premium" if r["plan_id"] == "premium" else "Free",
                r["sub_status"], _fmt_dt(r["sub_ends_at"]) if r["sub_ends_at"] else "مدى الحياة" if r["plan_id"] == "premium" else "—",
                str(r["devices_active"]), _fmt_dt(r["created_at"]),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 2 and r["account_status"] == "suspended":
                    item.setForeground(QColor("#e07070"))
                if col == 3 and r["plan_id"] == "premium":
                    item.setForeground(QColor("#6dbf8a"))
                self.table.setItem(i, col, item)

    def _selected_row(self):
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self.filtered):
            QMessageBox.information(self, "Engo Admin", "اختر مستخدمًا من الجدول أولًا.")
            return None
        return self.filtered[idx]

    # --- actions ------------------------------------------------------
    def _suspend(self):
        row = self._selected_row()
        if not row:
            return
        if QMessageBox.question(self, "تأكيد", f"تعليق حساب {row['email']}؟") != QMessageBox.StandardButton.Yes:
            return
        self.main.run_async(set_account_status, lambda _r: self._done("تم تعليق الحساب"),
                             args=(self.main.client, row["id"], "suspended"))

    def _activate(self):
        row = self._selected_row()
        if not row:
            return
        self.main.run_async(set_account_status, lambda _r: self._done("تم تفعيل الحساب"),
                             args=(self.main.client, row["id"], "active"))

    def _grant(self):
        row = self._selected_row()
        if not row:
            return
        dlg = GrantPremiumDialog(row["email"], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.main.run_async(grant_premium, lambda _r: self._done("تم منح الاشتراك المدفوع"),
                             args=(self.main.client, row["id"], dlg.ends_at_iso()))

    def _revoke(self):
        row = self._selected_row()
        if not row:
            return
        if QMessageBox.question(self, "تأكيد", f"سحب Premium من {row['email']}؟") != QMessageBox.StandardButton.Yes:
            return
        self.main.run_async(revoke_premium, lambda _r: self._done("تم سحب الاشتراك المدفوع"),
                             args=(self.main.client, row["id"]))

    def _view_devices(self):
        row = self._selected_row()
        if not row:
            return
        self.main.open_devices_for(row["email"])

    def _view_payments(self):
        row = self._selected_row()
        if not row:
            return
        self.main.open_payments_for(row["email"])

    def _done(self, message):
        self.main.status(message)
        self.load()


# --------------------------------------------------------------------------
# Devices tab
# --------------------------------------------------------------------------

class DevicesTab(QWidget):
    COLUMNS = ["البريد", "اسم الجهاز", "الحالة", "إصدار البرنامج", "آخر اتصال", "تاريخ التفعيل"]

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.rows = []
        self.filtered = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث بالإيميل أو اسم الجهاز…")
        self.search.textChanged.connect(self._apply_filter)
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.load)
        top.addWidget(self.search, 1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.revoke_btn = QPushButton("إلغاء تفعيل الجهاز")
        self.revoke_btn.clicked.connect(self._revoke)
        self.reactivate_btn = QPushButton("إعادة تفعيل الجهاز")
        self.reactivate_btn.clicked.connect(self._reactivate)
        actions.addWidget(self.revoke_btn)
        actions.addWidget(self.reactivate_btn)
        layout.addLayout(actions)

    def load(self):
        self.main.run_async(lambda c: c.select("devices", order="last_seen.desc"), self._on_loaded,
                             args=(self.main.client,), busy_label="جاري تحميل الأجهزة…")

    def _on_loaded(self, rows):
        self.rows = rows
        self._apply_filter()
        self.main.status(f"تم تحميل {len(rows)} جهاز")

    def set_search(self, text):
        self.search.setText(text)

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        self.filtered = []
        for d in self.rows:
            email = self.main.users_index.get(d.get("user_id"), "")
            name = d.get("device_name") or ""
            if not text or text in email.lower() or text in name.lower():
                self.filtered.append(d)
        self.table.setRowCount(len(self.filtered))
        for i, d in enumerate(self.filtered):
            email = self.main.users_index.get(d.get("user_id"), d.get("user_id", "—"))
            status_ar = {"active": "نشط", "revoked": "ملغى", "inactive": "غير نشط"}.get(d.get("status"), d.get("status"))
            values = [email, d.get("device_name") or "—", status_ar, d.get("app_version") or "—",
                      _fmt_dt(d.get("last_seen")), _fmt_dt(d.get("activated_at"))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 2 and d.get("status") == "revoked":
                    item.setForeground(QColor("#e07070"))
                elif col == 2 and d.get("status") == "active":
                    item.setForeground(QColor("#6dbf8a"))
                self.table.setItem(i, col, item)

    def _selected(self):
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self.filtered):
            QMessageBox.information(self, "Engo Admin", "اختر جهازًا من الجدول أولًا.")
            return None
        return self.filtered[idx]

    def _revoke(self):
        row = self._selected()
        if not row:
            return
        self.main.run_async(
            lambda c: c.update("devices", {"id": f"eq.{row['id']}"}, {"status": "revoked", "updated_at": _now_iso()}),
            lambda _r: self._done("تم إلغاء تفعيل الجهاز"), args=(self.main.client,))

    def _reactivate(self):
        row = self._selected()
        if not row:
            return
        self.main.run_async(
            lambda c: c.update("devices", {"id": f"eq.{row['id']}"}, {"status": "active", "updated_at": _now_iso()}),
            lambda _r: self._done("تم إعادة تفعيل الجهاز"), args=(self.main.client,))

    def _done(self, message):
        self.main.status(message)
        self.load()


# --------------------------------------------------------------------------
# Payments tab (read-only)
# --------------------------------------------------------------------------

class PaymentsTab(QWidget):
    COLUMNS = ["البريد", "الخطة", "المبلغ", "العملة", "المزوّد", "الحالة", "المدة", "التاريخ", "إجراء"]

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.rows = []
        self.filtered = []

        layout = QVBoxLayout(self)
        note = QLabel(
            "مفيش بوابة دفع إلكترونية متصلة بالبرنامج دلوقتي — المدفوعات بتتم يدويًا "
            "(تحويل بنكي / Instapay / Vodafone Cash وغيرها)، فسجّلها هنا يدويًا لحفظ السجل."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث بالإيميل…")
        self.search.textChanged.connect(self._apply_filter)
        record_btn = QPushButton("تسجيل دفعة يدويًا")
        record_btn.clicked.connect(self._record_manual)
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.load)
        top.addWidget(self.search, 1)
        top.addWidget(record_btn)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def _record_manual(self):
        dlg = RecordPaymentDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["email"]:
            QMessageBox.warning(self, "Engo Admin", "اكتب إيميل المستخدم أولًا.")
            return
        user_id = next((uid for uid, email in self.main.users_index.items()
                         if email.lower() == values["email"].lower()), None)
        if not user_id:
            QMessageBox.warning(self, "Engo Admin",
                                 "مفيش مستخدم بهذا الإيميل. افتح تبويب المستخدمين وتأكد من الإيميل أولًا.")
            return
        self.main.run_async(record_manual_payment, lambda _r: self._done("تم تسجيل الدفعة"),
                             args=(self.main.client, user_id, values))

    def _done(self, message):
        self.main.status(message)
        self.load()
        self.main.users_tab.load()

    def load(self):
        self.main.run_async(lambda c: c.select("payment_transactions", order="created_at.desc", limit=1000),
                             self._on_loaded, args=(self.main.client,), busy_label="جاري تحميل المدفوعات…")

    def _on_loaded(self, rows):
        self.rows = rows
        self._apply_filter()
        self.main.status(f"تم تحميل {len(rows)} عملية دفع")

    def set_search(self, text):
        self.search.setText(text)

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        self.filtered = []
        for p in self.rows:
            email = self.main.users_index.get(p.get("user_id"), "")
            if not text or text in email.lower():
                self.filtered.append(p)
        self.table.setRowCount(len(self.filtered))
        status_ar = {"pending": "معلّق", "succeeded": "ناجح", "failed": "فاشل",
                     "refunded": "مسترجع", "cancelled": "ملغى"}
        for i, p in enumerate(self.filtered):
            email = self.main.users_index.get(p.get("user_id"), p.get("user_id", "—"))
            metadata = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
            period = {"monthly": "شهري", "quarterly": "ربع سنوي", "semiannual": "نصف سنوي", "annual": "سنوي"}.get(metadata.get("billing_period"), "—")
            values = [email, p.get("plan_id") or "—",
                      str(p.get("amount")) if p.get("amount") is not None else "—",
                      p.get("currency") or "—", p.get("provider") or "—",
                      status_ar.get(p.get("status"), p.get("status")), period, _fmt_dt(p.get("created_at"))]
            for col, value in enumerate(values):
                self.table.setItem(i, col, QTableWidgetItem(str(value)))
            if p.get("status") == "pending" and metadata.get("billing_period") in ("monthly", "quarterly", "semiannual", "annual"):
                holder = QWidget(); row_layout = QHBoxLayout(holder); row_layout.setContentsMargins(1,1,1,1); row_layout.setSpacing(3)
                approve = QPushButton("تأكيد"); approve.setToolTip("تأكيد التحويل وتفعيل Premium")
                reject = QPushButton("رفض"); reject.setToolTip("رفض طلب الدفع")
                approve.clicked.connect(lambda _checked=False, payment=dict(p): self._approve_request(payment))
                reject.clicked.connect(lambda _checked=False, payment=dict(p): self._reject_request(payment))
                row_layout.addWidget(approve); row_layout.addWidget(reject)
                self.table.setCellWidget(i, 8, holder)
            else:
                self.table.setItem(i, 8, QTableWidgetItem("—"))

    def _approve_request(self, payment):
        answer = QMessageBox.question(self, "تأكيد الدفع", "هل تحققت من وصول المبلغ وتريد تفعيل مدة Premium المطلوبة؟",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        self.main.run_async(lambda c: approve_subscription_request(c, payment),
                            lambda _r: self._done("تم تأكيد الدفع وتفعيل الاشتراك"),
                            args=(self.main.client,), busy_label="جاري تفعيل الاشتراك…")

    def _reject_request(self, payment):
        answer = QMessageBox.question(self, "رفض الطلب", "هل تريد رفض طلب الدفع المعلّق؟",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        self.main.run_async(lambda c: reject_subscription_request(c, payment),
                            lambda _r: self._done("تم رفض طلب الدفع"),
                            args=(self.main.client,), busy_label="جاري تحديث الطلب…")


# --------------------------------------------------------------------------
# Feature limits tab — literal, one row per (plan, feature) DB row
# --------------------------------------------------------------------------

class FeaturesTab(QWidget):
    RESET_PERIODS = ["lifetime", "daily", "monthly", "per_file"]

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.rows = []

        layout = QVBoxLayout(self)
        note = QLabel("حدود Free يتم ضبطها لكل ميزة. في Premium، كل ميزة مفعّلة متاحة بلا حدود؛ أزل التفعيل فقط لإخفاء الميزة من الخطة.")
        note.setWordWrap(True)
        layout.addWidget(note)

        top = QHBoxLayout()
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.load)
        top.addStretch(1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["الخطة", "الميزة", "مفعّلة", "الحد", "فترة التصفير", ""])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 70)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def load(self):
        self.main.run_async(lambda c: c.select("feature_entitlements", order="feature_key.asc,plan_id.asc"),
                             self._on_loaded, args=(self.main.client,), busy_label="جاري تحميل حدود الميزات…")

    def _on_loaded(self, rows):
        self.rows = rows
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            plan_item = QTableWidgetItem("Premium" if r["plan_id"] == "premium" else "Free")
            feature_item = QTableWidgetItem(r["feature_key"])
            self.table.setItem(i, 0, plan_item)
            self.table.setItem(i, 1, feature_item)

            enabled_box = QCheckBox()
            enabled_box.setChecked(bool(r.get("enabled")))
            self.table.setCellWidget(i, 2, _centered(enabled_box))

            limit_key = "premium_limit" if r["plan_id"] == "premium" else "free_limit"
            is_premium = r["plan_id"] == "premium"
            limit_edit = QLineEdit("بلا حدود" if is_premium else ("" if r.get(limit_key) is None else str(r.get(limit_key))))
            limit_edit.setPlaceholderText("بلا حدود")
            limit_edit.setMinimumWidth(90)
            limit_edit.setReadOnly(is_premium)
            if is_premium:
                limit_edit.setToolTip("كل ميزة مفعّلة في Premium بلا حدود")
            # Keep the native application theme for the limit input, as in the
            # previous version (do not force a white QLineEdit background).
            self.table.setCellWidget(i, 3, limit_edit)

            period_combo = QComboBox()
            allowed_periods = self.RESET_PERIODS if r.get("feature_key") in ("tags", "tag_units") else [p for p in self.RESET_PERIODS if p != "per_file"]
            period_combo.addItems(allowed_periods)
            period_combo.setEnabled(not is_premium)
            current = r.get("reset_period") or "lifetime"
            if current in self.RESET_PERIODS:
                period_combo.setCurrentText(current)
            # Keep the native combo-box appearance, matching the previous version.
            self.table.setCellWidget(i, 4, period_combo)

            save_btn = QPushButton("حفظ")
            save_btn.clicked.connect(lambda _checked=False, row=i: self._save_row(row))
            self.table.setCellWidget(i, 5, save_btn)
        self.main.status(f"تم تحميل {len(rows)} حد ميزة")

    def _save_row(self, row_index):
        r = self.rows[row_index]
        enabled_box = _checkbox_in(self.table.cellWidget(row_index, 2))
        limit_edit: QLineEdit = self.table.cellWidget(row_index, 3)
        period_combo: QComboBox = self.table.cellWidget(row_index, 4)

        is_premium = r["plan_id"] == "premium"
        if is_premium:
            limit_value = None
            limit_key = "premium_limit"
        else:
            limit_text = limit_edit.text().strip()
            if limit_text and not limit_text.isdigit():
                QMessageBox.warning(self, "Engo Admin", "الحد لازم يكون رقم صحيح أو فاضي (بلا حدود).")
                return
            limit_value = int(limit_text) if limit_text else None
            limit_key = "free_limit"

        patch = {
            "enabled": enabled_box.isChecked(),
            limit_key: limit_value,
            "reset_period": period_combo.currentText(),
        }
        self.main.run_async(lambda c: c.update("feature_entitlements", {"id": f"eq.{r['id']}"}, patch),
                             lambda _res: self.main.status(f"تم حفظ حد {r['feature_key']} ({r['plan_id']})"),
                             args=(self.main.client,))


# --------------------------------------------------------------------------
# Trusted builds tab
# --------------------------------------------------------------------------

class BuildsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.rows = []

        layout = QVBoxLayout(self)

        add_box = QGroupBox("إضافة إصدار جديد")
        add_layout = QHBoxLayout(add_box)
        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("مثال: 2.4.0")
        self.approved_check = QCheckBox("موافَق عليه مباشرة")
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("ملاحظات (اختياري)")
        add_btn = QPushButton("إضافة")
        add_btn.clicked.connect(self._add_build)
        add_layout.addWidget(self.version_edit)
        add_layout.addWidget(self.approved_check)
        add_layout.addWidget(self.notes_edit, 1)
        add_layout.addWidget(add_btn)
        layout.addWidget(add_box)

        top = QHBoxLayout()
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.load)
        top.addStretch(1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الإصدار", "موافَق عليه", "ملاحظات", "تاريخ الموافقة", ""])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 70)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def load(self):
        self.main.run_async(lambda c: c.select("trusted_builds", order="created_at.desc"),
                             self._on_loaded, args=(self.main.client,), busy_label="جاري تحميل الإصدارات…")

    def _on_loaded(self, rows):
        self.rows = rows
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["app_version"]))

            approved_box = QCheckBox()
            approved_box.setChecked(bool(r.get("is_approved")))
            self.table.setCellWidget(i, 1, _centered(approved_box))

            notes_edit = QLineEdit(r.get("notes") or "")
            self.table.setCellWidget(i, 2, notes_edit)

            self.table.setItem(i, 3, QTableWidgetItem(_fmt_dt(r.get("approved_at"))))

            save_btn = QPushButton("حفظ")
            save_btn.clicked.connect(lambda _checked=False, row=i: self._save_row(row))
            self.table.setCellWidget(i, 4, save_btn)
        self.main.status(f"تم تحميل {len(rows)} إصدار")

    def _add_build(self):
        version = self.version_edit.text().strip()
        if not version:
            QMessageBox.information(self, "Engo Admin", "اكتب رقم الإصدار أولًا.")
            return
        body = {
            "app_version": version, "is_approved": self.approved_check.isChecked(),
            "notes": self.notes_edit.text().strip() or None,
        }
        if body["is_approved"]:
            body["approved_at"] = _now_iso()

        def done(_res):
            self.version_edit.clear()
            self.notes_edit.clear()
            self.approved_check.setChecked(False)
            self.main.status(f"تمت إضافة الإصدار {version}")
            self.load()

        self.main.run_async(lambda c: c.insert("trusted_builds", body), done, args=(self.main.client,))

    def _save_row(self, row_index):
        r = self.rows[row_index]
        approved_box = _checkbox_in(self.table.cellWidget(row_index, 1))
        notes_edit: QLineEdit = self.table.cellWidget(row_index, 2)
        is_approved = approved_box.isChecked()
        patch = {"is_approved": is_approved, "notes": notes_edit.text().strip() or None}
        patch["approved_at"] = _now_iso() if is_approved else None

        self.main.run_async(
            lambda c: c.update("trusted_builds", {"app_version": f"eq.{r['app_version']}"}, patch),
            lambda _res: self._done(r["app_version"]), args=(self.main.client,))

    def _done(self, version):
        self.main.status(f"تم حفظ الإصدار {version}")
        self.load()



# --------------------------------------------------------------------------
# Application update distribution settings
# --------------------------------------------------------------------------

class UpdatesTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window

        root = QVBoxLayout(self)
        release_box = QGroupBox("إعدادات إصدار ENGO والتحديثات")
        form = QFormLayout(release_box)

        self.enabled_check = QCheckBox("إظهار إشعار التحديث داخل البرنامج")
        self.latest_version = QLineEdit("2.3.6")
        self.latest_version.setPlaceholderText("مثال: 2.3.7")
        self.update_url = QLineEdit()
        self.update_url.setPlaceholderText("https://example.com/engo-setup.exe")
        self.message_ar = QTextEdit()
        self.message_ar.setPlaceholderText("رسالة تظهر للمستخدم باللغة العربية (اختياري)")
        self.message_en = QTextEdit()
        self.message_en.setPlaceholderText("Message shown to English users (optional)")
        self.message_ar.setFixedHeight(70)
        self.message_en.setFixedHeight(70)

        form.addRow("", self.enabled_check)
        form.addRow("أحدث إصدار:", self.latest_version)
        form.addRow("رابط التحديث:", self.update_url)
        form.addRow("رسالة التحديث بالعربية:", self.message_ar)
        form.addRow("Update message (English):", self.message_en)
        root.addWidget(release_box)

        actions = QHBoxLayout()
        self.refresh_btn = QPushButton("إعادة تحميل")
        self.save_btn = QPushButton("حفظ إعدادات التحديث")
        self.refresh_btn.clicked.connect(self.load)
        self.save_btn.clicked.connect(self._save)
        actions.addStretch(1)
        actions.addWidget(self.refresh_btn)
        actions.addWidget(self.save_btn)
        root.addLayout(actions)
        root.addStretch(1)

    def load(self):
        self.main.run_async(
            lambda c: c.select("app_update_settings", filters={"id": "eq.true"}, limit=1),
            self._on_loaded,
            args=(self.main.client,),
            busy_label="جاري تحميل إعدادات التحديثات…",
        )

    def _on_loaded(self, rows):
        row = rows[0] if rows else {}
        self.enabled_check.setChecked(bool(row.get("enabled", False)))
        self.latest_version.setText(str(row.get("latest_version") or "2.3.6"))
        self.update_url.setText(str(row.get("update_url") or ""))
        self.message_ar.setPlainText(str(row.get("message_ar") or ""))
        self.message_en.setPlainText(str(row.get("message_en") or ""))
        self.main.status("تم تحميل إعدادات التحديثات")

    def _save(self):
        version = self.latest_version.text().strip()
        url = self.update_url.text().strip()
        if not re.fullmatch(r"\d+(?:\.\d+){1,3}", version):
            QMessageBox.warning(self, "Engo Admin", "اكتب رقم إصدار صحيحًا مثل 2.3.6.")
            return
        parsed_url = urllib.parse.urlparse(url) if url else None
        if url and (parsed_url.scheme.lower() != "https" or not parsed_url.netloc):
            QMessageBox.warning(self, "Engo Admin", "أدخل رابط تحديث صحيحًا يبدأ بـ https://")
            return

        body = {
            "id": True,
            "enabled": self.enabled_check.isChecked(),
            "latest_version": version,
            "update_url": url or None,
            "message_ar": self.message_ar.toPlainText().strip() or None,
            "message_en": self.message_en.toPlainText().strip() or None,
            "updated_at": _now_iso(),
        }

        def save(client):
            existing = client.select(
                "app_update_settings", filters={"id": "eq.true"}, limit=1
            )
            return (
                client.update("app_update_settings", {"id": "eq.true"}, body)
                if existing else client.insert("app_update_settings", body)
            )

        self.main.run_async(
            save,
            lambda _result: self.main.status("تم حفظ إعدادات التحديثات"),
            args=(self.main.client,),
            busy_label="جاري حفظ إعدادات التحديثات…",
        )


# --------------------------------------------------------------------------
# Usage analytics and subscription pricing configuration
# --------------------------------------------------------------------------


def _select_all_pages(client: SupabaseAdminClient, table: str, select: str, order: str,
                      page_size: int = 1000, max_pages: int = 200):
    """Read past Supabase/PostgREST's default 1,000-row response limit safely."""
    rows = []
    for page_number in range(max_pages):
        page = client.select(table, select=select, order=order,
                             limit=page_size, offset=page_number * page_size)
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
    return rows


def fetch_admin_usage(client: SupabaseAdminClient):
    activity = _select_all_pages(client, "user_activity_daily",
        "user_id,device_id,activity_date,active_seconds", "activity_date.desc")
    counters = _select_all_pages(client, "usage_counters",
        "user_id,feature_key,scope_key,used,window_start", "updated_at.desc")
    return {"activity": activity, "counters": counters}


class UsageStatsTab(QWidget):
    def __init__(self, main_window):
        super().__init__(); self.main = main_window
        root=QVBoxLayout(self)
        self.summary=QLabel("الوقت النشط تقديري، ويُسجَّل من فواصل اتصال الجهاز (بحد أقصى 10 دقائق لكل فاصلة).")
        self.summary.setWordWrap(True); root.addWidget(self.summary)
        row=QHBoxLayout(); refresh=QPushButton("تحديث الإحصائيات"); refresh.clicked.connect(self.load)
        row.addStretch(1); row.addWidget(refresh); root.addLayout(row)
        self.table=QTableWidget(0,9)
        self.table.setHorizontalHeaderLabels(["المستخدم", "وقت الاستخدام", "رسائل الشات", "جلسات الصوت", "إنشاء Tags", "وحدات Tags", "الترجمة", "بحث AI", "ملفات/نشاطات أخرى"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        root.addWidget(self.table,1)

    def load(self):
        self.main.run_async(fetch_admin_usage, self._on_loaded, args=(self.main.client,),
                            busy_label="جاري تحميل إحصائيات الاستخدام…")

    @staticmethod
    def _duration(seconds):
        minutes=max(0,int(seconds or 0))//60
        hours, mins=divmod(minutes,60)
        return f"{hours} س {mins} د" if hours else f"{mins} د"

    def _on_loaded(self, result):
        result=result if isinstance(result,dict) else {}
        activity=result.get("activity") or []; counters=result.get("counters") or []
        totals={}; active={}; docs={}
        for row in activity:
            uid=str(row.get("user_id") or "")
            if not uid: continue
            active[uid]=active.get(uid,0)+int(row.get("active_seconds") or 0)
        for row in counters:
            uid=str(row.get("user_id") or ""); key=str(row.get("feature_key") or "")
            if not uid or not key: continue
            totals.setdefault(uid,{})[key]=totals.setdefault(uid,{}).get(key,0)+int(row.get("used") or 0)
            scope=str(row.get("scope_key") or "")
            if key in ("tags","tag_units") and scope: docs.setdefault(uid,set()).add(scope)
        user_ids=set(active)|set(totals)
        ordered=sorted(user_ids,key=lambda uid:active.get(uid,0),reverse=True)
        self.table.setRowCount(len(ordered))
        grand_seconds=sum(active.values())
        self.summary.setText(f"عدد المستخدمين الذين لديهم نشاط مسجل: {len(user_ids)} · إجمالي الوقت المسجل: {self._duration(grand_seconds)} · عدد الملفات التي استُخدمت عليها الوسوم: {sum(len(x) for x in docs.values())}. الوقت تقديري من نبضات الترخيص.")
        for i,uid in enumerate(ordered):
            feats=totals.get(uid,{})
            other=sum(v for k,v in feats.items() if k not in {"text_chat","voice_chat","tags","tag_units","translations","ai_search"})
            values=[self.main.users_index.get(uid,uid),self._duration(active.get(uid,0)),
                    str(feats.get("text_chat",0)),str(feats.get("voice_chat",0)),str(feats.get("tags",0)),
                    f"{feats.get('tag_units',0)} ({len(docs.get(uid,set()))} ملف)",str(feats.get("translations",0)),
                    str(feats.get("ai_search",0)),str(other)]
            for col,value in enumerate(values): self.table.setItem(i,col,QTableWidgetItem(value))
        self.main.status(f"تم تحميل إحصائيات {len(ordered)} مستخدم")


class PricingTab(QWidget):
    PERIODS=(
        ("monthly", "شهري", 1),
        ("quarterly", "ربع سنوي", 3),
        ("semiannual", "نصف سنوي", 6),
        ("annual", "سنوي", 12),
    )
    def __init__(self, main_window):
        super().__init__(); self.main=main_window; self.rows_by_period={}
        root=QVBoxLayout(self)
        note=QLabel("تحكم في وضع إطلاق Engo والأسعار ومدد الاشتراك وصورة QR. عند تفعيل المجاني بلا حدود يحصل كل حساب مسجل على جميع الميزات بلا سقف، ويختفي زر الاشتراك من البرنامج. عند إيقافه يعود تطبيق حدود Free وPremium وتظهر الخطط.")
        note.setWordWrap(True); root.addWidget(note)
        mode_box=QGroupBox("وضع إطلاق البرنامج")
        mode_layout=QHBoxLayout(mode_box)
        self.free_unlimited_check=QCheckBox("تشغيل البرنامج مجانًا وبلا حدود لجميع الحسابات المسجلة")
        self.free_unlimited_check.setChecked(True)
        self.save_mode_btn=QPushButton("حفظ وضع التشغيل")
        self.save_mode_btn.clicked.connect(self._save_runtime_mode)
        mode_layout.addWidget(self.free_unlimited_check,1)
        mode_layout.addWidget(self.save_mode_btn)
        root.addWidget(mode_box)
        self.table=QTableWidget(4,6); self.table.setHorizontalHeaderLabels(["الفترة", "المدة بالشهور", "السعر", "العملة", "متاحة", ""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(40); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)
        qr_group=QGroupBox("طرق الدفع")
        form=QFormLayout(qr_group)
        self.qr_url=QLineEdit(); self.qr_url.setPlaceholderText("https://.../engo-payment-qr.png")
        self.instructions=QTextEdit(); self.instructions.setPlaceholderText("اكتب تعليمات التحويل وطرق الدفع للمستخدم")
        self.instructions.setFixedHeight(90)
        form.addRow("رابط صورة QR:",self.qr_url); form.addRow("تعليمات الدفع:",self.instructions)
        root.addWidget(qr_group)
        buttons=QHBoxLayout(); self.save_settings_btn=QPushButton("حفظ إعدادات الدفع"); self.save_settings_btn.clicked.connect(self._save_settings)
        refresh=QPushButton("تحديث"); refresh.clicked.connect(self.load); buttons.addStretch(1); buttons.addWidget(refresh); buttons.addWidget(self.save_settings_btn); root.addLayout(buttons)

    def load(self):
        def fetch(c):
            return {"prices":c.select("subscription_prices",order="duration_months.asc"),
                    "settings":c.select("subscription_settings",filters={"id":"eq.true"},limit=1),
                    "runtime_settings":c.rpc("get_engo_runtime_settings", {})}
        self.main.run_async(fetch,self._on_loaded,args=(self.main.client,),busy_label="جاري تحميل الأسعار وإعدادات الدفع…")

    def _on_loaded(self,result):
        prices=result.get("prices") or []; self.rows_by_period={str(r.get("billing_period")):r for r in prices}
        runtime=result.get("runtime_settings") or {}
        self.free_unlimited_check.setChecked(bool(runtime.get("free_unlimited_mode", True)) if isinstance(runtime, dict) else True)
        for index,(period,label,months) in enumerate(self.PERIODS):
            existing=self.rows_by_period.get(period,{})
            self.table.setItem(index,0,QTableWidgetItem(label)); self.table.setItem(index,1,QTableWidgetItem(str(existing.get("duration_months",months))))
            price=QLineEdit("" if existing.get("amount") is None else str(existing.get("amount"))); price.setPlaceholderText("0.00")
            currency=QLineEdit(str(existing.get("currency") or "EGP")); enabled=QCheckBox(); enabled.setChecked(bool(existing.get("is_active",True)))
            save=QPushButton("حفظ"); save.clicked.connect(lambda _checked=False,p=period,i=index,m=months:self._save_price(p,i,m))
            self.table.setCellWidget(index,2,price); self.table.setCellWidget(index,3,currency); self.table.setCellWidget(index,4,_centered(enabled)); self.table.setCellWidget(index,5,save)
        settings_rows=result.get("settings") or []
        settings=settings_rows[0] if settings_rows else {}
        self.qr_url.setText(str(settings.get("qr_image_url") or "")); self.instructions.setPlainText(str(settings.get("payment_instructions") or ""))
        self.main.status("تم تحميل إعدادات الاشتراكات")

    def _save_runtime_mode(self):
        enabled = self.free_unlimited_check.isChecked()
        if not enabled:
            answer = QMessageBox.question(
                self, "تفعيل الاشتراكات",
                "سيتم إيقاف الوضع المجاني بلا حدود. ستعود حدود Free وPremium، وسيظهر زر الاشتراك للمستخدمين. هل تريد المتابعة؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.free_unlimited_check.setChecked(True)
                return
        self.main.run_async(
            lambda c: c.rpc("set_engo_free_unlimited_mode", {"p_enabled": enabled}),
            lambda _r: self.main.status("تم تفعيل وضع المجاني بلا حدود" if enabled else "تم تفعيل نظام الاشتراكات والحدود"),
            args=(self.main.client,), busy_label="جاري حفظ وضع التشغيل…",
        )

    def _save_price(self,period,row_index,months):
        price_edit:QLineEdit=self.table.cellWidget(row_index,2); currency_edit:QLineEdit=self.table.cellWidget(row_index,3)
        enabled=_checkbox_in(self.table.cellWidget(row_index,4))
        try: amount=float(price_edit.text().strip() or 0)
        except ValueError:
            QMessageBox.warning(self,"Engo Admin","اكتب سعرًا رقميًا صحيحًا."); return
        if amount<0:
            QMessageBox.warning(self,"Engo Admin","السعر لا يمكن أن يكون سالبًا."); return
        body={"plan_id":"premium","billing_period":period,"duration_months":months,
              "amount":amount,"currency":currency_edit.text().strip().upper() or "EGP","is_active":enabled.isChecked(),"updated_at":_now_iso()}
        def save(c):
            existing=c.select("subscription_prices",filters={"plan_id":"eq.premium","billing_period":f"eq.{period}"},limit=1)
            return c.update("subscription_prices",{"plan_id":"eq.premium","billing_period":f"eq.{period}"},body) if existing else c.insert("subscription_prices",body)
        self.main.run_async(save,lambda _r:self._saved_price(period),args=(self.main.client,),busy_label="جاري حفظ السعر…")

    def _saved_price(self,period):
        self.main.status(f"تم حفظ سعر {period}"); self.load()

    def _save_settings(self):
        body={"id":True,"qr_image_url":self.qr_url.text().strip() or None,
              "payment_instructions":self.instructions.toPlainText().strip() or None,"updated_at":_now_iso()}
        def save(c):
            rows=c.select("subscription_settings",filters={"id":"eq.true"},limit=1)
            return c.update("subscription_settings",{"id":"eq.true"},body) if rows else c.insert("subscription_settings",body)
        self.main.run_async(save,lambda _r:self.main.status("تم حفظ إعدادات QR وطرق الدفع"),args=(self.main.client,),busy_label="جاري حفظ إعدادات الدفع…")


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class AdminMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Engo", "EngoAdminPanel")
        self.client: SupabaseAdminClient | None = None
        self.users_index: dict[str, str] = {}
        self._workers = set()

        self.setWindowTitle("Engo · لوحة تحكم الحسابات والاشتراكات")
        self.resize(1200, 760)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        title = QLabel("Engo Admin Panel")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        self.connection_label = QLabel("غير متصل")
        self.connection_label.setStyleSheet("color:#e07070;")
        settings_btn = QPushButton("إعدادات الاتصال")
        settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(title)
        top_bar.addStretch(1)
        top_bar.addWidget(self.connection_label)
        top_bar.addWidget(settings_btn)
        root.addLayout(top_bar)

        self.tabs = QTabWidget()
        self.users_tab = UsersTab(self)
        self.devices_tab = DevicesTab(self)
        self.payments_tab = PaymentsTab(self)
        self.features_tab = FeaturesTab(self)
        self.usage_tab = UsageStatsTab(self)
        self.pricing_tab = PricingTab(self)
        self.builds_tab = BuildsTab(self)
        self.updates_tab = UpdatesTab(self)
        self.tabs.addTab(self.users_tab, "المستخدمون والاشتراكات")
        self.tabs.addTab(self.devices_tab, "الأجهزة")
        self.tabs.addTab(self.payments_tab, "المدفوعات")
        self.tabs.addTab(self.features_tab, "حدود الميزات")
        self.tabs.addTab(self.usage_tab, "إحصائيات الاستخدام")
        self.tabs.addTab(self.pricing_tab, "الخطط والأسعار")
        self.tabs.addTab(self.builds_tab, "نسخ البرنامج الموثوقة")
        self.tabs.addTab(self.updates_tab, "إعدادات التحديثات")
        root.addWidget(self.tabs, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._try_connect(silent=True)

    # --- connection ----------------------------------------------------
    def _open_settings(self):
        dlg = ConnectionDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save()
            self._try_connect(silent=False)

    def _try_connect(self, silent=False):
        url = str(self.settings.value("supabase_url", "") or "")
        key = str(self.settings.value("service_role_key", "") or "")
        if not url or not key:
            if not silent:
                QMessageBox.information(self, "Engo Admin", "من فضلك أدخل رابط Supabase ومفتاح service_role أولًا.")
            else:
                self._open_settings()
            return
        self.client = SupabaseAdminClient(url, key)

        def on_ok(_res):
            self.connection_label.setText("متصل ✓")
            self.connection_label.setStyleSheet("color:#6dbf8a;")
            self.users_tab.load()
            self.devices_tab.load()
            self.payments_tab.load()
            self.features_tab.load()
            self.pricing_tab.load()
            self.builds_tab.load()
            self.updates_tab.load()

        def on_err(message):
            self.connection_label.setText("فشل الاتصال")
            self.connection_label.setStyleSheet("color:#e07070;")
            QMessageBox.critical(self, "Engo Admin", f"تعذّر الاتصال بـ Supabase:\n{message}")

        self.run_async(self.client.test_connection, on_ok, on_error=on_err, busy_label="جاري الاتصال…")

    # --- shared helpers used by every tab ------------------------------
    def status(self, message):
        self.status_bar.showMessage(message, 6000)

    def run_async(self, fn, on_success, on_error=None, args=(), kwargs=None, busy_label=None):
        if busy_label:
            self.status(busy_label)
        worker = ApiWorker(fn, *args, **(kwargs or {}))
        worker.finished_ok.connect(on_success)
        worker.finished_ok.connect(lambda _r: self._workers.discard(worker))
        err_handler = on_error or (lambda msg: QMessageBox.critical(self, "Engo Admin", msg))
        worker.finished_err.connect(err_handler)
        worker.finished_err.connect(lambda _m: self._workers.discard(worker))
        self._workers.add(worker)  # keep a reference alive until it finishes
        worker.start()
        return worker

    def open_devices_for(self, email):
        self.tabs.setCurrentWidget(self.devices_tab)
        self.devices_tab.set_search(email)

    def open_payments_for(self, email):
        self.tabs.setCurrentWidget(self.payments_tab)
        self.payments_tab.set_search(email)


def main():
    app = QApplication(sys.argv)
    window = AdminMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
