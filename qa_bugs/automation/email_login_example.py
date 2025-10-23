"""Example Selenium automation: demonstrates a safe login pattern using environment
variables for credentials. This DOES NOT attempt real login by default; it shows
structure and provides helper functions you can adapt.

Usage (PowerShell):
  $env:QA_EMAIL_USER="your_user"; $env:QA_EMAIL_PASSWORD="your_pass"; \
  python -m qa_bugs.automation.email_login_example --url https://example.com/login

For ukr.net freestyle mail portal you'll need to inspect the actual DOM to plug the
right locators (provided below as starting hypotheses). Avoid committing secrets.
"""
from __future__ import annotations

import os
import time
import dataclasses
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


@dataclasses.dataclass
class LoginConfig:
    url: str
    username_env: str = "QA_EMAIL_USER"
    password_env: str = "QA_EMAIL_PASSWORD"
    headless: bool = False
    timeout: int = 20

    def get_credentials(self) -> tuple[str, str]:
        user = os.getenv(self.username_env, "")
        pwd = os.getenv(self.password_env, "")
        if not user or not pwd:
            raise ValueError(
                f"Missing credentials: set {self.username_env} and {self.password_env} environment variables"
            )
        return user, pwd


def build_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    return webdriver.Chrome(ChromeDriverManager().install(), options=opts)


def login_email(cfg: LoginConfig) -> None:
    user, pwd = cfg.get_credentials()
    driver = build_driver(cfg.headless)
    try:
        driver.get(cfg.url)

        wait = WebDriverWait(driver, cfg.timeout)

        # Locators: Replace with accurate ones after inspecting the live page.
        # Hypothetical examples for a login form:
        USERNAME = (By.CSS_SELECTOR, "input[name='login'], input[type='email']")
        PASSWORD = (By.CSS_SELECTOR, "input[name='password'], input[type='password']")
        SUBMIT = (By.CSS_SELECTOR, "button[type='submit'], button.login-button, input[type='submit']")

        # Resolve username field
        username_el = wait.until(lambda d: _first_present(d, USERNAME))
        username_el.clear(); username_el.send_keys(user)

        password_el = wait.until(lambda d: _first_present(d, PASSWORD))
        password_el.clear(); password_el.send_keys(pwd)

        submit_el = wait.until(lambda d: _first_present(d, SUBMIT))
        submit_el.click()

        # Example post-login wait condition (customize): presence of mailbox container
        # Adjust the selector below to something that appears only after successful login.
        post_selector = (By.CSS_SELECTOR, "div.mailbox, div.dashboard, nav[aria-label='Mailbox']")
        wait.until(lambda d: _first_present(d, post_selector))
        print("Login flow completed (post-login element detected).")
    finally:
        # Keep window open a moment for observation (omit in CI)
        time.sleep(2)
        driver.quit()


def _first_present(driver, locator_tuple):
    by, selector = locator_tuple
    matches = driver.find_elements(by, selector)
    for el in matches:
        if el.is_displayed():
            return el
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Safe email login automation example")
    parser.add_argument("--url", required=True, help="Login page URL")
    parser.add_argument("--headless", action="store_true", help="Run headless mode")
    args = parser.parse_args()

    cfg = LoginConfig(url=args.url, headless=args.headless)
    try:
        login_email(cfg)
    except Exception as e:
        print(f"[ERROR] {e}")
        raise
