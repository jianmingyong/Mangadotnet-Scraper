class FetchError(Exception):
    """Base class for any fetch related error"""


class SeriesNotFoundError(FetchError):
    """Base class for series that do not exists"""
