import os
from git import Repo
import tempfile
import requests

# --- Input parameters ---
github_token = os.environ["GITHUB_TOKEN"]
github_repo_url = "https://github.com/codequester/temp-address.git"
new_branch = "feature/my-pr-branch"
file_to_change = "hello.txt"
commit_message = "Add hello.txt from script"
pr_title = "Add hello.txt"
pr_body = "This PR adds hello.txt via GitPython script."

# --- Parse owner and repo name from URL ---
# e.g. https://github.com/your-username/your-repo.git
repo_parts = github_repo_url.rstrip(".git").split("/")
owner = repo_parts[-2]
repo_name = repo_parts[-1]

# --- Insert token into URL for authentication ---
authed_url = github_repo_url.replace(
    "https://", f"https://{github_token}@"
)

# --- Clone repo to temp directory ---
tmp_dir = tempfile.mkdtemp()
print(f"Cloning repo into {tmp_dir}")
repo = Repo.clone_from(authed_url, tmp_dir)

# --- Create new branch ---
repo.git.checkout("-b", new_branch)

# --- Create or modify a file ---
file_path = os.path.join(tmp_dir, file_to_change)
with open(file_path, "w") as f:
    f.write("Hello from GitPython!\n")

# --- Stage and commit the file ---
repo.index.add([file_path])
repo.index.commit(commit_message)

# --- Push the new branch ---
origin = repo.remote(name="origin")
origin.push(refspec=f"{new_branch}:{new_branch}")

print(f"Branch '{new_branch}' pushed to remote.")

# --- Create PR using GitHub API ---
api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
headers = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json"
}
payload = {
    "title": pr_title,
    "head": new_branch,
    "base": "main",
    "body": pr_body
}

print("Creating pull request...")
response = requests.post(api_url, headers=headers, json=payload)

if response.status_code == 201:
    pr_url = response.json()["html_url"]
    print(f"Pull request created: {pr_url}")
else:
    print(f"Failed to create PR: {response.status_code}")
    print(response.text)
