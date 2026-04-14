from playwright.sync_api import Playwright, sync_playwright, expect
from config import insta_username, insta_password
import functools
import time
import os
import json
from datetime import datetime
from bs4 import BeautifulSoup

user_data_list = []
post_data_list = []

API_ENDPOINTS = (
    "https://www.instagram.com/api/graphql",
    "https://www.instagram.com/api/v1",
    "https://www.instagram.com/graphql",
)

def save_user_metadata(user_record: dict):
    with open(user_jsonl_path, "a") as my_file:
        my_file.write(json.dumps(user_record) + '\n')
    return

def save_content_metadata(content_records: list[dict]):
    with open(content_jsonl_path, "a") as my_file:
        for content_record in content_records:
            my_file.write(json.dumps(content_record) + '\n')
    return

def intercept_response(response):
    if not response.request.resource_type == "xhr":
        return None

    url = response.url
    if not any(url.startswith(endpoint) for endpoint in API_ENDPOINTS):
        return None

    data = response.json()

    if data is None:
        return None

    # Extract and print user data to console
    if "data" in data.keys():
        if "user" in data["data"].keys():
            user_data = data["data"]["user"]
            print(user_data)
            save_user_metadata(user_data)
            print("=============================")

    # Extract and print content data to console
    if "data" in data.keys():
        if "xdt_api__v1__feed__user_timeline_graphql_connection" in data["data"].keys():
            if (
                "edges"
                in data["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]
            ):
                edges = data["data"][
                    "xdt_api__v1__feed__user_timeline_graphql_connection"
                ]["edges"]

                content_records = [edge["node"] for edge in edges]
                save_content_metadata(content_records)

                for content_record in content_records:
                    print(content_record)
                    print("=============================")
    return None


def pause_scraper(seconds_before: int, seconds_after: int):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if seconds_before > 0:
                # Sleep before executing logic
                print(f"sleeping {seconds_before} seconds before")
                time.sleep(seconds_before)

            # Execute logic
            result = func(*args, **kwargs)

            if seconds_after > 0:
                # Sleep after executing logic
                print(f"sleeping {seconds_after} seconds after")
                time.sleep(seconds_after)

            return result

        return wrapper

    return decorator


def cookies_expired(auth_json_path: str) -> bool:
    if not os.path.exists(auth_json_path):
        return True

    with open(auth_json_path, "r") as f:
        auth_dict = json.load(f)

    for cookie in auth_dict["cookies"]:
        if datetime.fromtimestamp(cookie["expires"]) < datetime.now():
            return True

    return False


def need_to_log_in(page) -> bool:
    if (
        page.get_by_label("Phone number, username, or email").is_visible()
        and page.get_by_label("Password").is_visible()
        and page.get_by_text("Log in", exact=True).is_visible()
    ):
        return True

    if (
        page.get_by_label("Mobile phone, username or email").is_visible()
        and page.get_by_label("Password").is_visible()
        and page.get_by_text("Log in", exact=True).is_visible()
    ):
        return True

    if (
        page.get_by_label("Mobile number, username or email").is_visible()
        and page.get_by_label("Password").is_visible()
        and page.get_by_text("Log in", exact=True).is_visible()
    ):
        return True

    return False


@pause_scraper(0, 5)
def visit_target_home_page(page, handle: str):
    print(f"visiting home page of @{handle}...")
    seed_home_page_url = f"https://www.instagram.com/{handle}/"
    page.goto(seed_home_page_url)

    time.sleep(5)

    if not page.url == seed_home_page_url:
        raise Exception("Failed to load target home page")

    return


@pause_scraper(5, 10)
def log_in_if_necessary(page, context, auth_json_path: str):
    if need_to_log_in(page):
        print(f"attempting login with account @{insta_username}...")
        # Log in sequence:
        if page.get_by_label("Phone number, username, or email").is_visible():
            page.get_by_label("Phone number, username, or email").fill(insta_username)
        elif page.get_by_label("Mobile number, username or email").is_visible():
            page.get_by_label("Mobile number, username or email").fill(insta_username)
        elif page.get_by_label("Mobile number, username or email").is_visible():
            page.get_by_label("Mobile number, username or email").fill(insta_username)
        else:
            raise Exception("Unexpected layout")

        page.get_by_label("Password").fill(insta_password)
        page.get_by_text("Log in", exact=True).click()

        # store authentication cookie
        context.storage_state(path=auth_json_path)

    else:
        print(f"No need to log in! Skipping...")


def is_content(relative_url: str, handle: str) -> bool:
    if relative_url.startswith(f"/{handle}/p/") or relative_url.startswith(
        f"/{handle}/reel/"
    ):
        return True
    return False


def find_lowest_content(page, handle: str):
    a_tags = page.locator("a")

    for i in range(0, a_tags.count()):
        j = a_tags.count() - 1 - i  # last index first
        elt = a_tags.nth(j)
        if is_content(elt.get_attribute("href"), handle):
            return elt
    return None


@pause_scraper(0, 5)
def scroll_down(page):
    print("scrolling down...")
    page.keyboard.down("PageDown")
    return


@pause_scraper(0, 5)
def scroll_down_smart(lowest_content):
    print("scrolling down...")
    lowest_content.scroll_into_view_if_needed()
    return lowest_content


def run(playwright: Playwright, seed: dict, auth_json_path: str) -> None:
    # initialize:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 800, "height": 600},
        storage_state=auth_json_path if os.path.exists(auth_json_path) else None,
    )
    page = context.new_page()

    page.on("response", intercept_response)

    # Go to landing page
    page.goto("https://www.instagram.com")

    # log in to instagram
    log_in_if_necessary(page, context, auth_json_path)

    # wait until the Home icon is visible
    expect(page.get_by_label("Home")).to_be_visible()

    # Visit the target account's home page:
    visit_target_home_page(page, seed["handle"])

    expect(page.get_by_text(seed["handle"])).to_be_visible()

    # Scroll down
    while True:
        lowest_content = find_lowest_content(page, seed["handle"])
        if lowest_content is None:
            raise (Exception("No posts found in content gallery"))
        scroll_down_smart(lowest_content)


if __name__ == "__main__":
    auth_json_path = os.path.join(
        os.path.dirname(__file__), f"login_cookies_{insta_username}.json"
    )
    seed = {"handle": "eye.on.palestine", "start_date": "2023-10-07"}

    user_jsonl_path = os.path.join(os.path.dirname(__file__), f"{seed['handle']}_user_metadata.jsonl")
    content_jsonl_path = os.path.join(os.path.dirname(__file__), f"{seed['handle']}_content_metadata.jsonl")

    with sync_playwright() as playwright:
        run(playwright, seed, auth_json_path)
