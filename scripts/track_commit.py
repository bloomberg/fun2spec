# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import requests
import os

def get_commits(owner, repo, github_token=None, per_page=100, max_commits=200):
    """
    Retrieves commit history from a GitHub repository.

    Args:
        owner (str): The owner of the repository.
        repo (str): The name of the repository.
        github_token (str, optional): A GitHub personal access token for authentication. Defaults to None.
        per_page (int, optional): Number of commits to retrieve per page (max 100). Defaults to 100.

    Returns:
        list: A list of commit dictionaries, or None if an error occurs.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"
    params = {'per_page': per_page}
    
    all_commits = []
    page = 1
    while len(all_commits) < max_commits:
        params['page'] = page
        response = requests.get(url, headers=headers, params=params, verify=False)

        if response.status_code == 200:
            commits = response.json()
            if not commits:
                break  # No more commits to fetch
            all_commits.extend(commits)
            page += 1
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    
    return all_commits


def get_commit_diff(owner, repo, commit_sha):
    """
    Retrieves the diff for a specific commit from GitHub.

    Args:
        owner (str): The owner of the repository.
        repo (str): The name of the repository.
        commit_sha (str): The SHA of the commit.

    Returns:
        str: The diff content, or None if an error occurred.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
    headers = {"Accept": "application/vnd.github.diff"}

    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching commit diff: {e}")
        return None

import re

def extract_function_changes(diff_text):
    file_pattern = re.compile(r'diff --git a/(.*) b/\1')
    function_pattern = re.compile(r'^\+(?!.*\-\-\-)(.*?)\s+(\w+)\s*\(', re.MULTILINE)
    
    file_name = None
    changes = {}

    for line in diff_text.splitlines():
        file_match = file_pattern.match(line)
        if file_match:
            file_name = file_match.group(1)
            changes[file_name] = []
        elif file_name:
            function_match = function_pattern.match(line)
            if function_match:
              changes[file_name].append(function_match.group(2))
    return changes

if __name__ == '__main__':
    github_token = os.environ.get("GITHUB_TOKEN")

    commits = get_commits(owner="bloomberg", repo="bde", github_token=github_token, max_commits=200)
    diff = get_commit_diff(owner="bloomberg", repo="bde", commit_sha=commits[-1]["sha"])
    
    if commits:
        print(f"Number of commits: {len(commits)}")
        # Print information about the first commit
        if commits:
            print(f"First commit message: {commits[0]['commit']['message']}")
            print(f"First commit author: {commits[0]['commit']['author']['name']}")
            print(f"First commit date: {commits[0]['commit']['author']['date']}")
    else:
        print("Failed to retrieve commits.")

    # Test for function extraction
    diff_text = """
diff --git a/file1.cpp b/file1.cpp
index 1234567..890abcd 100644
--- a/file1.cpp
+++ b/file1.cpp
@@ -1,4 +1,5 @@
 #include <iostream>
 
+void newFunction1() {}
 int main() {
     std::cout << "Hello, world!" << std::endl;
 }
diff --git a/file2.cpp b/file2.cpp
index 9876543..210fedc 100644
--- a/file2.cpp
+++ b/file2.cpp
@@ -1,4 +1,5 @@
 #include <string>
 
+std::string newFunction2(int x) {
+    return "value";
 }
"""

    function_changes = extract_function_changes(diff_text)
    print(function_changes)
    # Expected output: [('example.py', 'old_function'), ('example.py', 'new_function')]  
        