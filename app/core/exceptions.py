class AppError(Exception):
    """Base application error."""


class ValidationError(AppError):
    """Raised when user input or state is invalid."""


class DataLoadError(AppError):
    """Raised when a data source cannot be loaded."""


class ChartRenderError(AppError):
    """Raised when a chart cannot be rendered."""

