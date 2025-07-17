from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from typing import List
from git import Repo
import os
import requests
import tempfile, uuid


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
            os.makedirs(target_dir, exist_ok=True)
            for address in payload.addresses:
                yaml_str = template.render(address=address.dict())
                safe_name = address.name.replace(' ', '_').lower()
                filename = f"address-{safe_name}-{address.state}-{address.zip}.yaml"
                file_path = os.path.join(target_dir, filename)
                with open(file_path, "w") as f:
                    f.write(yaml_str)
                result[filename] = yaml_str

            # # Stage, commit, and push
            # repo.git.add(payload.git_path)

            # --- Stage and commit the file ---
            commit_msg = f"Add address YAML files [{uuid.uuid4()}]"
            repo.index.add([payload.git_path])
            repo.index.commit(commit_msg)

            # --- Push the new branch ---
            origin = repo.remote(name="origin")
            origin.push(refspec=f"{payload.git_branch}:{payload.git_branch}")
            print(f"Branch '{payload.git_branch}' pushed to remote.")

            #repo.remotes.origin.push(refspec=f"{payload.git_branch}:{payload.git_branch}")
           
            # Create PR via GitHub API

            #repo_path = payload.git_repo_url.rstrip(".git").split(":")[-1].replace("https://github.com/", "")

            # --- Parse owner and repo name from URL ---
            # e.g. https://github.com/your-username/your-repo.git
            repo_parts = payload.git_repo_url.rstrip(".git").split("/")
            owner = repo_parts[-2]
            repo_name = repo_parts[-1]

            pr_api = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
            pr_title = f"Add address YAML files [{uuid.uuid4()}]"
            pr_body = "Automated PR for address YAML files."
            pr_data = {
                "title": pr_title,
                "head": payload.git_branch,
                "base": "main",
                "body": pr_body
            }
            headers = {
                "Authorization": f"token {github_token}", 
                "Accept": "application/vnd.github.v3+json"
            }
            print("Creating pull request...")
            pr_resp = requests.post(pr_api, json=pr_data, headers=headers)
            if pr_resp.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail=f"Failed to create PR: {pr_resp.text}")
            pr_url = pr_resp.json().get("html_url")
        return {"yaml_files": result, "pull_request_url": pr_url}
    except TemplateError as e:
        raise HTTPException(status_code=500, detail=f"Template rendering error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
