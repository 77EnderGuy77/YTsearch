"""
Module: loaders.py

Utilities to load CSV and YAML files, with error handling and a unified interface.
"""
import csv
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Union

__all__ = [
    "load_csv",
    "load_yaml",
    "load_config",
    "load_file",
]

# Configure a module-level logger
logger = logging.getLogger(__name__)


def load_csv(
    csv_path: Union[str, Path],
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> List[Dict[str, Any]]:
    """
    Load a CSV file into a list of dictionaries.

    Args:
        csv_path: Path to the CSV file.
        delimiter: Field delimiter (default ',').
        encoding: File encoding (default 'utf-8').

    Returns:
        List of rows as dictionaries.

    Raises:
        FileNotFoundError: If the file does not exist.
        csv.Error: If parsing fails.
    """
    path = Path(csv_path)
    if not path.exists():
        logger.error("CSV file not found: %s", path)
        raise FileNotFoundError(f"CSV file not found: {path}")

    try:
        with path.open("r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            return list(reader)
    except csv.Error as e:
        logger.exception("Error reading CSV file: %s", path)
        raise


def load_yaml(
    yaml_path: Union[str, Path],
    encoding: str = "utf-8",
) -> Any:
    """
    Load a YAML file and return its parsed content.

    Args:
        yaml_path: Path to the YAML file.
        encoding: File encoding (default 'utf-8').

    Returns:
        Parsed YAML content (dict, list, etc.).

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If parsing fails.
    """
    path = Path(yaml_path)
    if not path.exists():
        logger.error("YAML file not found: %s", path)
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        content = path.read_text(encoding=encoding)
        return yaml.safe_load(content)
    except yaml.YAMLError:
        logger.exception("Error parsing YAML file: %s", path)
        raise


def load_config(
    config_path: Union[str, Path],
    encoding: str = "utf-8",
) -> Any:
    """
    Load a configuration file based on its extension.

    Supports:
      - YAML ('.yaml', '.yml')

    Args:
        config_path: Path to the config file.
        encoding: File encoding (default 'utf-8').

    Returns:
        Parsed configuration data.

    Raises:
        ValueError: If the file extension is unsupported.
    """
    path = Path(config_path)
    ext = path.suffix.lower()

    if ext in (".yaml", ".yml"):
        return load_yaml(path, encoding=encoding)
    else:
        logger.error("Unsupported config format: %s", ext)
        raise ValueError(f"Unsupported config format: {ext}")


def load_file(
    file_path: Union[str, Path],
    **kwargs,
) -> Any:
    """
    Load a file based on its extension.

    Supported formats:
      - CSV ('.csv')
      - YAML ('.yaml', '.yml')

    Args:
        file_path: Path to the file.
        **kwargs: Passed to the underlying loader (e.g., delimiter for CSV).

    Returns:
        Parsed file content.

    Raises:
        ValueError: If the file extension is unsupported.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        return load_csv(path, **kwargs)
    if ext in (".yaml", ".yml"):
        return load_yaml(path, **kwargs)
    else:
        logger.error("Unsupported file format: %s", ext)
        raise ValueError(f"Unsupported file format: {ext}")


if __name__ == "__main__":
    # Demonstration:
    sample_csv = Path("./demos/sample.csv")
    sample_yaml = Path("./demos/config.yaml")

    try:
        rows = load_file(sample_csv, delimiter=',')
        print("CSV data:", rows)
    except Exception as e:
        logger.error(e)

    try:
        cfg = load_file(sample_yaml)
        print("YAML config:", cfg)
    except Exception as e:
        logger