import re
import pandas as pd
import ast


def delete_outliers_by_msg(msg):
    if not isinstance(msg, str):
        return False

    # Define include and exclude patterns
    include_keywords = [r'\bmerge\b\s+.*\s+\bbranch\b', r'\bpull\s+request\b']
    exclude_keywords = ["fix", r'CVE-\d{4}-\d{4,5}']

    # Combine the include and exclude keywords into regex patterns
    include_pattern = '|'.join(include_keywords)
    exclude_pattern = '|'.join(exclude_keywords)

    # Use re.search() to check if the message contains any of the include patterns and does not contain any exclude
    # patterns
    if re.search(include_pattern, msg, flags=re.IGNORECASE) and not re.search(exclude_pattern, msg,
                                                                              flags=re.IGNORECASE):
        return True
    else:
        return False


# the fix commit that is also be blamed as VCC
def delete_outliers_by_vcc(log_file_path):
    """
    Extracts all hashes from log file records starting with a specific pattern.
    Hashes enclosed in curly braces {} are stored in a list, without extra quotes.

    Args:
        log_file_path (str): Path to the log file.

    Returns:
        list: A list containing all extracted hashes without extra quotes.
    """
    # Initialize a list to store the hashes
    hash_list = []

    # Define the regex pattern to match the specific log format
    pattern = r"^.*WARNING\s+!The fc also be blamed as vcc.*?{([^}]*)}"

    # Open and read the log file line by line
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            match = re.search(pattern, line)
            if match:
                # Extract hashes inside {} and split them by comma
                hashes = match.group(1).split(", ")
                # Strip whitespace and any surrounding quotes, then append to the list
                hash_list.extend(hash.strip(" '\"") for hash in hashes)

    return hash_list


# Function to convert string-formatted list to actual list
def convert_to_list(vcc_hash_str):
    if pd.isna(vcc_hash_str):
        return []
    try:
        return ast.literal_eval(vcc_hash_str.strip())
    except (ValueError, SyntaxError):
        return []


def map_commit_info(df1, df2):
    df1.drop_duplicates(subset=['fc_hash'])

    # Apply the conversion to the 'vcc_hash' column
    df1['vcc_hash'] = df1['vcc_hash'].apply(convert_to_list)

    # Create new columns in df2
    df2['commit_type'] = ''
    df2['cwe_id'] = ''
    df2['repo_url'] = ''

    # Iterate through df1 and update df2
    for _, row in df1.iterrows():
        # Handle FC hashes first
        fc_matches = df2['hash'] == row['fc_hash']
        df2.loc[fc_matches, ['commit_type', 'cwe_id', 'repo_url']] = ['FC', row['cwe_id'], row['repo_url']]

        # Handle VCC hashes
        for vcc_hash in row['vcc_hash']:
            if pd.notna(vcc_hash):
                vcc_matches = df2['hash'] == vcc_hash
                df2.loc[vcc_matches, ['commit_type', 'cwe_id', 'repo_url']] = ['VCC', row['cwe_id'], row['repo_url']]

    # Filter for FC commit types and remove duplicates based on 'hash'
    df2 = df2[df2['commit_type'] == 'FC'].drop_duplicates(subset=['hash'])

    return df2
