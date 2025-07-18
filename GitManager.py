import os
import requests
import uuid
from fastapi import HTTPException
from git import Repo

class GitManager:
    def __init__(self, repo_url, branch, token, base_dir=None):
        self.repo_url = repo_url
        self.branch = branch
        self.token = token
        self.base_dir = base_dir or os.getcwd()
        self.repo_dir = None
        self.repo = None

    def clone_and_checkout(self):
        import tempfile
        # Insert token into URL for authentication
        authed_url = self.repo_url.replace("https://", f"https://{self.token}@")
        tmpdir = tempfile.TemporaryDirectory()
        self.repo_dir = os.path.join(tmpdir.name, "repo")
        self.tmpdir = tmpdir  # keep reference so it's not GC'd
        self.repo = Repo.clone_from(authed_url, self.repo_dir)
        # Create and checkout branch
        self.repo.git.checkout("-b", self.branch)
        return self.repo_dir

    def add_commit_push(self, path_to_add, commit_msg=None):
        commit_msg = commit_msg or f"Automated commit [{uuid.uuid4()}]"
        self.repo.index.add([path_to_add])
        self.repo.index.commit(commit_msg)
        origin = self.repo.remote(name="origin")
        origin.push(refspec=f"{self.branch}:{self.branch}")

    def get_repo_path(self):
        repo_parts = self.repo_url.rstrip(".git").split("/")
        owner = repo_parts[-2]
        repo_name = repo_parts[-1]
        return f"{owner}/{repo_name}"

    def create_pull_request(self, pr_title, pr_body):
        repo_path = self.get_repo_path()
        pr_api = f"https://api.github.com/repos/{repo_path}/pulls"
        pr_data = {
            "title": pr_title,
            "head": self.branch,
            "base": "main",
            "body": pr_body
        }
        headers = {"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"}
        pr_resp = requests.post(pr_api, json=pr_data, headers=headers)
        if pr_resp.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Failed to create PR: {pr_resp.text}")
        return pr_resp.json()

    def merge_pull_request(self, pr_json, pr_title):
        merge_url = pr_json.get("url") + "/merge"
        headers = {"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"}
        merge_resp = requests.put(merge_url, headers=headers, json={"commit_title": pr_title})
        if merge_resp.status_code in (200, 201):
            return True
        else:
            raise HTTPException(status_code=500, detail=f"Failed to auto-merge PR: {merge_resp.text}")

    def cleanup(self):
        if hasattr(self, 'tmpdir'):
            self.tmpdir.cleanup()
