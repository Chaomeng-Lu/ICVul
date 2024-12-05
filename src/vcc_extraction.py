import os
import tempfile
import pandas as pd

from data_structure import commit_columns, file_columns, function_columns
from git import Repo
from git.exc import GitCommandError
from pydriller import ModificationType
from commit_extraction import extract_commits
import re
import concurrent.futures
from pydriller import Git
import shutil
import logging


invalid_extensions = ('.txt', '.md', '.man', '.lang', '.loc', '.tex', '.texi', '.rst',
                      '.gif', '.png', '.jpg', '.jpeg', '.svg', '.ico',
                      '.css', '.scss', '.less',
                      '.gradle', '.ini',
                      '.zip',
                      '.pdf')
exclusions = (r"^(install|changelog(s)?|change(s)?|author(s)?|news|readme|todo|about(s)?|credit(s)?|license|release("
              r"s)?|release(s)?|release(_|-)note(s)?|version(s)?|makefile|pom|\.git.*|\.travis|\.classpath|\.project)$")


def get_file_name(file):
    file_path = file.old_path
    # If this happens, then the file has been created in this commit
    if file_path == None:
        file_path = file.new_path
    return file_path


def print_blames(blamed):
    all_blamed_hashes = {blame for blames in blamed.values() for blame in blames}
    logging.info("Blamed {} commit(s)".format(len(all_blamed_hashes)))


def blame_deleted_lines(git_repo, fix_commit, fix_files):
    logging.info("Blaming the deleted lines***")
    blames = git_repo.get_commits_last_modified_lines(fix_commit)
    blamed_from_deleted_lines = {}
    for file, blamed_hashes in blames.items():
        if file not in fix_files:
            continue
        blamed_from_deleted_lines[file] = blamed_hashes
    print_blames(blamed_from_deleted_lines)
    return blamed_from_deleted_lines


def is_useless_line(line):
    return not line or \
        line.startswith("//") or \
        line.startswith("/*") or \
        line.startswith("*") or \
        line.startswith("#") or \
        line.startswith("'''") or \
        line.startswith('"""') or \
        line.startswith("=begin") or \
        line.startswith("<#") or \
        line.startswith("--") or \
        line.startswith("{-") or \
        line.startswith("--[[") or \
        line.startswith("<!--")


def is_valid_hunk(hunk, modified_file):
    # We are interested in change blocks made of added lines only
    if not all(line.startswith("+") for line in hunk["change_block"]):
        return False

    # If the change block is made ONLY of the following invalid lines, it is invalid for the blame
    first_line_block = int(hunk["new_start_line"]) + len(hunk["before_ctx"])
    last_line_block = first_line_block + len(hunk["change_block"]) - 1
    invalid_lines = []

    ## Step 1: useless lines are invalid
    for index, line in enumerate(hunk["change_block"]):
        if is_useless_line(line[1:].strip()):
            invalid_lines.append(index + first_line_block)
    ## Step 2: if the changed method entirely fits in the changed block, then it is a new method, and its lines are all invalid
    changed_methods = modified_file.changed_methods
    for m in changed_methods:
        if first_line_block <= m.start_line and m.end_line <= last_line_block:
            invalid_lines.extend(range(m.start_line, m.end_line + 1))
    ## Step 3: if a line doesn't belong to any method (constants, global variables, typedefs, etc.), it is invalid
    methods = modified_file.methods
    for i in range(first_line_block, last_line_block + 1):
        inside = False
        for m in methods:
            if m.start_line <= i and i <= m.end_line:
                inside = True
                break
        if not inside:
            invalid_lines.append(i)

    # Remove duplicates and sort
    invalid_lines = sorted(list(set(invalid_lines)))
    if invalid_lines == list(range(first_line_block, last_line_block + 1)):
        return False
    return True


