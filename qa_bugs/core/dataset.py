import pandas as pd
import pytz

class Dataset:
    def __init__(self, df: pd.DataFrame, timezone: str = 'UTC'):
        self.df = df.copy()
        self.tz = pytz.timezone(timezone)
