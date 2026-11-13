"""
Module: savers.py

Utilities to save CSV and YAML files, with error handling and flexible interfaces using PyYAML.
"""
import csv
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

__all__ = [
    "save_csv",
    "save_yaml",
    "save_file",
    "save_ids",
]

# Configure a module-level logger
logger = logging.getLogger(__name__)


def save_csv(
    rows: List[Dict[str, Any]],
    csv_path: Union[str, Path],
    fieldnames: Optional[List[str]] = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> None:
    """
    Save a list of dictionaries to a CSV file.

    Args:
        rows: List of dictionaries representing rows.
        csv_path: Path to write the CSV file.
        fieldnames: List of column names; if None, inferred from first row.
        delimiter: Delimiter used in the CSV file (default: ',').
        encoding: Text encoding of the file (default: 'utf-8').

    Raises:
        ValueError: If no fieldnames can be determined.
        csv.Error: If there is an issue writing the CSV.
    """
    path = Path(csv_path)
    if not fieldnames:
        if rows:
            fieldnames = list(rows[0].keys())
        else:
            logger.error("No field names provided for CSV save: %s", path)
            raise ValueError("fieldnames must be provided if rows are empty.")

    try:
        with path.open("w", encoding=encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
    except csv.Error:
        logger.exception("Error writing CSV file: %s", path)
        raise


def save_ids(
    config_file: Union[str, Path],
    channels_with_ids: List[Any]
) -> None:
    """
    Load an existing YAML config, update channel URLs and IDs, and write it back.

    Args:
        config_file: Path to the YAML config file.
        channels_with_ids: List of (url, id) pairs.
    """
    cfg_path = Path(config_file)

    # Load existing config as YAML
    try:
        content = cfg_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        logger.exception("Error loading YAML config: %s", cfg_path)
        raise

    # Extract URLs and IDs from pairs
    urls = [u for u, _ in channels_with_ids]
    ids = [i for _, i in channels_with_ids]
    data['channels'] = urls
    data['channel_ids'] = ids

    # Write back to YAML preserving key order
    try:
        with cfg_path.open('w', encoding='utf-8') as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                indent=2
            )
    except yaml.YAMLError:
        logger.exception("Error writing YAML file: %s", cfg_path)
        raise

    logger.info(f"Updated {config_file} with {len(urls)} channels and IDs")


def save_yaml(
    data: Any,
    yaml_path: Union[str, Path],
    encoding: str = "utf-8",
    **yaml_kwargs,
) -> None:
    """
    Save data to a YAML file using PyYAML.

    Args:
        data: Python object to serialize.
        yaml_path: Path to write the YAML file.
        encoding: Text encoding of the file (default: 'utf-8').
        **yaml_kwargs: Passed to yaml.safe_dump (e.g., default_flow_style).

    Raises:
        yaml.YAMLError: If there is an issue serializing the data.
    """
    path = Path(yaml_path)
    try:
        content = yaml.safe_dump(
            data,
            **yaml_kwargs,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )
        path.write_text(content, encoding=encoding)
    except yaml.YAMLError:
        logger.exception("Error writing YAML file: %s", path)
        raise


def save_file(
    data: Any,
    file_path: Union[str, Path],
    **kwargs,
) -> None:
    """
    Save data based on file extension.

    Supported formats:
        - CSV ('.csv')
        - YAML ('.yaml', '.yml')

    Args:
        data: Data to save (list of dicts for CSV, any for YAML).
        file_path: Destination file path.
        **kwargs: Passed to the underlying save function.

    Raises:
        ValueError: If the file extension is unsupported.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        return save_csv(data, path, **kwargs)
    if ext in (".yaml", ".yml"):  
        return save_yaml(data, path, **kwargs)

    logger.error("Unsupported file format for saving: %s", ext)
    raise ValueError(f"Unsupported file format for saving: {ext}")


if __name__ == "__main__":
    # Basic demonstration
    rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    config = {"app": {"version": "1.0", "debug": True}}

    try:
        save_file(rows, "./demos/demo_out.csv")
        logger.info("CSV saved to demo_out.csv")
    except Exception as err:
        logger.error(err)

    try:
        save_file(config, "./demos/demo_out.yaml")
        logger.info("YAML saved to demo_out.yaml")
    except Exception as err:
        logger.error(err)