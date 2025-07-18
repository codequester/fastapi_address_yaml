from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from typing import List
from git import Repo
import os
import requests
import tempfile, uuid
import re

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

def create_pull_request(repo_path, branch, pr_title, pr_body, token):
    pr_api = f"https://api.github.com/repos/{repo_path}/pulls"
    pr_data = {
        "title": pr_title,
        "head": branch,
        "base": "main",
        "body": pr_body
    }
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    pr_resp = requests.post(pr_api, json=pr_data, headers=headers)
    if pr_resp.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Failed to create PR: {pr_resp.text}")
    return pr_resp.json()

def merge_pull_request(pr_json, pr_title, token):
    merge_url = pr_json.get("url") + "/merge"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    merge_resp = requests.put(merge_url, headers=headers, json={"commit_title": pr_title})
    if merge_resp.status_code in (200, 201):
        return True
    else:
        raise HTTPException(status_code=500, detail=f"Failed to auto-merge PR: {merge_resp.text}")

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
    github_token = os.environ["GITHUB_TOKEN"]

    if not github_token:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN environment variable not set.")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            # --- Insert token into URL for authentication ---
            authed_url = payload.git_repo_url.replace(
                "https://", f"https://{github_token}@"
            )
            print(f"Cloning repo into {repo_dir}")
            # Clone the repo
            repo = Repo.clone_from(authed_url, repo_dir)

            # git = repo.git
            # # Fetch all branches
            # repo.remotes.origin.fetch()
            # # Try to checkout the branch, or create it from origin/main if it doesn't exist
            # try:
            #     git.checkout(payload.git_branch)
            # except GitCommandError:
            #     git.checkout('-b', payload.git_branch, 'origin/main')

            # --- Create new branch ---
            repo.git.checkout("-b", payload.git_branch)
            # Write YAML files
            target_dir = os.path.join(repo_dir, payload.git_path)
            for address in payload.addresses:
                rendered = render_templates_for_address(address, os.path.join(os.path.dirname(__file__), 'templates'))
                write_rendered_files(rendered, target_dir)
                result.update(rendered)

            # Stage, commit, and push
            commit_msg = f"Add address YAML files [{uuid.uuid4()}]"
            repo.index.add([payload.git_path])
            repo.index.commit(commit_msg)
            origin = repo.remote(name="origin")
            origin.push(refspec=f"{payload.git_branch}:{payload.git_branch}")
            print(f"Branch '{payload.git_branch}' pushed to remote.")

            # Parse owner and repo name from URL
            repo_parts = payload.git_repo_url.rstrip(".git").split("/")
            owner = repo_parts[-2]
            repo_name = repo_parts[-1]
            repo_path = f"{owner}/{repo_name}"
            pr_title = f"Add address YAML files [{uuid.uuid4()}]"
            pr_body = "Automated PR for address YAML files."
            pr_json = create_pull_request(repo_path, payload.git_branch, pr_title, pr_body, github_token)
            pr_url = pr_json.get("html_url")
            merged = False
            if not payload.approvalNeeded:
                merged = merge_pull_request(pr_json, pr_title, github_token)
            return {"yaml_files": result, "pull_request_url": pr_url, "auto_merged": merged}
    except TemplateError as e:
        raise HTTPException(status_code=500, detail=f"Template rendering error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