def parse_hunks(diff):
    hunk_headers_indexes = []
    diff_lines = diff.splitlines()
    for index, diff_line in enumerate(diff_lines):
        if diff_line.startswith("@@ -"):
            hunk_headers_indexes.append(index)

    hunks_text = []
    for index, hunk_line in enumerate(hunk_headers_indexes):
        if not index == len(hunk_headers_indexes) - 1:
            hunk_text = diff_lines[hunk_line:hunk_headers_indexes[index + 1]]
        else:
            hunk_text = diff_lines[hunk_line:]
        hunks_text.append(hunk_text)

    hunks = []
    for hunk_text in hunks_text:
        hunk = {}
        hunk["raw_text"] = diff

        hunk["header"] = hunk_text[0]
        old = re.search("@@ -(.*) \+", hunk["header"]).group(1).strip().split(",")
        # Ignore subprojects commit hunks, which are very rare
        if len(old) < 2:
            continue
        hunk["old_start_line"] = old[0]
        hunk["old_length"] = old[1]
        new = re.search(".*\+(.*) @@", hunk["header"]).group(1).strip().split(",")
        # Ignore very small hungs, which are very rare
        if len(new) < 2:
            continue
        hunk["new_start_line"] = new[0]
        hunk["new_length"] = new[1]
        code_context = hunk["header"][hunk["header"].rfind("@") + 2:].strip()
        hunk["code_context"] = code_context

        change_block = [(i, line) for i, line in enumerate(hunk_text) if line.startswith("+") or line.startswith("-")]
        start_index = change_block[0][0]
        end_index = change_block[-1][0]
        hunk["before_ctx"] = hunk_text[1:start_index]
        hunk["change_block"] = [el[1] for el in change_block]
        hunk["after_ctx"] = hunk_text[end_index + 1:]
        hunks.append(hunk)
    return hunks


"""
Get the commits blamed on the lines before and after (ignoring the empty lines) the change blocks made of added lines only
"""


def blame_context_lines(git_repo, fix_commit, fix_files):
    logging.info("Blaming the context lines for add-only hunks***")
    blamed_from_context_lines = {}
    for modified_file in fix_commit.modified_files:
        filepath = get_file_name(modified_file)
        # We don't consider new files because they won't blame anything
        if modified_file.change_type == ModificationType.ADD:
            continue
        # Consider only the files previously appoved
        if not filepath in fix_files:
            continue
        hunks = parse_hunks(modified_file.diff)
        blamed_hashes = set()
        for hunk in hunks:
            # Do not consider invalid hunks
            if not is_valid_hunk(hunk, modified_file):
                continue

            # At this point, we are sure that the hunk is made of added lines only, we can safely consider the "old start line + offset" to blame the entire hunk context only
            start_line = str(hunk["old_start_line"])
            offset = "+" + hunk["old_length"]
            # If the file is not found in the previous commits, it may be due to, rare, double renaming: we ignore these cases
            try:
                blame_output = git_repo.repo.git.blame("-w", "-c", "-l", "-L", start_line + "," + offset,
                                                       fix_commit.hash + "^", "--", filepath)
            except GitCommandError:
                continue

            blamed_hashes = set()
            for blame_line in blame_output.splitlines():
                blame_line_split = blame_line.split("\t")
                blamed_hash = blame_line_split[0]
                code = blame_line_split[3].split(")")[1].strip()
                # Should an empty line be blamed, ignore it
                if not code:
                    continue
                blamed_hashes.add(blamed_hash)
            blamed_from_context_lines[filepath] = blamed_hashes
    print_blames(blamed_from_context_lines)
    return blamed_from_context_lines


def is_file_valid(file_path):
    # Extension check
    file_extension = os.path.splitext(file_path)[1]
    if file_extension in invalid_extensions:
        return False
    # Excluded files check
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    if re.match(exclusions, file_name, re.IGNORECASE):
        return False
    # Test files
    file_dir = '/' + os.path.dirname(file_path) + '/'
    directory_match = re.match(r"^.*\/tests?\/.*$", file_dir, re.IGNORECASE)
    prefix_match = re.match(r"^test.+", file_name, re.IGNORECASE)
    postfix_match = re.match(r".+test$", file_name, re.IGNORECASE)
    return not (directory_match or prefix_match or postfix_match)


def get_contributing_commits(git_repo, fix_commit, fix_files):
    blamed_from_deleted_lines = blame_deleted_lines(git_repo, fix_commit, fix_files)
    blamed_from_context_lines = blame_context_lines(git_repo, fix_commit, fix_files)

    file_blames = blamed_from_deleted_lines.copy()
    for file, item in blamed_from_context_lines.items():
        if file in file_blames:
            file_blames[file].update(item)
        else:
            file_blames[file] = item

    vcc_hash_list = {blame for blames in file_blames.values() for blame in blames}

    # Check if the set is empty
    if len(vcc_hash_list) == 0:
        return []
    else:
        return list(vcc_hash_list)


