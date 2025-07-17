# FastAPI Address to YAML Service

This service exposes a REST API endpoint that accepts US address details as JSON and returns a YAML representation using Jinja2 templating.

## Requirements
- Python 3.8+
- FastAPI
- Uvicorn
- Jinja2
- Pydantic

## Installation
```bash
pip install -r requirements.txt
```

## Running the Service
```bash
uvicorn main:app --reload
```

## API Usage
### Endpoint
`POST /address/yaml`

### Request Body (JSON)
```
{
  "name": "John Doe",
  "street": "123 Main St",
  "city": "Springfield",
  "state": "IL",
  "zip": "62704"
}
```

### Response (YAML, text/plain)
```
name: John Doe
street: 123 Main St
city: Springfield
state: IL
zip: 62704
```

### Error Handling
- Returns `422 Unprocessable Entity` for validation errors.
- Returns `500 Internal Server Error` for template or unexpected errors.
# fastapi_address_yaml
