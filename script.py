import asyncio
from datetime import datetime, timedelta
import logging
from pathlib import Path

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd

from logger_config import setup_logger
from settings import settings


logger = setup_logger(__name__, "reports.log", level=logging.INFO)


def create_directories() -> None:
    """
    Создание директорий для хранения отчетов.
    """
    Path(settings.DOWNLOAD_REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.AVERAGE_REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"Папки {settings.DOWNLOAD_REPORTS_DIR} и {settings.AVERAGE_REPORTS_DIR} "
                f"успешно проверены или созданы.")


def generate_date_list(start_date: str, end_date: str) -> list[str]:
    """
    Генерирует список дат от start_date до end_date в формате день-месяц-год.
    """
    start = datetime.strptime(start_date, "%d-%m-%Y")
    end = datetime.strptime(end_date, "%d-%m-%Y")
    delta = timedelta(days=1)
    dates = []

    while start <= end:
        dates.append(start.strftime("%d-%m-%Y"))
        start += delta

    return dates


async def get_download_link(session: aiohttp.ClientSession, date: str) -> str | None:
    """
    Получает ссылку для скачивания отчета по указанной дате.
    """
    date = datetime.strptime(date, "%d-%m-%Y").strftime("%Y%m%d")
    # На сайте АТС Сибирь лежит вместе с Дальним Востоком
    # https://www.atsenergo.ru/nreport?rname=big_nodes_prices_pub&region=sib&rdate=20250105
    # Поэтому регион для ДВ для этой страницы будет Сибирь:
    if settings.PRICE_ZONE == "dv":
        ZONE = "sib"
    else:
        ZONE = settings.PRICE_ZONE
    url = f"{settings.BASE_URL}?rname=big_nodes_prices_pub&region={ZONE}&rdate={date}"
    async with session.get(url, ssl=False) as response:
        if response.status != 200:
            logger.error(f"Не удалось загрузить страницу: {url}, код ответа: {response.status}")
            return None

        html_content = await response.text()
        soup = BeautifulSoup(html_content, "html.parser")
        links = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Чтобы правильно забрать ДВ, проверяем что в названии файла на сайте есть dv:
            file_name = a_tag.get_text(strip=True)
            if "fid=" in href and "zip" not in href and settings.PRICE_ZONE in file_name:
                full_link = settings.BASE_URL + href
                links.append(full_link)

        if len(links) == 0:
            logger.error(f"Ссылки не найдены для даты {date}.")
            return None
        elif len(links) > 1:
            logger.error(f"Найдено несколько ссылок для даты {date}. Ожидалась единственная ссылка.")
            return None

        return links[0]


async def download_report(session: aiohttp.ClientSession, url: str, save_path: str) -> None:
    """
    Скачивает отчет по ссылке.
    """
    try:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        async with session.get(url, ssl=False) as response:
            if response.status == 200:
                async with aiofiles.open(save_path, "wb") as file:
                    await file.write(await response.read())
                logger.info(f"Отчёт успешно сохранён в {save_path}")
            else:
                logger.error(f"Не удалось скачать файл с {url}, код ответа: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла с {url}: {e}")


async def get_one_report(session: aiohttp.ClientSession, date: str, file_path: str) -> None:
    """
    Получает ссылку на отчет и скачивает файл.
    """
    report_url = await get_download_link(session, date)
    await download_report(session, report_url, file_path)


async def download_reports_for_dates() -> list[str]:
    """
    Асинхронно скачивает отчеты для всех дат.
    """
    dates_to_download = generate_date_list(settings.START_DATE, settings.END_DATE)
    downloaded_files = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        logger.info(f"Запуск скачивания отчётов для {len(dates_to_download)} дат.")

        for date in dates_to_download:
            file_name = f"{settings.PRICE_ZONE}_{date}.xls"
            file_path = Path(settings.DOWNLOAD_REPORTS_DIR) / file_name

            if file_path.exists():
                logger.info(f"Файл {file_name} уже существует, пропускаем скачивание.")
                downloaded_files.append(str(file_path))
                continue

            tasks.append(get_one_report(session, date, str(file_path)))
            downloaded_files.append(str(file_path))

        await asyncio.gather(*tasks)

    logger.info(f"Скачивание завершено, всего файлов: {len(downloaded_files)}.")
    return downloaded_files


def extract_avg_price_from_report(file_path: str, date: str) -> dict[str, float | None]:
    """
    Извлекает среднюю цену из одного отчета.
    """
    try:
        sheet_names = [str(hour) for hour in range(settings.HOURS_START, settings.HOURS_END+1)]
        all_sheets = pd.read_excel(file_path, sheet_name=sheet_names, skiprows=2)
        combined_data = pd.DataFrame()

        for sheet_name, sheet_data in all_sheets.items():
            try:
                filtered_df = sheet_data[sheet_data["Субъект РФ"] == settings.TARGET_REGION]
                combined_data = pd.concat([combined_data, filtered_df], ignore_index=True)
            except Exception as e:
                logger.error(f"Ошибка обработки листа {sheet_name} в файле {file_path}: {e}")

        if not combined_data.empty:
            avg_price = combined_data[settings.PRICE_FOR_CALCULATED].mean()
            return {"Дата": date, f"Среднее значение по параметру {settings.PRICE_FOR_CALCULATED}": avg_price}
        else:
            return {"Дата": date, f"Среднее значение по параметру {settings.PRICE_FOR_CALCULATED}": None}

    except Exception as e:
        logger.error(f"Ошибка обработки файла {file_path}: {e}")
        return {"Дата": date, f"Среднее значение по параметру {settings.PRICE_FOR_CALCULATED}": None}


def generating_reports(downloaded_files: list[str]) -> None:
    """
    Генерирует отчеты на основе средних цен.
    """
    results = []

    for file in downloaded_files:
        file_path = Path(file)
        date = file_path.stem.split("_")[1]
        report_result = extract_avg_price_from_report(file, date)
        results.append(report_result)

    results_df = pd.DataFrame(results)

    results_df["Дата"] = pd.to_datetime(results_df["Дата"], format="%d-%m-%Y").dt.strftime("%d.%m.%Y")

    csv_path = Path(settings.AVERAGE_REPORTS_DIR) / settings.OUTPUT_FILE_CSV
    xls_path = Path(settings.AVERAGE_REPORTS_DIR) / settings.OUTPUT_FILE_XLS
    xml_path = Path(settings.AVERAGE_REPORTS_DIR) / settings.OUTPUT_FILE_XML

    results_df.to_csv(csv_path, index=False, encoding="utf-8")
    results_df.to_excel(xls_path, index=False, engine="openpyxl")
    # В XML не должно быть пробелов и других знаков, поэтому меняем их на нижнее подчеркивание:
    results_df.columns = results_df.columns.str.replace(r"[^\w]", "_", regex=True)
    results_df.to_xml(xml_path, index=False, encoding="utf-8")
    logger.info(f"Результаты успешно сохранены в файлы: {csv_path}, {xls_path}, {xml_path}")


if __name__ == "__main__":
    logger.info("Начало выполнения скрипта.")
    create_directories()
    downloaded_files = asyncio.run(download_reports_for_dates())
    generating_reports(downloaded_files)
    logger.info("Работа скрипта завершена.")
