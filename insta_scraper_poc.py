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


def parse_video_urls(video_xml: str) -> list:
    if video_xml is None:
        return []
    soup = BeautifulSoup(video_xml, "xml")
    video_urls = [
        video_url_tag.contents[0] for video_url_tag in soup.find_all("BaseURL")
    ]
    return video_urls


def get_videos_from_content_dict(content_data: dict) -> list:
    videos = []

    if content_data["video_dash_manifest"] is not None:
        videos = parse_video_urls(content_data["video_dash_manifest"])

    if content_data["carousel_media"] is not None:
        for each_item in content_data["carousel_media"]:
            videos += parse_video_urls(each_item)

    return videos


def intercept_response(response):
    if not response.request.resource_type == "xhr":
        return None

    url = response.url
    # if not any(url.starts_with(endpoint) for endpoint in API_ENDPOINTS):
    #     return None
    if not any(url.startswith(endpoint) for endpoint in API_ENDPOINTS):
        return None

    data = response.json()

    # Extract and print user data to console
    if "data" in data.keys():
        if "user" in data["data"].keys():
            user_data = data["data"]["user"]
            print(user_data)
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

                for content_record in content_records:
                    print(content_record)
                    print("=============================")
                    video_urls = get_videos_from_content_dict(content_record)
                    for video_url in video_urls:
                        print(video_url)
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
        and page.get_by_role("button", name="Log in", exact=True).is_visible()
    ):
        # Cookies are not expired but the login layout is showing. Need to log in.
        return True

    if (
        page.get_by_label("Mobile phone, username or email").is_visible()
        and page.get_by_label("Password").is_visible()
        and page.get_by_role("button", name="Log in", exact=True).is_visible()
    ):
        # Cookies are not expired but the login layout is showing. Need to log in.
        return True

    if page.get_by_label("Mobile number, username or email").is_visible() and page.get_by_label("Password").is_visible() and page.get_by_role("button", name="Log in", exact=True).is_visible():
        return True

    # Cookies are not expired and the login layout is not showing. No need to log in.
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
        if page.get_by_label("Phone number, username, or email").count() > 0:
            page.get_by_label("Phone number, username, or email").fill(insta_username)
        elif page.get_by_label("Mobile number, username or email").count() > 0:
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

    # Scroll down
    while True:
        # scroll_down(page)
        lowest_content = find_lowest_content(page, seed["handle"])
        if lowest_content is None:
            raise (Exception("No posts found in content gallery"))
        scroll_down_smart(lowest_content)


if __name__ == "__main__":
    auth_json_path = os.path.join(
        os.path.dirname(__file__), f"login_cookies_{insta_username}.json"
    )
    seed = {"handle": "eye.on.palestine", "start_date": "2026-02-01"}

    with sync_playwright() as playwright:
        run(playwright, seed, auth_json_path)
