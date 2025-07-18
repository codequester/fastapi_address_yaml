from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from typing import List
from git import Repo
import os
import tempfile, uuid
import re
from GitManager import GitManager

# Set up Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['j2'])
)



def render_templates_for_address(address, templates_dir):
    rendered = {}
    for fname in os.listdir(templates_dir):
        if fname.endswith('.j2'):
            template = env.get_template(fname)
            # Derive output filename: replace <field> in template filename with address fields
            out_fname = fname[:-3]  # Remove .j2
            # Find <field> patterns
            matches = re.findall(r'<(\w+)>', out_fname)
            for field in matches:
                value = str(getattr(address, field, ''))
                out_fname = out_fname.replace(f'<{field}>', value)
            # Optionally, replace spaces with underscores and lowercase for name
            if 'name' in matches:
                value = str(getattr(address, 'name', '')).replace(' ', '_').lower()
                out_fname = out_fname.replace(str(getattr(address, 'name', '')), value)
            yaml_content = template.render(address=address.dict())
            rendered[out_fname] = yaml_content
    return rendered

def write_rendered_files(rendered_dict, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    for yaml_filename, yaml_content in rendered_dict.items():
        file_path = os.path.join(target_dir, yaml_filename)
        with open(file_path, "w") as f:
            f.write(yaml_content)

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
    approvalNeeded: bool = True

@app.post("/address/yaml")
async def addresses_to_yaml(payload: AddressPayload):
    result = {}
    pr_url = None
    try:
        github_token = os.environ["GITHUB_TOKEN"]
        if not github_token:
            raise HTTPException(status_code=500, detail="GITHUB_TOKEN environment variable not set.")

        # Initialize GitManager
        git_mgr = GitManager(
            repo_url=payload.git_repo_url,
            branch=payload.git_branch,
            token=github_token
        )
        repo_dir = git_mgr.clone_and_checkout()
        target_dir = os.path.join(repo_dir, payload.git_path)
        for address in payload.addresses:
            rendered = render_templates_for_address(address, os.path.join(os.path.dirname(__file__), 'templates'))
            write_rendered_files(rendered, target_dir)
            result.update(rendered)
        commit_msg = f"Add address YAML files [{uuid.uuid4()}]"
        git_mgr.add_commit_push(payload.git_path, commit_msg)
        pr_title = commit_msg
        pr_body = "Automated PR for address YAML files."
        pr_json = git_mgr.create_pull_request(pr_title, pr_body)
        pr_url = pr_json.get("html_url")
        merged = False
        if not payload.approvalNeeded:
            merged = git_mgr.merge_pull_request(pr_json, pr_title)
        git_mgr.cleanup()
        return {"yaml_files": result, "pull_request_url": pr_url, "auto_merged": merged}
    except TemplateError as e:
        raise HTTPException(status_code=500, detail=f"Template rendering error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
