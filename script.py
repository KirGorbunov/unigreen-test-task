import asyncio
from datetime import datetime, timedelta
import os

import aiohttp
from bs4 import BeautifulSoup


# TODO Возможно!, заменить BeautifulSoup на lxml


START_DATE = "20241002"
END_DATE = "20241010"
REGION = "eur"
BASE_URL = "https://www.atsenergo.ru/nreport"
DIR_NAME = "reports"


def generate_date_range(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    delta = timedelta(days=1)
    dates = []

    while start <= end:
        dates.append(start.strftime("%Y%m%d"))
        start += delta

    return dates


async def get_download_link(session: aiohttp.ClientSession, BASE_URL: str, DATE: str, REGION: str) -> str:
    url = f"{BASE_URL}?rname=big_nodes_prices_pub&region={REGION}&rdate={DATE}"
    async with session.get(url, ssl=False) as response:
        if response.status != 200:
            raise ValueError(f"Не удалось загрузить страницу: {url}, код ответа: {response.status}")

        html_content = await response.text()
        soup = BeautifulSoup(html_content, "html.parser")
        links = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "fid=" in href and "zip" not in href:
                full_link = BASE_URL + href
                links.append(full_link)

        if len(links) == 0:
            raise ValueError(f"Ссылки не найдены для даты {DATE}.")
        elif len(links) > 1:
            raise ValueError(f"Найдено несколько ссылок для даты {DATE}. Ожидалась единственная ссылка.")

        return links[0]


async def download_report(session: aiohttp.ClientSession, url: str, save_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        print(f"Скачивание отчёта с {url}...")

        async with session.get(url, ssl=False) as response:
            if response.status == 200:
                with open(save_path, "wb") as file:
                    file.write(await response.read())
                print(f"Отчёт успешно сохранён в {save_path}")
            else:
                print(f"Не удалось скачать файл, код ответа: {response.status}")
    except Exception as e:
        print(f"Ошибка при скачивании файла: {e}")


async def get_one_report(session: aiohttp.ClientSession, BASE_URL: str, date: str, REGION: str, FILE_PATH: str) -> None:
    report_url = await get_download_link(session, BASE_URL, date, REGION)
    await download_report(session, report_url, FILE_PATH)


async def download_reports_for_dates() -> None:
    dates_to_download = generate_date_range(START_DATE, END_DATE)

    # Создаем сессию aiohttp
    async with aiohttp.ClientSession() as session:
        tasks = []

        for date in dates_to_download:
            FILE_NAME = f"{date}.xlsx"
            FILE_PATH = f"{DIR_NAME}/{FILE_NAME}"

            try:
                tasks.append(get_one_report(session, BASE_URL, date, REGION, FILE_PATH))
            except ValueError as e:
                print(e)

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(download_reports_for_dates())