def get_fix_files(fix_commit):
    fix_files = []
    fix_added_lines = 0
    fix_removed_lines = 0
    for mod_file in fix_commit.modified_files:
        file_path = get_file_name(mod_file)
        if not is_file_valid(file_path):
            continue
        fix_files.append(file_path)
        fix_added_lines += mod_file.added_lines
        fix_removed_lines += mod_file.deleted_lines

    if len(fix_files) == 0:
        logging.warning("! Invalid fixing commit: no relevant files")
    if fix_added_lines == 0 and fix_removed_lines == 0:
        logging.warning("! Invalid fixing commit: no actual modifications")

    return fix_files


def process_commit(temp_dir, repo_url, fix_hash):
    # Initialize the Git repo object once
    git_repo = Git(temp_dir)
    vcc_hashes = []
    vcc_info = []
    try:
        fix_commit = git_repo.get_commit(fix_hash)
        fix_files = get_fix_files(fix_commit)
        logging.info(f"Start to fetch VCC based on fix commit: {repo_url} and {fix_hash}")
        vcc_hashes = get_contributing_commits(git_repo, fix_commit, fix_files)
        # Incase multiple lines blame to same vcc
        vcc_hashes = list(set(vcc_hashes))

        if len(vcc_hashes) != 0:
            # Collect the VCC info
            for vcc_hash in vcc_hashes:
                vcc_info_row = ';'.join([repo_url, fix_hash, vcc_hash])
                vcc_info.append(vcc_info_row)

    except Exception as e:
        logging.error(f"Error fetching commit when using Git: {repo_url} and {fix_hash}: {e}")

    return vcc_info, vcc_hashes


def get_vcc(repo_url, hashes):
    vcc_info_list = []
    commit_info = []
    file_info = []
    function_info = []
    vcc_hash_list = []

    # Ensure repo_url ends with '.git' if it is a GitHub URL
    if 'github' in repo_url and not repo_url.endswith('.git'):
        repo_url += '.git'

    temp_repo = tempfile.TemporaryDirectory()
    temp_dir = temp_repo.name

    try:
        # Clone the repository into the temporary directory
        Repo.clone_from(repo_url, temp_dir)
    except GitCommandError as e:
        logging.error(f"Error occurred while cloning the repository {repo_url}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while cloning the repository: {e}")
        return None

    try:
        for fix_hash in hashes:
            try:
                vcc_info, vcc_hashes = process_commit(temp_dir, repo_url, fix_hash)
                vcc_info_list.extend(vcc_info)
                vcc_hash_list.extend(vcc_hashes)
            except Exception as e:
                logging.error(f"Error processing fix commit hash {fix_hash}: {e}")

        if len(vcc_hash_list) != 0:
            # Incase some vcc contribute to multiple vul
            vcc_hash_list = list(set(vcc_hash_list))
            # Incase some fc also be blamed as vcc
            common_elements = set(hashes).intersection(set(vcc_hash_list))
            if common_elements:
                logging.warning(f"!The fc also be blamed as vcc in {repo_url}: {common_elements}")

        all_hashes = hashes.copy()
        all_hashes.extend(vcc_hash_list)

        logging.info(f"#####Number of commits need to be processed in repo {repo_url}: {len(all_hashes)}")
        repo_commits, repo_files, repo_methods = extract_commits(temp_dir, all_hashes, hashes, 100)

        if len(repo_commits) < len(all_hashes):
            if len(repo_commits) != 0:
                temp_df = pd.DataFrame(repo_commits)
                result = [item for item in all_hashes if item not in set(temp_df['hash'])]
                logging.warning(f"++++Failed process {len(all_hashes)-len(repo_commits)} commits in {repo_url}, missing hashes: {result}")
            else:
                logging.info(f"++++Failed process {len(all_hashes)-len(repo_commits)} commits in {repo_url}, missing hashes: {all_hashes}")

        commit_info.extend(repo_commits)
        file_info.extend(repo_files)
        function_info.extend(repo_methods)

    except Exception as e:
        logging.error(f"Error initializing Git repo: {e}")

    # Clean up: Remove the temporary directory and its contents
    try:
        temp_repo.cleanup()
    except (PermissionError, OSError):
        # On Windows there might be cleanup errors.
        # Manually remove files
        logging.error(f"Repo cleanup failed for {repo_url}, trying manual removal")
        try:
            shutil.rmtree(temp_repo.name, ignore_errors=True)
        except Exception as cleanup_error:
            logging.error(f"Manual cleanup also failed for {repo_url}: {cleanup_error}")

    return vcc_info_list, commit_info, file_info, function_info


