import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from git import Repo
from pydriller import Repository


def get_method_code(source_code, start_line, end_line):
    try:
        if source_code is not None:
            code = ('\n'.join(source_code.split('\n')[int(start_line) - 1: int(end_line)]))
            return code
        else:
            return None
    except Exception as e:
        logging.error(f'Problem while extracting method code from the changed file contents: {e}')
        pass


def changed_methods_both(file):
    """
    Return the list of methods that were changed.
    :return: list of methods
    """
    new_methods = file.methods
    old_methods = file.methods_before
    added = file.diff_parsed["added"]
    deleted = file.diff_parsed["deleted"]

    methods_changed_new = {
        y
        for x in added
        for y in new_methods
        if y.start_line <= x[0] <= y.end_line
    }
    methods_changed_old = {
        y
        for x in deleted
        for y in old_methods
        if y.start_line <= x[0] <= y.end_line
    }
    return methods_changed_new, methods_changed_old


def process_method_before(commit_hash, file_source_code_before, mb):
    if file_source_code_before is not None:
        return {
            'hash': commit_hash,
            'name': mb.name,
            'filename': mb.filename,
            'num_lines_of_code': mb.nloc,
            'complexity': mb.complexity,
            'token_count': mb.token_count,
            'parameters': mb.parameters,
            'signature': mb.long_name,
            'start_line': mb.start_line,
            'end_line': mb.end_line,
            # 'fan_in': mb.fan_in,
            # 'fan_out': mb.fan_out,
            # 'general_fan_out': mb.general_fan_out,
            'length': mb.length,
            'top_nesting_level': mb.top_nesting_level,
            'code': get_method_code(file_source_code_before, mb.start_line, mb.end_line),
            'before_change': 'True'
        }


def process_method_after(commit_hash, file_source_code, mc):
    if file_source_code is not None:
        return {
            'hash': commit_hash,
            'name': mc.name,
            'filename': mc.filename,
            'num_lines_of_code': mc.nloc,
            'complexity': mc.complexity,
            'token_count': mc.token_count,
            'parameters': mc.parameters,
            'signature': mc.long_name,
            'start_line': mc.start_line,
            'end_line': mc.end_line,
            # 'fan_in': mc.fan_in,
            # 'fan_out': mc.fan_out,
            # 'general_fan_out': mc.general_fan_out,
            'length': mc.length,
            'top_nesting_level': mc.top_nesting_level,
            'code': get_method_code(file_source_code, mc.start_line, mc.end_line),
            'before_change': 'False'
        }


def get_methods(file, commit_hash):
    """
    returns the list of methods in the file.
    """
    file_methods = []
    file_source_code = file.source_code
    file_source_code_before = file.source_code_before

    try:
        if file.changed_methods:
            methods_after, methods_before = changed_methods_both(file)  # in source_code_after/_before
            futures = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                if methods_before:
                    futures.extend(executor.submit(process_method_before, commit_hash, file_source_code_before, mb) for mb in methods_before)
                if methods_after:
                    futures.extend(executor.submit(process_method_after, commit_hash, file_source_code, mc) for mc in methods_after)
                if futures:
                    for future in as_completed(futures):
                        result = future.result()
                        if result:
                            file_methods.append(result)

        if file_methods:
            return file_methods
        else:
            return None

    except Exception as e:
        logging.error(f'Extracting failed for methods in: {commit_hash}, {e}')
        pass


def is_c_or_cpp_file_type(filename):
    if not filename:
        return False
    # List of file extensions to check (in lowercase)
    extensions = ('.c', '.h', '.ec', '.ecp', '.pgc', '.cpp', '.cxx', '.cc', '.pcc', '.hpp')
    # Convert filename to lowercase for case-insensitive comparison
    filename_lower = filename.lower()
    # Check if the filename ends with any of the extensions
    return any(filename_lower.endswith(ext) for ext in extensions)


