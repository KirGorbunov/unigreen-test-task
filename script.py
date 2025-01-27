from bs4 import BeautifulSoup
import requests
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
DATE = "20250127"
REGION = "eur"
BASE_URL = "https://www.atsenergo.ru/nreport"


def get_download_link(BASE_URL: str, DATE: str, REGION: str) -> str:
    url = f"{BASE_URL}?rname=big_nodes_prices_pub&region={REGION}&rdate={DATE}"
    response = requests.get(url, verify=False, timeout=10)
    if response.status_code != 200:
        raise ValueError(f"Не удалось загрузить страницу: {url}, код ответа: {response.status_code}")
    html_content = response.text
    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "fid=" in href and "zip" not in href:
            full_link = BASE_URL + href
            links.append(full_link)
    if len(links) == 0:
        raise ValueError("Ссылки не найдены.")
    elif len(links) > 1:
        raise ValueError("Найдено несколько ссылок. Ожидалась единственная ссылка.")

    return links[0]

result = get_download_link(BASE_URL, DATE, REGION)
