import json
from pathlib import Path

from apps.api.main import app


def export_openapi_schema() -> Path:
    schema = app.openapi()
    out_path = Path(__file__).parent / "openapi.json"
    out_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = export_openapi_schema()
    print(f"Exported OpenAPI schema to {p}")
