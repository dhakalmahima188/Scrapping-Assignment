

import csv
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/catalogue/"
START_URL = "https://books.toscrape.com/catalogue/page-1.html"

RATING_MAP = {
    "Zero": 0,
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}

OUTPUT_FILE = "output.csv"


def get_page(url: str, retries: int = 3, delay: float = 1.0) -> Optional[BeautifulSoup]:
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            print(f"  [warn] Attempt {attempt}/{retries} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(delay * attempt)
    return None


def parse_books(soup: BeautifulSoup) -> list[dict]:
    books = []
    articles = soup.select("article.product_pod")

    for article in articles:
        title_tag = article.select_one("h3 > a")
        title = title_tag["title"] if title_tag else ""

        price_tag = article.select_one("p.price_color")
        price_text = price_tag.text.strip() if price_tag else "0"
        price = float("".join(c for c in price_text if c.isdigit() or c == "."))

        rating_tag = article.select_one("p.star-rating")
        rating_word = rating_tag["class"][1] if rating_tag else "Zero"
        rating = RATING_MAP.get(rating_word, 0)


        relative_href = title_tag["href"] if title_tag else ""
        clean_href = relative_href.replace("../", "")
        url = BASE_URL + clean_href

        books.append({
            "title": title,
            "price": price,
            "rating": rating,
            "url": url,
        })

    return books


def get_next_page_url(soup: BeautifulSoup) -> Optional[str]:
    next_btn = soup.select_one("li.next > a")
    if not next_btn:
        return None
    return BASE_URL + next_btn["href"]


def scrape_all() -> list[dict]:
    all_books = []
    current_url = START_URL
    page_num = 1

    while current_url:
        print(f"Scraping page {page_num}: {current_url}")
        soup = get_page(current_url)

        if soup is None:
            print(f"  [error] Could not fetch page {page_num}. Stopping.")
            break

        books = parse_books(soup)
        all_books.extend(books)
        print(f"  -> {len(books)} books collected (total: {len(all_books)})")

        current_url = get_next_page_url(soup)
        page_num += 1
        time.sleep(0.5) 

    return all_books


def write_csv(books: list[dict], filepath: str) -> None:
    fieldnames = ["title", "price", "rating", "url"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(books)
    print(f"\nWrote {len(books)} records to {filepath}")


if __name__ == "__main__":
    books = scrape_all()
    print(f"Fetched  {len(books)} records. Writing to {OUTPUT_FILE}...")
    write_csv(books, OUTPUT_FILE)
    print("Done!")