def get_files(commit):
    """
    returns the list of files of the commit.
    """
    commit_files = []
    commit_methods = []
    try:
        logging.info(f'Extracting files for {commit.hash}')
        if commit.modified_files:
            for file in commit.modified_files:
                # logging.info(f'Processing file {file.filename}')
                # programming_language = guess_pl(file.source_code)

                if is_c_or_cpp_file_type(file.filename):
                    file_row = {
                        'hash': commit.hash,
                        'filename': file.filename,
                        'old_path': file.old_path,
                        'new_path': file.new_path,
                        'change_type': file.change_type,
                        'diff': file.diff,
                        'diff_parsed': file.diff_parsed,
                        'num_lines_added': file.added_lines,
                        'num_lines_deleted': file.deleted_lines,
                        'code_after': file.source_code,
                        'code_before': file.source_code_before,
                        'num_method_changed': len(file.changed_methods) if file.changed_methods else 0,
                        'num_lines_of_code': file.nloc,
                        'complexity': file.complexity,
                        'token_count': file.token_count,
                        # 'programming_language': programming_language,
                    }
                    commit_files.append(file_row)
                    file_methods = get_methods(file, commit.hash)

                    if file_methods is not None:
                        commit_methods.extend(file_methods)
        else:
            logging.info('The list of modified_files is empty')

        return commit_files, commit_methods

    except Exception as e:
        logging.error(f'Extract failed for files in:{commit.hash}, {e}')
        pass


def get_all_branch(repo_temp_dir):
    all_branches = []
    repo = Repo(repo_temp_dir)
    all_branch = repo.branches + repo.remotes.origin.refs

    for branch in all_branch:
        all_branches.append(branch.name)

    return all_branches


def extract_commits(repo_temp_dir, hashes, fc_hashes, max_workers):
    """This function extract git commit information of only the hashes list that were specified in the
    commit URL. All the commit_fields of the corresponding commit have been obtained.
    Every git commit hash can be associated with one or more modified/manipulated files.
    One vulnerability with same hash can be fixed in multiple files so we have created a dataset of modified files
    as 'df_file' of a project.
    :param fc_hashes:
    :param repo_temp_dir:
    :param max_workers:
    :param repo_url: list of url links of all the projects.
    :param hashes: list of hashes of the commits to collect
    :return dataframes: at commit level and file level.
    """
    repo_commits = []
    repo_files = []
    repo_methods = []

    target_branch = get_all_branch(repo_temp_dir)

    single_hash = None
    if len(hashes) == 1:
        single_hash = hashes[0]
        hashes = None

    for commit in Repository(path_to_repo=repo_temp_dir,
                             only_commits=hashes,
                             single=single_hash,
                             only_in_branch=target_branch,
                             num_workers=max_workers).traverse_commits():
        logging.info(f'-------Processing commit, {commit.hash}---------')
        try:
            commit_row = {
                'hash': commit.hash,
                'msg': commit.msg,
                'author': commit.author.email,
                'author_date': commit.author_date,
                'author_timezone': commit.author_timezone,
                'committer': commit.committer.email,
                'committer_date': commit.committer_date,
                'committer_timezone': commit.committer_timezone,
                'in_main_branch': commit.in_main_branch,
                'merge': commit.merge,
                'parents': commit.parents,
                'num_lines_deleted': commit.deletions,
                'num_lines_added': commit.insertions,
                'num_lines_changed': commit.lines,
                'num_files_changed': commit.files,
                'dmm_unit_size': commit.dmm_unit_size,
                'dmm_unit_complexity': commit.dmm_unit_complexity,
                'dmm_unit_interfacing': commit.dmm_unit_interfacing
            }
            repo_commits.append(commit_row)
            if commit.hash in fc_hashes:
                commit_files, commit_methods = get_files(commit)
                if len(commit_files) != 0:
                    repo_files.extend(commit_files)
                if len(commit_methods) != 0:
                    repo_methods.extend(commit_methods)
        except Exception as e:
            logging.error(f'Problem while fetching the commits:{commit.hash}, {e}')
            pass

    return repo_commits, repo_files, repo_methods