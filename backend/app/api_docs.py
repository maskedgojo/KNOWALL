"""Serve the static, versioned OpenAPI spec and interactive Swagger UI.

No new Flask extension is required. The UI JS/CSS are loaded from a pinned
CDN release; an internet connection is needed for the interactive page.
"""
import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template_string

api_docs_bp = Blueprint("api_docs", __name__)


@api_docs_bp.get("/openapi.json")
def openapi_spec():
    path = Path(__file__).with_name("openapi.json")
    with path.open("r", encoding="utf-8") as file:
        spec = json.load(file)
    return jsonify(spec)


@api_docs_bp.get("/docs")
def swagger_ui():
    return render_template_string("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KNOWALL · API Documentation</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {
      SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        persistAuthorization: false,
        validatorUrl: null,
        withCredentials: true
      });
    };
  </script>
</body>
</html>""")
