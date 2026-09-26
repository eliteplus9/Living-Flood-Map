"""Data loading utilities.

Keep data I/O here so frontends can load the same formats.
"""
from typing import Union
import pandas as pd


def load_data(path: str = "data/main_contestant.csv") -> pd.DataFrame:
    """Load the default dataset from disk.

    Args:
        path: Relative path to the CSV file containing at least a `tweet` column.

    Returns:
        A pandas DataFrame.
    """
    df = pd.read_csv(path)
    return df


def read_uploaded_csv(uploaded_file) -> pd.DataFrame:
    """Read a user-uploaded CSV file (e.g. from Streamlit's file_uploader).

    Args:
        uploaded_file: A file-like object (supports pd.read_csv).

    Returns:
        A pandas DataFrame.
    """
    return pd.read_csv(uploaded_file)
