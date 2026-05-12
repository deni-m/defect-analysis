import base64
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests
from openai import AzureOpenAI, OpenAI
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parent.parent
APP_PATH = ROOT / "src" / "qa_bugs" / "ui" / "app.py"
TEST_DATA_PATH = ROOT / "data" / "bugs_sample.csv"
BASELINE_PATH = ROOT / "tests" / "baselines" / "ui_homepage_baseline.png"
ARTIFACTS_DIR = ROOT / "tests" / "artifacts"
CURRENT_SHOT_PATH = ARTIFACTS_DIR / "ui_homepage_current.png"
PORT = int(os.getenv("QA_BUGS_E2E_PORT", "8511"))


def _wait_for_streamlit(base_url: str, timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    health_url = f"{base_url}/_stcore/health"
    while time.time() < deadline:
        try:
            resp = requests.get(health_url, timeout=2)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"Streamlit did not become healthy in {timeout_s}s: {health_url}")


def _start_streamlit(csv_path: Path) -> tuple[subprocess.Popen, str]:
    env = os.environ.copy()
    env["QA_BUGS_E2E_INPUT_CSV"] = str(csv_path)
    cmd = [
        "python",
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.headless=true",
        f"--server.port={PORT}",
        "--browser.gatherUsageStats=false",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{PORT}"
    _wait_for_streamlit(base_url)
    return proc, base_url


def _stop_streamlit(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _capture_fullpage_screenshot(url: str, out_path: Path, csv_path: Path) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        raise FileNotFoundError(f"Test data file missing: {csv_path}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1600, "height": 2200})
        page = context.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=120_000)
            page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=60_000)

            # Ensure first screen is actually rendered and visible before any interaction.
            expect(page.get_by_text("QA Bugs Analytics", exact=False).first).to_be_visible(timeout=60_000)
            expect(page.get_by_text("Upload JIRA CSV File", exact=False).first).to_be_visible(timeout=60_000)

            # Ensure the uploader block itself (dropzone area) is visible and settled.
            uploader_block = page.locator("[data-testid='stFileUploaderDropzone']").first
            expect(uploader_block).to_be_visible(timeout=60_000)

            # Wait for the uploader instructions text to confirm the dropzone is fully interactive.
            expect(
                page.locator("[data-testid='stFileUploaderDropzoneInstructions']").first
            ).to_be_visible(timeout=60_000)
            page.wait_for_timeout(750)

            # Verify deterministic test-mode injection is active in UI.
            try:
                page.get_by_text("E2E mode active:", exact=False).first.wait_for(timeout=90_000)
            except PlaywrightTimeoutError as ex:
                page.screenshot(path=str(ARTIFACTS_DIR / "ui_e2e_mode_not_active.png"), full_page=True)
                raise TimeoutError(
                    "Timed out waiting for E2E mode file injection marker in Streamlit UI. "
                    "See tests/artifacts/ui_e2e_mode_not_active.png"
                ) from ex

            # Wait for run button and execute analysis.
            run_button = page.locator("button:visible", has_text="Run Analysis").first
            run_button.wait_for(timeout=120_000)

            # Guard against disabled/inactive button state.
            try:
                expect(run_button).to_be_enabled(timeout=60_000)
            except PlaywrightTimeoutError as ex:
                page.screenshot(path=str(ARTIFACTS_DIR / "ui_run_button_disabled.png"), full_page=True)
                raise TimeoutError(
                    "Run Analysis button stayed disabled after file upload. "
                    "Check mapping/status prompts in UI."
                ) from ex

            # If partial metrics confirmation appears, acknowledge it.
            confirm_checkbox = page.get_by_label("I understand — continue with the remaining metrics")
            if confirm_checkbox.count() > 0:
                confirm_checkbox.first.check()

            run_button.click()

            # Wait for analysis completion signal.
            # The success toast is transient because Streamlit calls st.rerun() right after success,
            # so we also accept stable post-analysis result markers.
            try:
                page.locator("text=Analysis complete!").or_(
                    page.locator("text=Detailed Metrics")
                ).or_(
                    page.locator("text=AI Summary")
                ).or_(
                    page.locator("text=Total Defects")
                ).first.wait_for(timeout=300_000)
            except PlaywrightTimeoutError as ex:
                page.screenshot(path=str(ARTIFACTS_DIR / "ui_analysis_timeout.png"), full_page=True)
                raise TimeoutError(
                    "Timed out waiting for analysis completion/results in Streamlit UI. "
                    "Verify app responsiveness and check tests/artifacts/ui_analysis_timeout.png."
                ) from ex

            # Give one extra beat for final rerender before screenshot.
            page.wait_for_timeout(2500)

            # Streamlit renders inside overflow:hidden containers so full_page=True
            # cannot detect the real content height. Measure it via JS and expand
            # the viewport to the actual height before capturing.
            full_height = page.evaluate(
                "Math.max("
                "  document.body.scrollHeight,"
                "  document.documentElement.scrollHeight,"
                "  document.body.offsetHeight,"
                "  document.documentElement.offsetHeight"
                ")"
            )
            page.set_viewport_size({"width": 1600, "height": max(full_height, 2200)})
            page.wait_for_timeout(500)
            page.screenshot(path=str(out_path), full_page=False)
        finally:
            context.close()
            browser.close()


def _choose_llm_client_and_model():
    # Prefer direct OpenAI if available.
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        model = os.getenv("QA_BUGS_E2E_VISION_MODEL", "gpt-5-mini")
        return OpenAI(api_key=openai_key), model

    # Fall back to Azure OpenAI if configured.
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_endpoint:
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT", os.getenv("QA_BUGS_E2E_VISION_MODEL", "gpt-5-mini"))
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
        client = AzureOpenAI(api_key=azure_key, api_version=api_version, azure_endpoint=azure_endpoint)
        return client, model

    pytest.skip(
        "Missing LLM credentials. Set OPENAI_API_KEY or AZURE_OPENAI_KEY + AZURE_OPENAI_ENDPOINT "
        "to run visual comparison."
    )


def _png_to_data_url(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return {}
    return {}


def _compare_images_with_llm(baseline_path: Path, current_path: Path) -> tuple[bool, str, str]:
    client, model = _choose_llm_client_and_model()

    system = (
        "You are a strict visual regression judge for web app screenshots. "
        "Treat layout shifts, missing sections, broken cards/charts, and major style changes as failures. "
        "Ignore tiny anti-aliasing/font-rendering differences and timestamp-like dynamic values. "
        "Return only compact JSON: {\"pass\": boolean, \"confidence\": number, \"reason\": string}."
    )

    user_content = [
        {"type": "text", "text": "Compare baseline screenshot (image 1) with current screenshot (image 2)."},
        {"type": "text", "text": "Pass only if visually equivalent for E2E regression purposes."},
        {"type": "image_url", "image_url": {"url": _png_to_data_url(baseline_path)}},
        {"type": "image_url", "image_url": {"url": _png_to_data_url(current_path)}},
    ]

    req = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "max_completion_tokens": 500,
    }
    # GPT-5 family can reject temperature; omit it entirely.

    resp = client.chat.completions.create(**req)
    text = (resp.choices[0].message.content or "").strip()
    parsed = _extract_json_object(text)
    passed = bool(parsed.get("pass", False))
    reason = str(parsed.get("reason", "No reason provided"))
    return passed, reason, text


@pytest.mark.e2e
@pytest.mark.live
def test_streamlit_visual_regression_with_llm():
    """Playwright E2E visual regression using bugs_sample.csv and GPT-5-mini image comparison."""
    if not APP_PATH.exists():
        pytest.fail(f"Streamlit app not found: {APP_PATH}")
    if not TEST_DATA_PATH.exists():
        pytest.fail(f"Required test data file not found: {TEST_DATA_PATH}")

    update_baseline = os.getenv("QA_BUGS_E2E_UPDATE_BASELINE", "0") == "1"

    proc = None
    try:
        proc, base_url = _start_streamlit(TEST_DATA_PATH)
        _capture_fullpage_screenshot(base_url, CURRENT_SHOT_PATH, TEST_DATA_PATH)

        if update_baseline:
            BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_bytes(CURRENT_SHOT_PATH.read_bytes())
            pytest.skip(f"Baseline updated: {BASELINE_PATH}")

        if not BASELINE_PATH.exists():
            pytest.fail(
                "Baseline image is missing. Create it by running with "
                "QA_BUGS_E2E_UPDATE_BASELINE=1 once. "
                f"Expected baseline path: {BASELINE_PATH}"
            )

        passed, reason, raw = _compare_images_with_llm(BASELINE_PATH, CURRENT_SHOT_PATH)
        assert passed, (
            "Visual regression check failed. "
            f"Reason: {reason}. "
            f"Baseline: {BASELINE_PATH}. "
            f"Current: {CURRENT_SHOT_PATH}. "
            f"Raw model output: {raw}"
        )
    finally:
        if proc is not None:
            _stop_streamlit(proc)
