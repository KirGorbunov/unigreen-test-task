import asyncio
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
import pandas as pd

from logger_config import setup_logger


logger = setup_logger(__name__, "reports.log", level=logging.INFO)


START_DATE = "20241009"
END_DATE = "20241010"
REGION = "eur"
BASE_URL = "https://www.atsenergo.ru/nreport"
DIR_NAME = "reports"
TARGET_REGION = "Республика Бурятия"
HOURS_START = 2
HOURS_END = 16
HOURS_RANGE = range(HOURS_START, HOURS_END)
OUTPUT_FILE_CSV = f"average_prices_{START_DATE}-{END_DATE}.csv"
OUTPUT_FILE_XLS = f"average_prices_{START_DATE}-{END_DATE}.xls"
OUTPUT_FILE_XML = f"average_prices_{START_DATE}-{END_DATE}.xml"
PRICE_FOR_CALCULATED = "Равновесная узловая цена, руб./МВт∙ч"


def generate_date_range(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    delta = timedelta(days=1)
    dates = []

    while start <= end:
        dates.append(start.strftime("%Y%m%d"))
        start += delta

    return dates


async def get_download_link(session: aiohttp.ClientSession, BASE_URL: str, DATE: str, REGION: str) -> str | None:
    url = f"{BASE_URL}?rname=big_nodes_prices_pub&region={REGION}&rdate={DATE}"
    async with session.get(url, ssl=False) as response:
        if response.status != 200:
            logger.error(f"Не удалось загрузить страницу: {url}, код ответа: {response.status}")
            return None

        html_content = await response.text()
        soup = BeautifulSoup(html_content, "html.parser")
        links = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "fid=" in href and "zip" not in href:
                full_link = BASE_URL + href
                links.append(full_link)

        if len(links) == 0:
            logger.error(f"Ссылки не найдены для даты {DATE}.")
            return None
        elif len(links) > 1:
            logger.error(f"Найдено несколько ссылок для даты {DATE}. Ожидалась единственная ссылка.")
            return None

        return links[0]


async def download_report(session: aiohttp.ClientSession, url: str, save_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        async with session.get(url, ssl=False) as response:
            if response.status == 200:
                with open(save_path, "wb") as file:
                    file.write(await response.read())
            else:
                logger.error(f"Не удалось скачать файл с {url}, код ответа: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла с {url}: {e}")


async def download_reports_for_dates() -> list[str]:
    dates_to_download = generate_date_range(START_DATE, END_DATE)
    downloaded_files = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        logger.info(f"Запуск скачивания отчётов для {len(dates_to_download)} дат.")

        for date in dates_to_download:
            FILE_NAME = f"{date}.xlsx"
            FILE_PATH = f"{DIR_NAME}/{FILE_NAME}"

            if os.path.exists(FILE_PATH):
                logger.info(f"Файл {FILE_NAME} уже существует, пропускаем скачивание.")
                downloaded_files.append(FILE_PATH)
                continue

            tasks.append(download_report(session, await get_download_link(session, BASE_URL, date, REGION), FILE_PATH))
            downloaded_files.append(FILE_PATH)

        await asyncio.gather(*tasks)

    logger.info(f"Скачивание завершено, всего файлов: {len(downloaded_files)}.")
    return downloaded_files


def extract_avg_price_from_report(file_path: str, date: str) -> dict[str, float | None]:
    try:
        sheet_names = [str(hour) for hour in range(HOURS_START, HOURS_END)]
        all_sheets = pd.read_excel(file_path, sheet_name=sheet_names, skiprows=2)
        combined_data = pd.DataFrame()

        for sheet_name, sheet_data in all_sheets.items():
            try:
                filtered_df = sheet_data[sheet_data["Субъект РФ"] == TARGET_REGION]
                combined_data = pd.concat([combined_data, filtered_df], ignore_index=True)
            except Exception as e:
                logger.error(f"Ошибка обработки листа {sheet_name} в файле {file_path}: {e}")

        if not combined_data.empty:
            avg_price = combined_data[PRICE_FOR_CALCULATED].mean()
            return {"Дата": date, f"Среднее значение по параметру {PRICE_FOR_CALCULATED}": avg_price}
        else:
            return {"Дата": date, f"Среднее значение по параметру {PRICE_FOR_CALCULATED}": None}

    except Exception as e:
        logger.error(f"Ошибка обработки файла {file_path}: {e}")
        return {"Дата": date, f"Среднее значение по параметру {PRICE_FOR_CALCULATED}": None}


def generating_reports(downloaded_files: list[str]) -> None:
    results = []

    for file in downloaded_files:
        file_path = Path(file)
        date = file_path.stem
        report_result = extract_avg_price_from_report(file, date)
        results.append(report_result)

    results_df = pd.DataFrame(results)

    results_df["Дата"] = pd.to_datetime(results_df["Дата"], format="%Y%m%d").dt.strftime("%d.%m.%Y")

    results_df.to_csv(OUTPUT_FILE_CSV, index=False, encoding="utf-8")
    results_df.to_excel(OUTPUT_FILE_XLS, index=False, engine="openpyxl")
    # Формат XML не поддерживает пробелы и некоторые другие символы -> заменяем их на нижнее подчеркивание:
    results_df.columns = results_df.columns.str.replace(r"[^\w]", "_", regex=True)
    results_df.to_xml(OUTPUT_FILE_XML, index=False, encoding="utf-8")
    logger.info("Результаты успешно сохранены в файлы: "
                f"{OUTPUT_FILE_CSV}, {OUTPUT_FILE_XLS}, {OUTPUT_FILE_XML}")


if __name__ == "__main__":
    logger.info("Начало выполнения скрипта.")
    downloaded_files = asyncio.run(download_reports_for_dates())
    generating_reports(downloaded_files)
    logger.info("Работа скрипта завершена.")
