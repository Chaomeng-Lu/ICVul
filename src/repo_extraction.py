from datetime import datetime

import pandas as pd
from github import Github
from github.GithubException import BadCredentialsException
from github import RateLimitExceededException
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging


def extract_repo_name_url(commit_urls):
    # Split the input string by ';' and take the first URL
    commit_url = commit_urls.split(';')[0].strip()
    # find'/commit/'
    commit_part = '/commit/'
    if commit_part in commit_url:
        # get url in front of'/commit/'
        repo_name = '/'.join(commit_url.split('/')[3:5])
        repo_url = commit_url.split(commit_part)[0]
        # extracting commit-level data
        if 'github' in repo_url:
            repo_url = repo_url + '.git'
        return repo_url, repo_name
    else:
        raise ValueError("Invalid GitHub commit URL")


def get_github_meta(repo_url, token):
    """
    returns github meta-information of the repo_url
    """
    repo_url = repo_url.replace('.git', '')
    owner, project = repo_url.split('/')[-2], repo_url.split('/')[-1]
    repo_name = '/'.join([owner, project])
    logging.info(f'Processing for repository: {repo_url}')

    git_link = Github(token)
    try:
        git_user = git_link.get_user(owner)
        repo = git_user.get_repo(project)

        meta_row = {'repo_url': repo_url,
                    'repo_name': repo_name,
                    'owner': owner,
                    'description': repo.description,
                    'date_created': repo.created_at,
                    'date_last_push': repo.pushed_at,
                    'homepage': repo.homepage,
                    'repo_language': repo.language,
                    'forks_count': repo.forks,
                    'stars_count': repo.stargazers_count,
                    'size': repo.size,
                    'topics': repo.get_topics(),
                    'open_issues_count': repo.open_issues_count,
                    'total_commits': repo.get_commits().totalCount,
                    'contributors_count': repo.get_contributors().totalCount if not (repo_name == 'torvalds/linux' or repo_name == 'pfsense/FreeBSD-ports' or repo_name == 'ruscur/linux' or repo_name == 'gregkh/linux') else 'Too large, need to check manually!',
                    'releases_count': repo.get_releases().totalCount,
                    'tags_count': repo.get_tags().totalCount,
                    'collecting_date': datetime.now()
                    }
        logging.info(f'Successfully processed for repository: {repo_url}')
    except RateLimitExceededException:
        logging.warning(f'Token Rate limit exceeded for {repo_url}. Waiting for 1 hour before retrying.')
        time.sleep(3600)  # Wait before retrying, the limit of personal token access, 1000 requests per hour
        return get_github_meta(repo_url, token)  # Retry
    except BadCredentialsException as e:
        logging.error(f'Credential problem while accessing GitHub repository {repo_url}: {e}')
        return None
    except Exception as e:
        logging.error(f'Other issues while getting meta-data for GitHub repository {repo_url}: {e}')
        return None
    return meta_row


def nan_list_to_none(lst):
    if len(lst) == 1 and pd.isna(lst[0]):
        return None
    return lst


def fetch_repo_info(repo_urls, token, max_workers):
    """
    Fetch metadata for multiple repository URLs in parallel.
    """
    metadata_list = []
    unreachable_url = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(get_github_meta, url, token): url for url in repo_urls}
        for future in as_completed(future_to_url):
            repo_url = future_to_url[future]
            try:
                meta_dict = future.result()
                if meta_dict is None:
                    unreachable_url.append(repo_url)
                else:
                    metadata_list.append(meta_dict)
            except Exception as e:
                logging.error(f'Error fetching metadata for {repo_url}: {e}')

    return metadata_list, unreachable_url
