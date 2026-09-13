"""
Utility modules for METRIC ETa pipeline.

Provides logging, validation, and exception handling utilities.
"""

from .exceptions import (
    AnchorPixelError,
    CalibrationError,
    ComputationError,
    ConfigurationError,
    DataInputError,
    DTCalibrationError,
    EnergyBalanceError,
    GeoTIFFWriteError,
    METRICError,
    OutputError,
    PipelineError,
    RadiationBalanceError,
    ScenePathError,
    VisualizationError,
    WeatherDataError,
    create_error_context,
    handle_exception,
)
from .logger import Logger, get_progress_bar, log_execution_time, log_step
from .validation import (
    check_albedo_range,
    check_cloud_coverage,
    check_energy_balance,
    check_et_range,
    check_for_nodata,
    check_ndvi_range,
    check_temperature_range,
    validate_calibration_params,
    validate_input_data,
    validate_scene_path,
    validate_weather_data,
)

__all__ = [
    # Logger
    "Logger",
    "log_step",
    "get_progress_bar",
    "log_execution_time",

    # Validation
    "validate_scene_path",
    "validate_weather_data",
    "validate_calibration_params",
    "check_ndvi_range",
    "check_albedo_range",
    "check_temperature_range",
    "check_et_range",
    "check_for_nodata",
    "check_cloud_coverage",
    "check_energy_balance",
    "validate_input_data",

    # Exceptions
    "METRICError",
    "DataInputError",
    "ScenePathError",
    "WeatherDataError",
    "CalibrationError",
    "AnchorPixelError",
    "DTCalibrationError",
    "ComputationError",
    "RadiationBalanceError",
    "EnergyBalanceError",
    "OutputError",
    "GeoTIFFWriteError",
    "VisualizationError",
    "ConfigurationError",
    "PipelineError",
    "handle_exception",
    "create_error_context"
]
