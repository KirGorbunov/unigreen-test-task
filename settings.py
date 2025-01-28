from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    START_DATE: str
    END_DATE: str
    REGION: str
    BASE_URL: str
    DIR_NAME: str
    TARGET_REGION: str
    HOURS_START: int
    HOURS_END: int
    PRICE_FOR_CALCULATED: str

    @property
    def OUTPUT_FILE_CSV(self) -> str:
        return f"average_prices_{self.START_DATE}-{self.END_DATE}.csv"

    @property
    def OUTPUT_FILE_XLS(self) -> str:
        return f"average_prices_{self.START_DATE}-{self.END_DATE}.xls"

    @property
    def OUTPUT_FILE_XML(self) -> str:
        return f"average_prices_{self.START_DATE}-{self.END_DATE}.xml"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
