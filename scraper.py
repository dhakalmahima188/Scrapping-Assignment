

import csv
import time
import requests
from bs4 import BeautifulSoup

class BookScraper:
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
    DEFAULT_RETRIES = 3
    DEFAULT_DELAY = 1

    def __init__(self, output_file: str = "output.csv"):
        self.output_file = output_file
        self.session = requests.Session()

    def get_page(self, url: str):
        for attempt in range(1, self.DEFAULT_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                response.encoding = 'utf-8'
                return BeautifulSoup(response.text, "html.parser")
            except requests.RequestException as e:
                print(f"Attempt {attempt}/{self.DEFAULT_RETRIES} failed for {url}: {e}")
                if attempt < self.DEFAULT_RETRIES:
                    time.sleep(self.DEFAULT_DELAY * attempt)
        return None

    def parse_books(self, soup: BeautifulSoup):
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
            rating = self.RATING_MAP.get(rating_word, 0)

            relative_href = title_tag["href"] if title_tag else ""
            clean_href = relative_href.replace("../", "")
            url = self.BASE_URL + clean_href

            books.append({
                "title": title,
                "price": price,
                "rating": rating,
                "url": url,
            })

        return books

    def get_next_page_url(self, soup: BeautifulSoup):
        next_btn = soup.select_one("li.next > a")
        if not next_btn:
            return None
        return self.BASE_URL + next_btn["href"]

    def scrape_all(self) -> list[dict]:
        all_books = []
        current_url = self.START_URL
        page_num = 1
        start_time = time.time()

        while current_url:
            print(f"Scraping page {page_num}: {current_url}")
            soup = self.get_page(current_url)

            if soup is None:
                print(f"Could not fetch page {page_num}. Stopping.")
                break

            books = self.parse_books(soup)
            all_books.extend(books)
            print(f"{len(books)} books collected  in the loop. (total: {len(all_books)})")

            current_url = self.get_next_page_url(soup)
            page_num += 1
            time.sleep(0.5)

        elapsed = time.time() - start_time
        print(f"\nTask completed: {len(all_books)} books scraped in {elapsed:.1f}s")
        return all_books

    def write_csv(self, books: list[dict]) :
        fieldnames = ["title", "price", "rating", "url"]
        with open(self.output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(books)
        print(f"\nExtracted {len(books)} records to {self.output_file}")

    def run(self) -> None:
        books = self.scrape_all()
        print(f"Fetched {len(books)} records. Writing to {self.output_file}...")
        self.write_csv(books)
        print("Done!")


if __name__ == "__main__":
    BookScraper().run()
