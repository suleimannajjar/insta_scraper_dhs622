import json
from bs4 import BeautifulSoup
import requests
import os
from config import IMAGE_DIR, VIDEO_DIR, HEADERS

IMAGE_EXTENSIONS = ('.jpg', '.png', '.heic', '.webp')

def get_video_name(post_id: str, video_url: str) -> str:
    video_name = video_url[video_url.rfind('/') + 1:]
    video_name = video_name[:video_name.find('mp4')+len('.mp4')-1]
    video_name = f"{post_id}_{video_name}"
    return video_name

def get_image_name(post_id: str, image_url: str) -> str:
    image_name = image_url[image_url.rfind('/') + 1:]

    found_extension = False
    for extension in IMAGE_EXTENSIONS:
        if image_name.find(extension) != -1:
            found_extension = True
            image_name = image_name[:image_name.find(extension)]
            image_name = f"{post_id}_{image_name}.png"  # force every image type to be PNG

    if not found_extension:
        raise Exception
    return image_name

def load_data(file_path):
    """loads list of dictionaries into memory"""
    data = []
    with open(file_path, "r") as f:
        for line in f:
            data.append(json.loads(line))
    return data

def parse_video_urls(video_xml: str) -> list:
    if video_xml is None:
        return []
    soup = BeautifulSoup(video_xml, "xml")
    video_urls = [video_url_tag.contents[0] for video_url_tag in soup.find_all('BaseURL')]
    video_urls = list(set(video_urls))
    return video_urls

def extract_image_url(image_versions2):
    image_urls = image_versions2['candidates']

    if not isinstance(image_urls, list):
        raise Exception

    if len(image_urls) == 0:
        raise Exception # if this is possible, return None and handle accordingly

    # take first image, it should be the one with the highest resolution
    image_url = image_urls[0]['url']
    return image_url

def extract_images_from_post(post: dict) -> list[dict]:
    post_id = post['id']
    image_urls = []

    if post['image_versions2'] is not None:
        # there is a single image associated with this post
        image_url = extract_image_url(post['image_versions2'])
        image_urls.append(image_url)
    if post['carousel_media'] is not None:
        # there are multiple images... or videos associated with this post
        for each_item in post['carousel_media']:
            if each_item['image_versions2'] is not None:
                image_url = extract_image_url(each_item['image_versions2'])
                image_urls.append(image_url)

    this_post_image_metadata = [
        {
            'post_id': post_id,
            'image_url': image_url
        } for image_url in image_urls
    ]

    return this_post_image_metadata

def extract_videos_from_post(post: dict) -> list[dict]:
    post_id = post['id']
    video_urls = []

    if post['video_dash_manifest'] is not None:
        # there are video URLs listed in video_dash_manifest
        # extract them for scraping
        video_urls += parse_video_urls(post['video_dash_manifest'])

    if post['carousel_media'] is not None:
        # there are video URLs listed in carousel_media
        # extract them for scraping
        for each_item in post['carousel_media']:
            video_urls += parse_video_urls(each_item['video_dash_manifest'])

    this_post_video_metadata = [
        {
            'post_id': post_id,
            'video_url': video_url
        } for video_url in video_urls
    ]

    return this_post_video_metadata

def fetch_images(images: list[dict]) -> None:
    for image in images:
        image_name = get_image_name(post_id=image['post_id'], image_url=image['image_url'])
        image_full_path = os.path.join(IMAGE_DIR, image_name)

        if os.path.exists(image_full_path):
            print("skipping (already downloaded)")
            continue

        print(f"downloading image {image['image_url']}...")
        resp = requests.get(image['image_url'], headers=HEADERS)
        resp.raise_for_status()

        with open(image_full_path, "wb") as binary_file:
            binary_file.write(resp.content)
    return

def fetch_videos(videos: list[dict]) -> None:
    for video in videos:
        video_name = get_video_name(post_id=video['post_id'], video_url=video['video_url'])
        video_full_path = os.path.join(VIDEO_DIR, video_name)

        if os.path.exists(video_full_path):
            print("skipping (already downloaded)")
            continue

        print(f"downloading video {video['video_url']}...")
        resp = requests.get(video['video_url'], headers=HEADERS)
        resp.raise_for_status()

        with open(video_full_path, "wb") as binary_file:
            binary_file.write(resp.content)
    return

if __name__ == "__main__":
    data = load_data("PATH_TO_YOUR_CONTENT_JSONL_FILE")

    for record in data:
        images = extract_images_from_post(record)
        videos = extract_videos_from_post(record)

        fetch_images(images)
        fetch_videos(videos)