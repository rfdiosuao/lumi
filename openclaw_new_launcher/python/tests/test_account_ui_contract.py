from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LICENSE_PAGE = os.path.join(REPO_ROOT, "src", "components", "license", "LicensePage.tsx")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")
STARTUP_CACHE_FILE = os.path.join(REPO_ROOT, "src", "services", "startupCache.ts")


class AccountUiContractTests(unittest.TestCase):
    def test_license_page_exposes_inline_email_code_login_register_and_logout(self) -> None:
        with open(LICENSE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("密码登录", source)
        self.assertIn("邮箱注册", source)
        self.assertIn("发送验证码", source)
        self.assertIn("验证并登录", source)
        self.assertIn("accountApi.sendEmailCode", source)
        self.assertIn("purpose: authMode === 'register' ? 'register' : 'login'", source)
        self.assertIn("accountApi.loginWithEmailCode", source)
        self.assertIn("accountApi.register", source)
        self.assertIn("邮箱验证码", source)
        self.assertIn("退出登录", source)

    def test_subscription_entry_is_native_and_keeps_purchase_external(self) -> None:
        with open(LICENSE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("订阅", source)
        self.assertIn("余额", source)
        self.assertIn("套餐", source)
        self.assertIn("到期", source)
        self.assertIn("打开订阅页", source)
        self.assertIn("data-native-subscription-dashboard", source)
        self.assertIn("data-subscription-external-fallback", source)
        self.assertIn("账户与余额", source)
        self.assertIn("套餐方案", source)
        self.assertIn("SUBSCRIPTION_PLANS", source)
        self.assertNotIn("<iframe", source)
        self.assertNotIn("订阅页已在当前页面打开", source)
        self.assertIn("accountApi.subscription", source)
        self.assertIn("purchaseUrl", source)

    def test_subscription_opening_guides_login_and_rejects_localhost_urls(self) -> None:
        with open(LICENSE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("safeSubscriptionUrl", source)
        self.assertIn("isLocalSubscriptionUrl", source)
        self.assertIn("handleOpenSubscription", source)
        self.assertIn("请先登录中转站账号", source)
        self.assertIn("订阅页地址不可用", source)
        self.assertIn("当前网络不可用", source)
        self.assertIn("navigator.onLine === false", source)
        self.assertIn("localhost", source)
        self.assertIn("127.0.0.1", source)
        self.assertIn("DEFAULT_ACCOUNT_CENTER_URL", source)
        self.assertIn("`${DEFAULT_BASE_URL}/wallet`", source)
        self.assertIn("parsed.pathname.replace(/\\/+$/, '') === '/topup'", source)
        self.assertNotIn("`${DEFAULT_BASE_URL}/topup`", source)

    def test_account_api_exposes_register_and_subscription(self) -> None:
        with open(API_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("register: (params", source)
        self.assertIn("api('/api/account/register', 'POST'", source)
        self.assertIn("subscription: ()", source)
        self.assertIn("api('/api/account/subscription')", source)

    def test_account_page_uses_cached_safe_snapshot_before_manual_refresh(self) -> None:
        with open(LICENSE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(STARTUP_CACHE_FILE, "r", encoding="utf-8") as handle:
            cache_source = handle.read()

        self.assertIn("loadCachedAccount", page_source)
        self.assertIn("saveCachedAccount", page_source)
        self.assertIn("accountCacheUsable", page_source)
        self.assertIn("LOOM_ACCOUNT_CACHE_KEY", cache_source)
        self.assertIn("sanitizeAccountForCache", cache_source)
        self.assertIn("delete safe.tokenMasked", cache_source)
        self.assertIn("delete safe.gatewayBaseUrl", cache_source)
        self.assertNotIn("已显示上一次账号快照", page_source)
        self.assertNotIn("LoggedInPanel", page_source)


if __name__ == "__main__":
    unittest.main()
