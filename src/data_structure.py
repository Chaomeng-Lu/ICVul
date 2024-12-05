# Table0 Repository info
repo_columns = [
    'repo_url',
    'repo_name',
    'owner',
    'description',
    'date_created',
    'date_last_push',
    'homepage',
    'repo_language',
    'forks_count',
    'stars_count',
    'size',
    'topics',
    'open_issues_count',
    'total_commits',
    'contributors_count',
    'releases_count',
    'tags_count',
    'collecting_date'
]

# Table1 CVE_CWE_FC_VCC
cve_cwe_commit_columns = [
    'cve_id',
    'cwe_id',
    'repo_url',
    'fc_hash',
    'vcc_hash'
]

# Table2 FC(Fix Commit) info
# Table3 VCC(Vulnerability Contribute Commit) info
commit_columns = [
    'hash',
    'msg',
    'author',
    'author_date',
    'author_timezone',
    'committer',
    'committer_date',
    'committer_timezone',
    'in_main_branch',
    'merge',
    'parents',
    'num_lines_deleted',
    'num_lines_added',
    'num_lines_changed',
    'num_files_changed',
    'dmm_unit_size',
    'dmm_unit_complexity',
    'dmm_unit_interfacing'
]

# Table4 (changed)file info (remove all annotations), may have duplication
file_columns = [
    'hash',
    'filename',
    'old_path',
    'new_path',
    'change_type',
    'diff',
    'diff_parsed',
    'num_lines_added',
    'num_lines_deleted',
    'code_after',
    'code_before',
    'num_method_changed',
    'num_lines_of_code',
    'complexity',
    'token_count',
    # 'programming_language',
]

# Table5 (changed)function info (remove all annotations), may have duplication
function_columns = [
    'hash',
    'name',
    'filename',
    'num_lines_of_code',
    'complexity',
    'token_count',
    'parameters',
    'signature',
    'start_line',
    'end_line',
    # 'fan_in',
    # 'fan_out',
    # 'general_fan_out', Still under developing, not working in lizard
    'length',
    'top_nesting_level',
    'code',
    'before_change'
]
"""Features Explanation: fan_in: This metric measures how many other functions or methods call a particular function. 
In other words, it indicates the number of functions that depend on the function in question. fan_out: This metric 
measures how many functions or methods are called by a particular function. It indicates the number of functions that 
the function in question depends on. general_fan_out: While fan_out covers direct dependencies (i.e., the functions a 
method directly calls), general_fan_out might refer to a broader measure of dependencies. This can include not just 
direct calls but also transitive dependencies — essentially, the total number of unique functions that can be reached 
starting from the function in question, including all levels of indirect calls."""