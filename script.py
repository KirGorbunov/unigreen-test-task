from datetime import datetime, timedelta
import os

from bs4 import BeautifulSoup
import requests
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
START_DATE = "20241002"
END_DATE = "20241010"
REGION = "eur"
BASE_URL = "https://www.atsenergo.ru/nreport"
DIR_NAME = "reports"


def generate_date_range(start_date: str, end_date: str) -> list:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    delta = timedelta(days=1)
    dates = []
    while start <= end:
        dates.append(start.strftime("%Y%m%d"))
        start += delta

    return dates

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

def download_report(url: str, save_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        print(f"Скачивание отчёта с {url}...")
        response = requests.get(url, verify=False, timeout=10)

        if response.status_code == 200:
            with open(save_path, "wb") as file:
                file.write(response.content)
            print(f"Отчёт успешно сохранён в {save_path}")
        else:
            print(f"Не удалось скачать файл, код ответа: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при скачивании файла: {e}")


dates_to_download = generate_date_range(START_DATE, END_DATE)
for date in dates_to_download:
    FILE_NAME = f"{date}.xlsx"
    FILE_PATH = f"{DIR_NAME}/{FILE_NAME}"
    try:
        report_url = get_download_link(BASE_URL, date, REGION)
        download_report(report_url, FILE_PATH)
    except ValueError as e:
        print(e)
