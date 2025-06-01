# app/browser_automation/mvp_selenium_wrapper.py
import time
import os # For path joining in demo
from typing import Optional, Tuple
import base64 # For decoding CDP screenshot
import json # For CDP params if complex, though often not needed directly

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException # Added for stale elements
)
from selenium.webdriver.remote.webelement import WebElement # For type hinting

class MVPSeleniumWrapper:
    def __init__(self, webdriver_path: Optional[str] = None, headless: bool = True): # Defaulting to headless for potential CI
        """
        Initializes the Selenium WebDriver (Chrome).
        :param webdriver_path: Optional path to ChromeDriver. If None, assumes it's in PATH.
        :param headless: If True, runs the browser in headless mode.
        """
        self.driver: Optional[webdriver.Chrome] = None
        try:
            chrome_options = ChromeOptions()
            if headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox") # Common for Docker/CI environments
            chrome_options.add_argument("--disable-dev-shm-usage") # Common for Docker/CI
            chrome_options.add_argument("--window-size=1920,1080") # Standard window size

            if webdriver_path:
                service = ChromeService(executable_path=webdriver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Assumes chromedriver is in PATH
                self.driver = webdriver.Chrome(options=chrome_options)

            # Check if the driver is indeed Chrome, as CDP commands are Chrome-specific
            if self.driver.name != 'chrome':
                print("MVPSeleniumWrapper: WARNING - WebDriver is not Chrome. CDP-based full-page screenshots may not work.")

            self.driver.set_page_load_timeout(30) # Max 30 seconds for page load
            print("MVPSeleniumWrapper: WebDriver initialized successfully.")

        except WebDriverException as e:
            print(f"MVPSeleniumWrapper: Error initializing WebDriver: {e}")
            print("Ensure ChromeDriver is installed, its version matches your Chrome browser, and it's in PATH or path is provided.")
            self.driver = None # Ensure driver is None if init fails
        except Exception as e:
            print(f"MVPSeleniumWrapper: An unexpected error occurred during WebDriver initialization: {e}")
            self.driver = None


    def navigate_to_url(self, url: str) -> bool:
        """
        Navigates the browser to the given url.
        Returns True on success, False on failure.
        """
        if not self.driver:
            print("MVPSeleniumWrapper: Driver not initialized.")
            return False
        try:
            self.driver.get(url)
            print(f"MVPSeleniumWrapper: Navigated to URL: {url}")
            return True
        except TimeoutException:
            print(f"MVPSeleniumWrapper: Timeout while trying to navigate to {url}.")
            return False
        except WebDriverException as e:
            print(f"MVPSeleniumWrapper: Error navigating to URL '{url}': {e}")
            return False
        except Exception as e:
            print(f"MVPSeleniumWrapper: An unexpected error occurred during navigation to '{url}': {e}")
            return False

    def get_page_state(self) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
        """
        Captures the current page state including URL, a viewport screenshot, and the full DOM.
        The screenshot is of the current viewport only.

        Returns:
            Tuple[Optional[str], Optional[bytes], Optional[str]]:
                (current_url, viewport_screenshot_bytes, dom_string).
            Returns (None, None, None) if an error occurs or driver not initialized.
        """
        if not self.driver:
            print("MVPSeleniumWrapper: Driver not initialized.")
            return None, None, None
        try:
            current_url = self.driver.current_url
            # It's good practice to ensure the page has settled a bit before screenshot/DOM capture
            # WebDriverWait(self.driver, 5).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(0.5) # Small fixed delay, more robust waits are better for real apps

            screenshot_bytes = self.driver.get_screenshot_as_png()
            dom_string = self.driver.page_source
            print(f"MVPSeleniumWrapper: Page state captured for URL: {current_url}")
            return current_url, screenshot_bytes, dom_string
        except WebDriverException as e:
            print(f"MVPSeleniumWrapper: Error getting page state: {e}")
            return None, None, None
        except Exception as e:
            print(f"MVPSeleniumWrapper: An unexpected error occurred while getting page state: {e}")
            return None, None, None

    def get_full_page_screenshot_bytes(self) -> Optional[bytes]:
        """
        Attempts to capture a screenshot of the entire scrollable page using Chrome DevTools Protocol (CDP).
        This method is browser-specific and works best with Chrome/Chromium.

        Returns:
            Optional[bytes]: Screenshot bytes (PNG) if successful, None otherwise.
        """
        if not self.driver or self.driver.name != 'chrome':
            print("MVPSeleniumWrapper: Full page screenshot via CDP is only supported for Chrome and driver is not available or not Chrome.")
            return None

        try:
            print("MVPSeleniumWrapper: Attempting full page screenshot via CDP...")
            # 1. Get full page size using Page.getLayoutMetrics
            layout_metrics = self.driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
            # content_size is deprecated, use css_content_size if available, else fallback
            if 'css_content_size' in layout_metrics: # For newer Chrome versions
                full_width = layout_metrics['css_content_size']['width']
                full_height = layout_metrics['css_content_size']['height']
            elif 'content_size' in layout_metrics: # Fallback for older versions
                 full_width = layout_metrics['content_size']['width']
                 full_height = layout_metrics['content_size']['height']
            else: # Fallback for even older versions or different structures
                full_width = layout_metrics['width']
                full_height = layout_metrics['height']


            if full_width == 0 or full_height == 0:
                print("MVPSeleniumWrapper: CDP getLayoutMetrics returned zero width or height. Cannot take full screenshot.")
                return None

            print(f"  CDP: Full page dimensions: {full_width}x{full_height}")

            # 2. Get current device metrics to restore later
            original_metrics = self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": 0, "height": 0, "deviceScaleFactor": 0, "mobile": False
            }) # This call with 0s effectively gets current settings without overriding if it's the first call like this.
               # A more direct way to get original metrics isn't always available, so we capture viewport.

            current_viewport_width = self.driver.get_window_size()['width']
            current_viewport_height = self.driver.get_window_size()['height']
            device_scale_factor = self.driver.execute_script('return window.devicePixelRatio')


            # 3. Set device metrics to full page size
            self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": int(full_width),
                "height": int(full_height),
                "deviceScaleFactor": device_scale_factor, # Use current device scale factor
                "mobile": False,
                # "scale": 1 # Ensure page is not scaled down
            })
            print(f"  CDP: Set device metrics override to full page size.")
            time.sleep(0.5) # Allow page to reflow with new metrics, might need adjustment

            # 4. Capture screenshot of the (now full-sized) viewport
            # `captureBeyondViewport` can be true, but with metrics override, it captures the overridden viewport.
            screenshot_data_base64 = self.driver.execute_cdp_cmd("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True, # Ensure it captures everything within the overridden viewport
                "clip": { # Define the capture area to be the full page
                    "x": 0, "y": 0,
                    "width": full_width, "height": full_height,
                    "scale": 1
                }
            })['data']
            print(f"  CDP: Page.captureScreenshot command executed.")

            # 5. Reset device metrics override
            self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
            # It might be necessary to restore previous viewport if changed, e.g., by resizing window or using setDeviceMetricsOverride again
            # For simplicity, we rely on clearDeviceMetricsOverride for now.
            # A more robust reset might involve:
            # self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            #     "width": current_viewport_width, "height": current_viewport_height,
            #     "deviceScaleFactor": device_scale_factor, "mobile": False
            # })
            print(f"  CDP: Cleared device metrics override.")

            return base64.b64decode(screenshot_data_base64)

        except Exception as e:
            print(f"MVPSeleniumWrapper: Error during CDP full page screenshot: {e}")
            # Attempt to clear metrics override just in case it was set before an error
            try:
                self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
            except:
                pass # Ignore errors during cleanup
            return None


    def fill_text_field(self, xpath: str, text: str, timeout: int = 10) -> bool:
        """
        Finds an element using XPath, clears it, and sends text.
        Returns True on success, False on failure.
        """
        if not self.driver:
            print("MVPSeleniumWrapper: Driver not initialized.")
            return False
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            element = wait.until(EC.visibility_of_element_located((By.XPATH, xpath))) # Ensure visible
            element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath))) # Ensure clickable (often implies interactable)

            element.clear()
            element.send_keys(text)
            print(f"MVPSeleniumWrapper: Filled text field '{xpath}' with '{text[:30]}...'")
            return True
        except TimeoutException:
            print(f"MVPSeleniumWrapper: Timeout finding or interacting with element '{xpath}'.")
            return False
        except NoSuchElementException:
            print(f"MVPSeleniumWrapper: Element not found with XPath '{xpath}'.")
            return False
        except WebDriverException as e:
            print(f"MVPSeleniumWrapper: WebDriver error interacting with field '{xpath}': {e}")
            return False
        except Exception as e:
            print(f"MVPSeleniumWrapper: An unexpected error occurred while filling field '{xpath}': {e}")
            return False


    def click_element(self, xpath: str, timeout: int = 10) -> bool:
        """
        Finds an element using XPath and clicks it.
        Returns True on success, False on failure.
        """
        if not self.driver:
            print("MVPSeleniumWrapper: Driver not initialized.")
            return False
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

            element.click()
            print(f"MVPSeleniumWrapper: Clicked element '{xpath}'")
            return True
        except TimeoutException:
            print(f"MVPSeleniumWrapper: Timeout finding or clicking element '{xpath}'.")
            return False
        except NoSuchElementException:
            print(f"MVPSeleniumWrapper: Element not found with XPath '{xpath}'.")
            return False
        except WebDriverException as e: # Catches ElementClickInterceptedException etc.
            print(f"MVPSeleniumWrapper: WebDriver error clicking element '{xpath}': {e}")
            return False
        except Exception as e:
            print(f"MVPSeleniumWrapper: An unexpected error occurred while clicking element '{xpath}': {e}")
            return False

    def close_browser(self):
        """Closes the browser and quits the driver."""
        if self.driver:
            try:
                self.driver.quit()
                print("MVPSeleniumWrapper: Browser closed and driver quit.")
            except WebDriverException as e:
                print(f"MVPSeleniumWrapper: Error quitting driver: {e}")
            except Exception as e:
                print(f"MVPSeleniumWrapper: An unexpected error occurred while closing browser: {e}")
            finally:
                self.driver = None


