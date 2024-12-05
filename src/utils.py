import pandas as pd
import re



# Function to extract the first repo URL and store all hashes in a list
def process_multiple_urls(reference_urls):
    git_url2 = r'(?P<repo>(https|http):\/\/github\.com\/[^\/]+\/[^\/]+)\/commit\/(?P<hash>\w+)(\?[^#]*)?(#.*)?'

    urls = reference_urls.split(';')  # Split the string by semicolons
    repo_url = None
    hash_codes = []

    for i, url in enumerate(urls):
        match = re.match(git_url2, url)
        if match:
            # Keep the first repo URL encountered
            if repo_url is None:
                repo_url = match.group('repo').replace(r'http:', r'https:')
            hash_codes.append(match.group('hash'))

    # Return the first repo URL and a list of hashes
    return pd.Series([repo_url, hash_codes])