def fetch_vcc_for_row(row):
    """
    Helper function to process each row and get VCC info.
    """
    repo_url = row['repo_url']
    hashes = row['fc_hash']
    return get_vcc(repo_url, hashes)


def nan_list_to_none(lst):
    if len(lst) == 1 and pd.isna(lst[0]):
        return None
    return lst


def store_data(file_info_all, function_info_all, vcc_info_list_all, commit_info_all):

    # Process vcc info
    df_vcc_info = pd.DataFrame(vcc_info_list_all, columns=['vcc_info_list'])
    df_vcc_info['vcc_hash'] = df_vcc_info['vcc_info_list'].apply(lambda x: x.split(';')[-1])
    df_vcc_info['fc_hash'] = df_vcc_info['vcc_info_list'].apply(lambda x: x.split(';')[-2])
    fc_vcc_hash_df = df_vcc_info.groupby('fc_hash')['vcc_hash'].apply(list).reset_index()
    fc_vcc_hash_df['vcc_hash'] = fc_vcc_hash_df['vcc_hash'].apply(nan_list_to_none)
    fc_vcc_hash_df = fc_vcc_hash_df.drop_duplicates(subset='fc_hash')

    # Save fc_vcc_hash data
    fc_vcc_hash_df.to_csv('..//data/processed/fc_vcc_hash.csv', index=False)
    logging.info("------------------------------------------------------------------------------")
    logging.info(f"Successfully stored info to fc_vcc_hash.csv, table shape: {fc_vcc_hash_df.shape}")

    # Create and store commit_info data
    commit_info_df = pd.DataFrame(commit_info_all, columns=commit_columns)
    # commit_info_df = commit_info_df.drop_duplicates(subset='hash')
    commit_info_df.to_csv('..//data/processed/commit_info.csv', index=False)
    logging.info(f"Successfully stored info to commit_info.csv, table shape: {commit_info_df.shape}")

    # Create and store file_info data
    file_info_df = pd.DataFrame(file_info_all, columns=file_columns)
    file_info_df = file_info_df.drop_duplicates(subset='code_after')
    file_info_df.to_csv('..//data/processed/file_info.csv', index=False)
    logging.info(f"Successfully stored info to file_info.csv, table shape: {file_info_df.shape}")

    # Process and store function_info data
    function_info_df = pd.DataFrame(function_info_all, columns=function_columns)
    total_rows = len(function_info_df)
    function_info_df = function_info_df.drop_duplicates(subset='code')
    rows_after = len(function_info_df)
    num_duplicates = total_rows - rows_after
    function_info_df.to_csv('..//data/processed/function_info.csv', index=False)
    logging.info(f"Dropped duplicates with the same source code in total: {num_duplicates}")
    logging.info(f"Successfully stored info to function_info.csv, table shape: {function_info_df.shape}")
    logging.info("------------------------------------------------------------------------------")


def get_vcc_url(df, max_workers):
    """
    Fetch metadata for multiple repository URLs in parallel.
    """
    vcc_info_list_all = []
    commit_info_all = []
    file_info_all = []
    function_info_all = []
    i = 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Map each row to the fetch_vcc_for_row function
        future_to_row = {executor.submit(fetch_vcc_for_row, row): row for _, row in df.iterrows()}

        for future in concurrent.futures.as_completed(future_to_row):
            logging.info(f"*******Processing completed repo in total: {i}")
            print(f"Processing completed repositories in total: {i}")
            i += 1
            row = future_to_row[future]
            try:
                vcc_info_list, commit_info, file_info, function_info = future.result()
                file_info_all.extend(file_info)
                function_info_all.extend(function_info)
                if vcc_info_list is not None:
                    vcc_info_list_all.extend(vcc_info_list)
                commit_info_all.extend(commit_info)
            except Exception as e:
                logging.error(f"Error processing row {row}: {e}")

    # Save all collected data at once
    store_data(file_info_all, function_info_all, vcc_info_list_all, commit_info_all)

    return True
