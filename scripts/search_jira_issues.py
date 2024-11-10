#!/usr/bin/env python3

import http.client
import urllib.parse
import os
import base64
import json
import uuid
import sys

jira_auth_username: str = os.getenv("JIRA_AUTH_USERNAME", "")
jira_auth_password: str = os.getenv("JIRA_AUTH_TOKEN_PASSWORD", "")

jira_organization: str = os.getenv("JIRA_ORG_NAME", "")

jira_jql: str = os.getenv("JIRA_JQL", "")

jira_jql_max_results: int = int(os.getenv("JIRA_JQL_MAX_RESULTS", 20))

temp_directory = os.getenv("alfred_workflow_cache", "/tmp")

# read the first argument
first_arg = sys.argv[1] if len(sys.argv) > 1 else None
first_arg = first_arg.strip() if first_arg else None

def search_issues_jql(jql: str):
    auth = base64.b64encode(f"{jira_auth_username}:{jira_auth_password}".encode('utf-8'))
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    'Authorization': 'Basic ' + auth.decode('utf-8'),
    }
    payload = json.dumps({
    "expand": "names",
    "fields": [
        "id",
        "priority",
        "summary",
        "progress",
        "status",
        "issuetype"
    ],
    "maxResults": jira_jql_max_results,
    "jql":  jira_jql
    })

    conn = http.client.HTTPSConnection(jira_organization + ".atlassian.net")
    conn.request("POST", "/rest/api/3/search/jql", payload, headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return json.loads(data)

def read_issue_type_cache_map() -> dict[str, str]:
    if not os.path.exists(temp_directory):
        os.makedirs(temp_directory)

    # Dict issuetype id to icon url
    issue_type_cache_filepath = temp_directory + '/issue_type_cache'
    if os.path.exists(issue_type_cache_filepath):
        with open(issue_type_cache_filepath, 'r') as file:
            # read line by line , split by ':' and create a dict
            issue_type_cache = {}
            for line in file.readlines():
                parts = line.split(':')
                icon_file_path = parts[1].strip()
                if os.path.exists(icon_file_path):
                    issue_type_cache[parts[0]] = parts[1]
            return issue_type_cache
    else:
        return {}

def write_issue_type(issuetype_id: str, icon_file_path: str):
    # write the issuetype id and icon file path to the end of the file
    issue_type_cache_filepath = temp_directory + '/issue_type_cache'
    with open(issue_type_cache_filepath, 'a') as file:
        file.write(f"{issuetype_id}:{icon_file_path}")

def download_image_to_temp(issuetype_id: str, url: str):
    # Parse the URL
    parsed_url = urllib.parse.urlparse(url)

    # Set up the connection and request
    conn = http.client.HTTPSConnection(parsed_url.netloc)
    conn.request("GET", parsed_url.path + "?" + parsed_url.query)

    # Get the response
    response = conn.getresponse()

    if response.status == 200:
        # Get Content-Type and map to file extensions
        content_type = response.getheader("Content-Type")
        extension_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "image/webp": ".webp"
        }

        # Determine file extension based on content type, default to .img if unknown
        file_extension = extension_map.get(content_type.split(";")[0], ".jpg")

        # Generate a unique filename in {temp_directory}
        file_name = f"{temp_directory}/{issuetype_id}{file_extension}"

        # Write the image data to the temp file
        with open(file_name, 'wb') as file:
            file.write(response.read())

        return file_name
    else:
        return None

    conn.close()

def build_reponse(jira_jqrs_response: dict, issuetype_icon_cache: dict) -> str:

    for issue in jira_jqrs_response.get('issues', []):
        fields = issue.get('fields', {})
        issuetype = fields.get('issuetype', {})
        iconUrl = issuetype.get('iconUrl')
        issuetype_id = issuetype.get('id')

        if issuetype_id not in issuetype_icon_cache:
            issutetype_icon_path = download_image_to_temp(issuetype_id, iconUrl)
            if issutetype_icon_path:
                write_issue_type(issuetype_id, issutetype_icon_path)
                issuetype_icon_cache[issuetype_id] = issutetype_icon_path

    items = []
    for issue in jira_jqrs_response.get('issues', []):
        fields = issue.get('fields', {})
        issuetype = fields.get('issuetype', {})
        issuetype_id = issuetype.get('id')
        title = fields.get('summary')
        key = issue.get('key')

        # filter the issues based on the first argument
        # fzf search is
        if first_arg:
            match_in_title = first_arg.lower() in title.lower()
            match_in_key = first_arg.lower() in key.lower()
            if not match_in_title and not match_in_key:
                continue

        element = {
                'title': title,
                'subtitle': key,
                'arg': 'https://' + jira_organization + '.atlassian.net/browse/' + key
        }
        if issuetype_id in issuetype_icon_cache:
            element['icon'] = { 'path': issuetype_icon_cache[issuetype_id] }
        items.append(element)

    response = {
        'items': items
    }

    # return the List of issues
    return json.dumps(response)


issuetype_icon_cache = read_issue_type_cache_map()

json_data = search_issues_jql(jira_jql)

response_str = build_reponse(json_data, issuetype_icon_cache)

# return the List of issues
print(response_str)
