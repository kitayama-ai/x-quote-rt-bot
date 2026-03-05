"""
X Auto Post System — 引用元ツイートの画像ダウンロード

SocialData API のレスポンスから画像URLを抽出し、
一時ファイルとしてダウンロードする。投稿時にアップロードして添付。
"""
import os
import tempfile
import requests
from pathlib import Path


def extract_image_urls(tweet_data: dict) -> list[str]:
    """
    ツイートデータから画像URLを抽出する。

    SocialData (v1.1互換) 形式:
        tweet["extended_entities"]["media"][*]["media_url_https"]
    または:
        tweet["entities"]["media"][*]["media_url_https"]

    Args:
        tweet_data: SocialData / X API レスポンスのツイートデータ

    Returns:
        画像URLのリスト (最大4枚)
    """
    urls: list[str] = []

    # extended_entities を優先（高解像度画像）
    media_list = (
        tweet_data.get("extended_entities", {}).get("media", [])
        or tweet_data.get("entities", {}).get("media", [])
    )

    for media in media_list:
        if media.get("type") != "photo":
            continue
        url = media.get("media_url_https") or media.get("media_url", "")
        if url:
            # 高画質版を取得
            if "?" not in url:
                url = f"{url}?format=jpg&name=large"
            urls.append(url)

    return urls[:4]  # Twitter の最大画像数


def download_image(url: str, timeout: int = 30) -> str | None:
    """
    画像URLをダウンロードして一時ファイルのパスを返す。

    Args:
        url: 画像URL
        timeout: タイムアウト秒数

    Returns:
        一時ファイルのパス。失敗時はNone。
    """
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        if resp.status_code != 200:
            print(f"  ⚠️ 画像ダウンロード失敗: {resp.status_code} ({url[:60]})")
            return None

        # Content-Type から拡張子を推定
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "gif" in content_type:
            ext = ".gif"
        elif "webp" in content_type:
            ext = ".webp"

        # 一時ファイルに書き出し
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name

    except Exception as e:
        print(f"  ⚠️ 画像ダウンロードエラー: {e}")
        return None


def download_tweet_images(tweet_data: dict, max_images: int = 1) -> list[str]:
    """
    ツイートデータから画像をダウンロードし、一時ファイルパスのリストを返す。

    Args:
        tweet_data: ツイートデータ (SocialData形式)
        max_images: ダウンロードする最大画像数 (デフォルト1)

    Returns:
        一時ファイルパスのリスト
    """
    urls = extract_image_urls(tweet_data)
    if not urls:
        return []

    paths: list[str] = []
    for url in urls[:max_images]:
        path = download_image(url)
        if path:
            paths.append(path)

    return paths


def cleanup_temp_images(paths: list[str]) -> None:
    """一時ファイルを削除する。"""
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
