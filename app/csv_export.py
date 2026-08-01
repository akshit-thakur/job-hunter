import csv
from io import StringIO
from typing import Any

from app.models import APPLICATION_FIELDS
from app.queries import all_applications

# Spreadsheet apps (Excel, Sheets) treat cells starting with these characters
# as formulas. Prefix with a tab to neutralize without altering the visible
# value, so free-text fields (company, notes) can't trigger formula execution.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _escape_formula(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "\t" + value
    return value


def applications_csv() -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=APPLICATION_FIELDS)
    writer.writeheader()
    for row in all_applications():
        writer.writerow(
            {field: _escape_formula(row.get(field)) for field in APPLICATION_FIELDS}
        )
    return output.getvalue()