if __name__ == '__main__':
    print("--- Running MVP Selenium Wrapper Demo ---")

    # IMPORTANT: For this demo to run locally, you need:
    # 1. Google Chrome browser installed.
    # 2. ChromeDriver downloaded (matching your Chrome version) and either:
    #    a) Placed in a directory included in your system's PATH.
    #    b) Its path provided to MVPSeleniumWrapper(webdriver_path="path/to/chromedriver")
    # 3. The 'test_form.html' file created in the root directory of this project.

    # To run headless (no browser window visible), pass headless=True
    # For local debugging, headless=False is often better.
    # In a CI/headless server environment, headless=True is necessary.
    # The test execution environment for this tool may not have a display, so headless=True is often necessary.
    # For local developer testing, visible browser (headless=False) is usually preferred.
    # This demo will try to run headless by default.

    use_headless_mode = True
    # Set use_headless_mode = False if you are running this locally and want to see the browser.
    # Ensure you have a display environment if running non-headless.
    print(f"Demo will run in {'headless' if use_headless_mode else 'visible'} mode.")

    # Path to your test_form.html - assumes it's in the project root
    # This path needs to be absolute for `file:///` URLs to work reliably.
    # Assuming this script is in app/browser_automation, project_root is two levels up.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_form_path = os.path.join(project_root, "test_form.html")
    # Ensure path is absolute for file:/// URL
    if not os.path.isabs(local_form_path): # Should be absolute already with abspath
        local_form_path = os.path.abspath(local_form_path)
    local_form_url = f"file:///{local_form_path.replace(os.sep, '/')}"

    # Ensure logs directory exists for saving screenshots
    logs_dir = os.path.join(project_root, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    viewport_screenshot_path = os.path.join(logs_dir, "viewport_test.png")
    fullpage_screenshot_path = os.path.join(logs_dir, "fullpage_test.png")
    longpage_viewport_path = os.path.join(logs_dir, "longpage_viewport.png")
    longpage_fullpage_path = os.path.join(logs_dir, "longpage_fullpage.png")


    wrapper = MVPSeleniumWrapper(headless=use_headless_mode)

    if wrapper.driver: # Proceed only if driver initialized successfully
        # Test Case 1: Example.com (simple page, viewport vs full might be similar)
        print("\n--- Test Case 1: example.com (Viewport vs Full) ---")
        if wrapper.navigate_to_url("https://www.example.com"):
            url, viewport_bytes, dom = wrapper.get_page_state()
            if viewport_bytes:
                with open(viewport_screenshot_path, "wb") as f:
                    f.write(viewport_bytes)
                print(f"  Viewport screenshot saved to: {viewport_screenshot_path} ({len(viewport_bytes)} bytes)")

            fullpage_bytes = wrapper.get_full_page_screenshot_bytes()
            if fullpage_bytes:
                with open(fullpage_screenshot_path, "wb") as f:
                    f.write(fullpage_bytes)
                print(f"  Full-page screenshot saved to: {fullpage_screenshot_path} ({len(fullpage_bytes)} bytes)")
            else:
                print("  Failed to capture full-page screenshot for example.com.")
        else:
            print("  Failed to navigate to example.com")

        # Test Case 2: Local HTML form interaction
        print(f"\n--- Test Case 2: Local Test Form Interaction ({local_form_url}) ---")
        if wrapper.navigate_to_url(local_form_url):
            print("  Navigated to local test form.")
            name_xpath = "//input[@id='test_name']"
            fill_success = wrapper.fill_text_field(name_xpath, "MVP User Test")
            print(f"  Fill 'Name' field success: {fill_success}")
            if not use_headless_mode: time.sleep(0.5)

            button_xpath = "//button[@id='test_button']"
            click_success = wrapper.click_element(button_xpath)
            print(f"  Click 'Test Button' success: {click_success}")
            if not use_headless_mode: time.sleep(0.5)

            _, _, dom_after_click = wrapper.get_page_state()
            if dom_after_click and "Button clicked successfully!" in dom_after_click:
                print("  Confirmed button click message in updated DOM.")
        else:
            print(f"  Failed to navigate to local test form. Ensure '{local_form_path}' exists.")

        # Test Case 3: Long Page for Full Screenshot Test
        long_page_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
        print(f"\n--- Test Case 3: Long Page Full Screenshot ({long_page_url}) ---")
        if wrapper.navigate_to_url(long_page_url):
            _, viewport_lp_bytes, _ = wrapper.get_page_state()
            if viewport_lp_bytes:
                with open(longpage_viewport_path, "wb") as f:
                    f.write(viewport_lp_bytes)
                print(f"  Long page viewport screenshot saved to: {longpage_viewport_path} ({len(viewport_lp_bytes)} bytes)")

            fullpage_lp_bytes = wrapper.get_full_page_screenshot_bytes()
            if fullpage_lp_bytes:
                with open(longpage_fullpage_path, "wb") as f:
                    f.write(fullpage_lp_bytes)
                print(f"  Long page full-page screenshot saved to: {longpage_fullpage_path} ({len(fullpage_lp_bytes)} bytes)")
            else:
                print("  Failed to capture full-page screenshot for the long page.")
        else:
            print(f"  Failed to navigate to {long_page_url}")

        wrapper.close_browser()
    else:
        print("Demo aborted: WebDriver did not initialize.")

    # --- Demonstrate get_all_interactable_elements_details (after other tests if browser is still open) ---
    # Re-initialize for a clean test of this specific function if needed, or chain it.
    # For this demo, let's assume the browser from previous tests is closed and we open a new one for this specific test.
    print("\n--- Test Case 4: Get All Interactable Elements ---")
    wrapper_for_details = MVPSeleniumWrapper(headless=use_headless_mode)
    if wrapper_for_details.driver:
        if wrapper_for_details.navigate_to_url(local_form_url): # Use the local form
            print(f"  Navigated to {local_form_url} for detail extraction.")
            all_elements_data = wrapper_for_details.get_all_interactable_elements_details()
            print(f"  Found {len(all_elements_data)} interactable elements on the page.")
            if all_elements_data:
                print("  Details of the first few elements:")
                for i, el_data in enumerate(all_elements_data[:3]): # Print first 3
                    print(f"    Element {i+1}:")
                    print(f"      XPath: {el_data['xpath']}")
                    print(f"      Tag: {el_data['tag_name']}")
                    print(f"      Text: '{el_data['text_content']}'")
                    print(f"      Location: ({el_data['location_x']}, {el_data['location_y']}), Size: ({el_data['width']}x{el_data['height']})")
                    print(f"      Visible: {el_data['is_visible']}")
                    print(f"      Attributes: {el_data['attributes']}")
            else:
                print("  No interactable elements found or extracted.")
        else:
            print(f"  Failed to navigate to {local_form_url} for detail extraction test.")
        wrapper_for_details.close_browser()
    else:
        print("  WebDriver for details test did not initialize.")


    print("\n--- MVP Selenium Wrapper Demo Finished ---")

    # --- Helper for XPath Generation ---
    def _generate_xpath_for_element(self, element: WebElement) -> Optional[str]:
        """
        Generates a robust XPath for a given Selenium WebElement using JavaScript.
        """
        if not self.driver:
            return None
        try:
            # JavaScript function to generate XPath
            # This function is more robust for elements with IDs, otherwise generates full path.
            js_get_xpath = """
            function getPathTo(element) {
                if (element.id !== '') {
                    // Ensure the ID is properly escaped for XPath if it contains quotes
                    let id = element.id;
                    if (id.includes("'") && id.includes('"')) { // Contains both single and double
                        // Fallback to a less specific XPath if ID is problematic, or use concat
                        // For simplicity here, we'll just use the tagName if ID is too complex
                        return element.tagName.toLowerCase();
                    } else if (id.includes("'")) { // Contains single quotes
                        return '//*[@id="' + id + '"]';
                    }
                    // Default: contains double quotes or no quotes
                    return "//*[@id='" + id + "']";
                }
                if (element === document.body) return element.tagName.toLowerCase();

                var ix = 0;
                var siblings = element.parentNode.childNodes;
                for (var i = 0; i < siblings.length; i++) {
                    var sibling = siblings[i];
                    if (sibling === element) {
                        return getPathTo(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        ix++;
                    }
                }
                return null; // Should not happen
            }
            return getPathTo(arguments[0]);
            """
            xpath = self.driver.execute_script(js_get_xpath, element)
            return xpath
        except WebDriverException as e:
            print(f"MVPSeleniumWrapper: Error generating XPath for element: {e}")
            return None
        except Exception as e: # Catch any other unexpected errors
            print(f"MVPSeleniumWrapper: Unexpected error in XPath generation: {e}")
            return None

    # --- New method to extract details of all interactable DOM elements ---
    def get_all_interactable_elements_details(self) -> List[Dict[str, Any]]:
        """
        Finds common interactable elements on the current page and extracts their details,
        including location, size, key attributes, and a generated XPath.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each representing an element.
        """
        if not self.driver:
            print("MVPSeleniumWrapper: Driver not initialized.")
            return []

        print("MVPSeleniumWrapper: Extracting details of all interactable elements...")
        elements_details_list: List[Dict[str, Any]] = []

        # Broad CSS selector for common interactable elements
        # This can be expanded. Using individual find_elements calls and merging might be more robust for complex cases.
        selectors = [
            "input", "textarea", "select", "button", "a[href]",
            '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
            '[role="menuitem"]', '[role="tab"]', '[role="textbox"]', '[role="combobox"]',
            '[role="option"]', '[role="slider"]', '[role="spinbutton"]', '[role="switch"]',
            '[role="treeitem"]'
        ]

        # Using a set to store unique elements found by different selectors
        unique_elements_set = set()
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    unique_elements_set.add(el) # WebElement is hashable
            except WebDriverException as e:
                print(f"MVPSeleniumWrapper: Error finding elements with selector '{selector}': {e}")
                continue

        print(f"  Found {len(unique_elements_set)} potential interactable elements initially.")

        attributes_to_extract = [
            "id", "name", "class", "type", "href", "role", "aria-label",
            "aria-labelledby", "aria-describedby", "value", "placeholder",
            "disabled", "readonly", "checked", "selected" # Added checked/selected
        ]

        count_processed = 0
        for element in unique_elements_set:
            try:
                if not element.is_displayed():
                    # print(f"  Skipping non-visible element: {element.tag_name}") # Can be very verbose
                    continue

                location = element.location
                size = element.size

                # Basic check for valid location/size (element might be hidden in a way is_displayed misses, e.g. 0x0 size)
                if size['width'] == 0 or size['height'] == 0:
                    # print(f"  Skipping element with zero width/height: {element.tag_name}") # Can be verbose
                    continue

                tag_name = element.tag_name.lower()
                text_content = element.text

                attrs = {}
                for attr in attributes_to_extract:
                    try:
                        attr_value = element.get_attribute(attr)
                        if attr_value is not None: # Only store if attribute exists and has a value
                            attrs[attr] = attr_value
                    except StaleElementReferenceException:
                        print(f"MVPSeleniumWrapper: Element became stale while getting attribute '{attr}'. Skipping attribute.")
                        continue # Skip this attribute
                    except Exception as e_attr:
                        print(f"MVPSeleniumWrapper: Error getting attribute '{attr}': {e_attr}")


                xpath = self._generate_xpath_for_element(element)
                if not xpath:
                    print(f"MVPSeleniumWrapper: Could not generate XPath for element {tag_name} with text '{text_content[:30]}...'. Skipping element.")
                    continue # Skip if XPath generation fails, as it's crucial for grounding

                element_data = {
                    "xpath": xpath,
                    "tag_name": tag_name,
                    "text_content": text_content.strip() if text_content else "",
                    "location_x": location['x'],
                    "location_y": location['y'],
                    "width": size['width'],
                    "height": size['height'],
                    "is_visible": True, # Already checked is_displayed
                    "attributes": attrs
                }
                elements_details_list.append(element_data)
                count_processed += 1

            except StaleElementReferenceException:
                print("MVPSeleniumWrapper: Element became stale during processing. Skipping element.")
                continue # Skip this element
            except WebDriverException as e_el:
                print(f"MVPSeleniumWrapper: WebDriverException processing an element: {e_el}. Skipping element.")
                continue
            except Exception as e_gen: # Catch any other unexpected error for one element
                 print(f"MVPSeleniumWrapper: Unexpected error processing an element: {e_gen}. Skipping element.")
                 continue

        print(f"MVPSeleniumWrapper: Extracted details for {len(elements_details_list)} visible and interactable elements.")
        return elements_details_list
