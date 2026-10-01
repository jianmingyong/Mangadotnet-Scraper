class FetchError(Exception):
    """Base class for any fetch related error"""


class NotFoundError(Exception):
    """Base class for series that do not exists"""
