from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from typing import List
import os

# Set up Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['j2'])
)

template = env.get_template('address.yaml.j2')

app = FastAPI()


class Address(BaseModel):
    name: str = Field(..., example="John Doe")
    street: str = Field(..., example="123 Main St")
    city: str = Field(..., example="Springfield")
    state: str = Field(..., example="IL")
    zip: str = Field(..., example="62704", pattern=r"^\d{5}(-\d{4})?$")

class AddressPayload(BaseModel):
    git_repo_url: str
    git_branch: str
    git_path: str
    addresses: List[Address]

@app.post("/address/yaml")
async def addresses_to_yaml(payload: AddressPayload):
    result = {}
    try:
        for address in payload.addresses:
            yaml_str = template.render(address=address.dict())
            # Sanitize name for filename (replace spaces with underscores, lowercase)
            safe_name = address.name.replace(' ', '_').lower()
            filename = f"address-{safe_name}-{address.state}-{address.zip}.yaml"
            result[filename] = yaml_str
        # The following values are available for git logic:
        # payload.git_repo_url, payload.git_branch, payload.git_pathgit 
        return result
    except TemplateError as e:
        raise HTTPException(status_code=500, detail=f"Template rendering error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
